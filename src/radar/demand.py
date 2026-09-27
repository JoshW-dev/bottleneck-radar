"""Stage 2: hyperscaler capex from SEC XBRL, converted into physical units."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

import yaml

from . import edgar
from .config import CONFIG, DATA, month_key
from .http import get
from .store import write_json

HYPERSCALERS = {
    "MSFT": {"name": "Microsoft", "cik": "0000789019", "tag": "PaymentsToAcquirePropertyPlantAndEquipment"},
    "AMZN": {"name": "Amazon", "cik": "0001018724", "tag": "PaymentsToAcquireProductiveAssets"},
    "GOOGL": {"name": "Alphabet", "cik": "0001652044", "tag": "PaymentsToAcquirePropertyPlantAndEquipment"},
    "META": {"name": "Meta", "cik": "0001326801", "tag": "PaymentsToAcquirePropertyPlantAndEquipment"},
    "ORCL": {"name": "Oracle", "cik": "0001341439", "tag": "PaymentsToAcquirePropertyPlantAndEquipment"},
}
QUARTER_DAYS = range(80, 100)
CAPEX_TERMS = re.compile(r"capital expenditure|capex|property and equipment", re.I)
FORWARD_TERMS = re.compile(r"\b(expect|expects|anticipate|outlook|guidance|forecast|plan to|will be)\b", re.I)


def _day(value: str) -> date:
    return date.fromisoformat(value)


def quarterly(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Quarterly values from XBRL cash-flow facts, oldest first.

    Cash-flow facts are often year-to-date (a Q3 10-Q reports nine months), so a
    quarter is the difference between consecutive year-to-date values that share a
    start date. Facts that already span one quarter are used as they are.
    """
    newest: dict[tuple[str, str], dict[str, Any]] = {}
    for fact in facts:
        key = (fact["start"], fact["end"])
        if key not in newest or fact["filed"] > newest[key]["filed"]:
            newest[key] = fact

    quarters: dict[str, dict[str, Any]] = {}
    by_start: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for (start, end), fact in newest.items():
        by_start[start].append(fact)
        if (_day(end) - _day(start)).days in QUARTER_DAYS:
            quarters[end] = {"start": start, "end": end, "value": fact["val"], "derived": False}

    for group in by_start.values():
        group.sort(key=lambda f: f["end"])
        for earlier, later in zip(group, group[1:]):
            start = (_day(earlier["end"]) + timedelta(days=1)).isoformat()
            if later["end"] not in quarters and (_day(later["end"]) - _day(start)).days in QUARTER_DAYS:
                quarters[later["end"]] = {
                    "start": start,
                    "end": later["end"],
                    "value": later["val"] - earlier["val"],
                    "derived": True,
                }
    return [quarters[end] for end in sorted(quarters)]


