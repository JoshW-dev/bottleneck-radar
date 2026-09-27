"""Stage 3b: name the one input where demand runs furthest ahead of supply, and write the monthly memo."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import yaml

from . import llm
from .config import CONFIG, DATA, month_key
from .store import read_json, write_json, write_text

INPUTS = ["memory", "advanced_chips", "gas_turbines", "grid_interconnection"]

SYSTEM = """You write a short monthly research note on the AI data center supply chain for one reader.

You get this month's data as JSON:
- demand: hyperscaler capex from SEC filings, converted into physical units with stated assumptions, plus forward-looking capex quotes
- supply: figures for four candidate inputs (memory chips, leading-edge chips, gas turbines, grid connections)
- owners: which listed companies make each input
- consensus_candidates: the companies most investors already own for AI exposure
- last_month: last month's note, if there is one

Do this:
1. Rank all four inputs by tightness from 1 (loose) to 5 (tightest). Tight means demand is growing faster than supply can, and supply has little room to add capacity soon.
2. Pick the ONE input that is the bottleneck. Explain why in plain English, citing the numbers you were given.
3. Name who owns it, using only ids from that input's owners list.
4. Name the consensus trade, meaning what most investors buy instead, using only ids from consensus_candidates.
5. Give two to four falsifiers: a specific figure in next month's data and the threshold that would show this call is wrong.
6. Compare with last_month: what changed and why. If it is null, say this is the first note.
7. List data gaps: failed sources, figures entered by hand, stale dates, and assumptions marked unverified.

Rules:
- Use only numbers that appear in the data. Say how old a figure is when it matters.
- Leading-edge chips have no direct supply series here. Taiwan's export orders measure demand for Taiwanese electronics, so say so if you lean on them.
- Short, plain sentences. No em dashes. No hype.
- This is research. Never tell the reader to buy, sell or hold anything."""


def load_owners() -> dict[str, Any]:
    return yaml.safe_load((CONFIG / "owners.yaml").read_text())


def schema(owners: dict[str, Any]) -> dict[str, Any]:
    ids = sorted(owners["companies"])
    text = {"type": "string"}

    def obj(**props: Any) -> dict[str, Any]:
        return {"type": "object", "additionalProperties": False, "required": list(props), "properties": props}

    return obj(
        bottleneck={"type": "string", "enum": INPUTS},
        headline=text,
        why=text,
        ranking={
            "type": "array",
            "items": obj(
                input={"type": "string", "enum": INPUTS},
                tightness={"type": "integer"},
                demand_signal=text,
                supply_signal=text,
            ),
        },
        owners={"type": "array", "items": {"type": "string", "enum": ids}},
        consensus_trade={"type": "array", "items": {"type": "string", "enum": ids}},
        falsifiers={"type": "array", "items": obj(metric=text, threshold=text, why=text)},
        change_vs_last_month=text,
        data_gaps={"type": "array", "items": text},
    )


def _physical(p: dict[str, float]) -> dict[str, float]:
    return {
        "gw": round(p["gw"], 1),
        "gpus_millions": round(p["gpus"] / 1e6, 2),
        "hbm_gb_billions": round(p["hbm_gb"] / 1e9, 2),
        "sqft_millions": round(p["sqft"] / 1e6, 1),
        "turbine_equivalents_7ha": round(p["turbines_7ha"]),
    }


def previous_month(month: str) -> str:
    year, mon = map(int, month.split("-"))
    return f"{year - (mon == 1):04d}-{12 if mon == 1 else mon - 1:02d}"


def evidence(demand: dict, supply: dict, owners: dict, previous: dict | None) -> dict[str, Any]:
    names = owners["companies"]

    def listing(ids: list[str]) -> list[dict[str, str]]:
        return [{"id": i, "name": names[i]["name"]} for i in ids]

    companies = demand["companies"]
    return {
        "today": date.today().isoformat(),
        "demand": {
            "hyperscaler_capex_ttm_usd_bn": round(demand["total"]["ttm"] / 1e9, 1),
            "ttm_growth": round(demand["total"]["ttm_growth"], 3),
            "run_rate_usd_bn": round(demand["total"]["run_rate"] / 1e9, 1),
            "latest_quarters": {
                t: {"quarter_end": c["latest"]["end"], "capex_usd_bn": round(c["latest"]["value"] / 1e9, 1), "yoy": round(c.get("yoy", 0), 3)}
                for t, c in companies.items()
            },
            "physical_ttm": _physical(demand["physical"]["ttm"]),
            "physical_added_vs_prior_year": _physical(demand["physical"]["added_vs_prior_ttm"]),
            "forward_capex_quotes": {t: c["guidance"]["forward"] for t, c in companies.items() if c["guidance"].get("forward")},
            "unverified_assumptions": [k for k, v in demand["assumptions"].items() if v.get("status")],
        },
        "supply": {
            "memory": supply.get("memory"),
            "advanced_chips": {"taiwan_export_orders": supply.get("export_orders")},
            "gas_turbines": supply.get("gas_turbines"),
            "grid_interconnection": supply.get("grid"),
        },
        "failed_sources": supply.get("errors", []),
        "owners": {i: listing(owners["inputs"][i]["owners"]) for i in INPUTS},
        "consensus_candidates": listing(owners["consensus_candidates"]),
        "last_month": previous
        and {k: previous.get(k) for k in ("month", "bottleneck", "headline", "falsifiers", "ranking")},
    }


def validate(call: dict[str, Any], owners: dict[str, Any]) -> dict[str, Any]:
    """Keep owners to the chosen input's list and the consensus to its candidates."""
    allowed = owners["inputs"][call["bottleneck"]]["owners"]
    dropped = [c for c in call["owners"] if c not in allowed]
    call["owners"] = [c for c in call["owners"] if c in allowed] or list(allowed)
    call["consensus_trade"] = [c for c in call["consensus_trade"] if c in owners["consensus_candidates"]]
    if dropped:
        call["data_gaps"].append(f"Dropped owners that aren't listed for {call['bottleneck']}: {', '.join(dropped)}")
    call["ranking"].sort(key=lambda r: -r["tightness"])
    return call


