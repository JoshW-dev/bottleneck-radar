"""The month's call turned into a dated basket: the bottleneck's owners at equal weight, with the
consensus trade alongside as the comparison.

A snapshot is written once and never rewritten, so the track record can't be edited after the
fact. `radar performance` prices every snapshot from the first close after it was published.
"""

from __future__ import annotations

from typing import Any

from .bottleneck import load_owners
from .config import DATA
from .store import read_json, write_json

PICKS = DATA / "picks"
RULE = (
    "Equal weight across the call's owners, bought at the first close after the call is published "
    "and held until the next call replaces it. Prices in US dollars, dividends included."
)


def basket(ids: list[str], owners: dict[str, Any]) -> list[dict[str, Any]]:
    companies = owners["companies"]
    priced = [i for i in ids if companies[i].get("quote")]
    weight = round(1 / len(priced), 6) if priced else 0.0
    return [
        {
            "id": i,
            "name": companies[i]["name"],
            "quote": companies[i]["quote"],
            "weight": weight,
            "role": companies[i].get("role", ""),
        }
        for i in priced
    ]


def snapshot(call: dict[str, Any], owners: dict[str, Any]) -> dict[str, Any]:
    return {
        "month": call["month"],
        "published": call["generated"],
        "bottleneck": call["bottleneck"],
        "label": owners["inputs"][call["bottleneck"]]["label"],
        "headline": call["headline"],
        "rule": RULE,
        "picks": basket(call["owners"], owners),
        "consensus": basket(call["consensus_trade"], owners),
    }


def snapshots() -> list[dict[str, Any]]:
    return [read_json(p) for p in sorted(PICKS.glob("*.json"))]


def run(force: bool = False) -> dict[str, Any] | None:
    calls = sorted(DATA.glob("20[0-9][0-9]-[01][0-9]/bottleneck.json"))
    if not calls:
        print("No call yet, so no picks. Run `radar bottleneck` first.")
        return None
    call = read_json(calls[-1])
    path = PICKS / f"{call['month']}.json"
    if path.exists() and not force:
        print(f"Picks for {call['month']} were frozen on {read_json(path)['published']}; leaving {path.relative_to(DATA.parent)} as it is.")
        return read_json(path)
    snap = snapshot(call, load_owners())
    write_json(path, snap)
    tickers = ", ".join(p["quote"] for p in snap["picks"])
    print(f"Picks for {call['month']}: {tickers}, {snap['picks'][0]['weight']:.0%} each. Wrote {path.relative_to(DATA.parent)}")
    return snap