def consecutive_tail(quarters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The newest run of quarters with no gaps between them."""
    tail = quarters[-1:]
    for quarter in reversed(quarters[:-1]):
        if _day(tail[0]["start"]) - _day(quarter["end"]) != timedelta(days=1):
            break
        tail.insert(0, quarter)
    return tail


def summarize(quarters: list[dict[str, Any]]) -> dict[str, Any]:
    tail = consecutive_tail(quarters)[-8:]
    values = [q["value"] for q in tail]
    out: dict[str, Any] = {"quarters": tail, "latest": tail[-1]}
    if len(values) >= 2:
        out["qoq"] = values[-1] / values[-2] - 1
    if len(values) >= 5:
        out["yoy"] = values[-1] / values[-5] - 1
    if len(values) >= 4:
        out["ttm"] = sum(values[-4:])
    if len(values) >= 8:
        out["prior_ttm"] = sum(values[:4])
        out["ttm_growth"] = out["ttm"] / out["prior_ttm"] - 1
    return out


def load_assumptions() -> dict[str, Any]:
    return yaml.safe_load((CONFIG / "assumptions.yaml").read_text())


def physical(capex_usd: float, a: dict[str, Any]) -> dict[str, float]:
    """What a pile of capex buys, using the factors in config/assumptions.yaml."""
    spend = capex_usd * a["datacenter_share_of_capex"]["value"]
    mw = spend / a["capex_per_gw"]["value"] * 1000
    gpus = mw * a["it_power_share"]["value"] * 1000 / a["kw_per_gpu"]["value"]
    return {
        "capex_usd": capex_usd,
        "gw": mw / 1000,
        "gpus": gpus,
        "hbm_gb": gpus * a["hbm_gb_per_gpu"]["value"],
        "sqft": mw * a["sqft_per_mw"]["value"],
        "turbines_7ha": mw / a["mw_per_turbine"]["value"],
    }


NARRATIVE = re.compile(
    r"\b(was|were|is|are|increased|decreased|grew|rose|fell|expects?|anticipates?|driven|reflects?|reflecting)\b", re.I
)


def _is_prose(sentence: str) -> bool:
    """Keeps narrative sentences and drops table labels, which rarely end in a period or carry a verb."""
    digits = sum(ch.isdigit() for ch in sentence)
    return (
        sentence.endswith(".")
        and len(sentence.split()) >= 10
        and digits / len(sentence) < 0.15
        and bool(NARRATIVE.search(sentence))
    )


def guidance(cik: str) -> dict[str, Any]:
    """Capex sentences from the latest earnings release, copied word for word."""
    release = edgar.latest_earnings_release(cik)
    if not release:
        return {"error": "no earnings release exhibit found"}
    text = edgar.html_to_text(get(release["url"], sec=True, ttl_hours=24 * 7))
    lines = [s.lstrip("•·- ").strip() for s in edgar.sentences(text)]
    capex = [s for s in lines if CAPEX_TERMS.search(s) and _is_prose(s)]
    forward = [s for s in capex if FORWARD_TERMS.search(s)]
    return {**release, "forward": forward[:4], "other": [s for s in capex if s not in forward][:4]}


def run() -> dict[str, Any]:
    assumptions = load_assumptions()
    companies = {}
    for ticker, info in HYPERSCALERS.items():
        facts = edgar.concept(info["cik"], info["tag"])["units"]["USD"]
        companies[ticker] = {
            "name": info["name"],
            "xbrl_tag": info["tag"],
            **summarize(quarterly(facts)),
            "guidance": guidance(info["cik"]),
        }

    ttm = sum(c["ttm"] for c in companies.values())
    prior = sum(c["prior_ttm"] for c in companies.values())
    run_rate = 4 * sum(c["latest"]["value"] for c in companies.values())
    result = {
        "generated": date.today().isoformat(),
        "companies": companies,
        "total": {"ttm": ttm, "prior_ttm": prior, "ttm_growth": ttm / prior - 1, "run_rate": run_rate},
        "physical": {
            "ttm": physical(ttm, assumptions),
            "run_rate": physical(run_rate, assumptions),
            "added_vs_prior_ttm": physical(ttm - prior, assumptions),
        },
        "assumptions": assumptions,
        "notes": [
            "Capex is cash paid for property and equipment (Amazon: productive assets). Finance leases are excluded.",
            "Quarters end on different months: Oracle's fiscal quarters end in Feb, May, Aug and Nov.",
        ],
    }
    path = write_json(DATA / month_key() / "demand.json", result)

    p = result["physical"]["ttm"]
    print(f"Hyperscaler capex, trailing 4 quarters: ${ttm / 1e9:,.0f}B ({ttm / prior - 1:+.0%} on the prior year), "
          f"run rate ${run_rate / 1e9:,.0f}B")
    print(f"  = {p['gw']:.1f} GW, {p['gpus'] / 1e6:.1f}M GPUs, {p['hbm_gb'] / 1e9:.2f}B GB of HBM, "
          f"{p['sqft'] / 1e6:,.0f}M sq ft, {p['turbines_7ha']:,.0f} turbine-equivalents")
    for ticker, c in companies.items():
        print(f"  {ticker}: latest quarter to {c['latest']['end']} ${c['latest']['value'] / 1e9:.1f}B "
              f"({c.get('yoy', 0):+.0%} y/y), {len(c['guidance'].get('forward', []))} forward-looking capex quotes")
    print(f"  wrote {path.relative_to(DATA.parent)}")
    return result