def _tidy_all(value: Any) -> Any:
    if isinstance(value, str):
        return llm.tidy(value)
    if isinstance(value, list):
        return [_tidy_all(v) for v in value]
    if isinstance(value, dict):
        return {k: _tidy_all(v) for k, v in value.items()}
    return value


def _cell(text: Any) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def _pct(x: float | None) -> str:
    return f"{x:+.0%}" if x is not None else "n/a"


def numbers_table(demand: dict, supply: dict) -> list[str]:
    """The figures behind the call, rendered by code so the memo can't misquote them."""
    rows: list[tuple[str, str, str, str]] = []
    total = demand["total"]
    latest_end = max(c["latest"]["end"] for c in demand["companies"].values())
    rows.append(("Hyperscaler capex, trailing 4 quarters", f"${total['ttm'] / 1e9:,.0f}B ({_pct(total['ttm_growth'])} y/y)", f"to {latest_end}", "SEC XBRL"))
    p = demand["physical"]["ttm"]
    rows.append(("Same capex in physical terms", f"{p['gw']:.1f} GW, {p['gpus'] / 1e6:.1f}M GPUs, {p['hbm_gb'] / 1e9:.2f}B GB of HBM, {p['turbines_7ha']:,.0f} turbine-equivalents", "", "config/assumptions.yaml"))
    if m := supply.get("memory"):
        rows.append(("Korea memory chip exports", f"${m['memory_usd'] / 1e9:.1f}B ({_pct(m.get('memory_yoy'))} y/y)", m.get("period", ""), f"[MOTIR]({m['source']})"))
        if "ddr5_16gb_contract_usd" in m:
            rows.append(("DDR5 16Gb contract price", f"${m['ddr5_16gb_contract_usd']:.2f} ({_pct(m.get('ddr5_16gb_yoy'))} y/y)", m.get("period", ""), f"[MOTIR]({m['source']})"))
    if o := supply.get("export_orders"):
        e = o["electronics"]
        rows.append(("Taiwan export orders, electronics", f"${e['usd_millions'] / 1e3:.1f}B ({_pct(e.get('yoy'))} y/y)", e["period"], f"[MOEA]({e['url']})"))
    for t in supply.get("gas_turbines", []):
        committed = t.get("backlog_and_slots_gw") or t.get("backlog_gw", 0) + t.get("slot_reservations_gw", 0)
        years = f", {t['years_of_backlog']} years of shipments" if t.get("years_of_backlog") else ""
        when = t.get("quarter") or str(t.get("as_of", ""))
        rows.append((f"{t['company']} gas backlog + slot reservations", f"{committed:g} GW{years}", when, f"[{t['method']}]({t['source']})"))
    for g in supply.get("grid", []):
        rows.append((g["name"], f"{g.get('base_load_gw')} GW base + {g.get('studied_load_gw')} GW studied", str(g["as_of"]), f"[manual]({g['source']})"))
    lines = ["| Figure | Value | As of | Source |", "|---|---|---|---|"]
    return lines + [f"| {' | '.join(_cell(c) for c in row)} |" for row in rows]


def memo(result: dict[str, Any], demand: dict, supply: dict, owners: dict) -> str:
    names, inputs = owners["companies"], owners["inputs"]

    def who(ids: list[str]) -> str:
        return ", ".join(f"{names[i]['name']} ({'/'.join(names[i]['tickers'])})" for i in ids) or "none named"

    lines = [
        f"# AI supply bottleneck, {date.fromisoformat(result['generated']):%B %Y}",
        "",
        f"## The call: {inputs[result['bottleneck']]['label']}",
        "",
        result["headline"],
        "",
        result["why"],
        "",
        "## Ranking",
        "",
        "| Input | Tightness | Demand | Supply |",
        "|---|---:|---|---|",
    ]
    for r in result["ranking"]:
        lines.append(f"| {inputs[r['input']]['label']} | {r['tightness']}/5 | {_cell(r['demand_signal'])} | {_cell(r['supply_signal'])} |")
    lines += ["", "## Who owns it", "", who(result["owners"]), "", "## The consensus trade", "", who(result["consensus_trade"]), ""]
    lines += ["## What would prove this wrong", "", "| Figure | Threshold | Why |", "|---|---|---|"]
    lines += [f"| {_cell(f['metric'])} | {_cell(f['threshold'])} | {_cell(f['why'])} |" for f in result["falsifiers"]]
    lines += ["", "## Since last month", "", result["change_vs_last_month"], "", "## Data gaps", ""]
    lines += [f"- {gap}" for gap in result["data_gaps"]] or ["- None"]
    lines += ["", "## The numbers", "", *numbers_table(demand, supply), "", "---", ""]
    usage = result["usage"]
    lines.append(
        f"Generated {result['generated']} by bottleneck-radar with {usage['model']} "
        f"({usage['input_tokens']:,} tokens in, {usage['output_tokens']:,} out, ${usage['cost_usd']:.2f}). "
        "Research notes only. Nothing here is investment advice."
    )
    return "\n".join(lines)


def run(dry_run: bool = False) -> dict[str, Any] | None:
    month = month_key()
    folder = DATA / month
    demand, supply = read_json(folder / "demand.json"), read_json(folder / "supply.json")
    owners = load_owners()
    last = DATA / previous_month(month) / "bottleneck.json"
    previous = read_json(last) if last.exists() else None
    user = "This month's data:\n\n" + json.dumps(evidence(demand, supply, owners, previous), indent=1, ensure_ascii=False, default=str)

    if dry_run or not llm.available():
        path = write_text(folder / "bottleneck-prompt.md", f"# System\n\n{SYSTEM}\n\n# User\n\n{user}")
        reason = "dry run" if dry_run else "no ANTHROPIC_API_KEY"
        print(f"Bottleneck call skipped ({reason}). Prompt saved to {path.relative_to(DATA.parent)}")
        return None

    call, usage = llm.structured(SYSTEM, user, schema(owners))
    call = validate(_tidy_all(call), owners)
    result = {"month": month, "generated": date.today().isoformat(), **call, "usage": usage}
    write_json(folder / "bottleneck.json", result)
    path = write_text(folder / "memo.md", memo(result, demand, supply, owners))
    print(f"Bottleneck: {owners['inputs'][call['bottleneck']]['label']}. {call['headline']}")
    print(f"  {usage['input_tokens']:,} tokens in, {usage['output_tokens']:,} out, ${usage['cost_usd']:.2f}; wrote {path.relative_to(DATA.parent)}")
    return result
