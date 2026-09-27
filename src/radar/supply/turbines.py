"""Gas turbine backlogs.

GE Vernova states its gas backlog in sentences in its earnings release on EDGAR,
so that part is parsed. Siemens Energy and MHI only publish theirs in slide decks,
so they come from config/manual.yaml for now.
"""

from __future__ import annotations

import re
from typing import Any

from .. import edgar
from ..http import get

GE_VERNOVA_CIK = "0001996810"
QUARTER = re.compile(r"\b(first|second|third|fourth)[- ]quarter(?: of)?,? (\d{4})", re.I)
PATTERNS = {
    "backlog_and_slots_gw": r"backlog and slot reservation agreements grew from [\d.]+ to ([\d.]+) GW",
    "backlog_gw": r"backlog growth from [\d.]+ to ([\d.]+) GW",
    "slot_reservations_gw": r"slot reservation agreements from [\d.]+ to ([\d.]+) GW",
    "shipped_gw_quarter": r"shipped ([\d.]+) GW",
    "year_end_target_gw": r"at least ([\d.]+) GW by year-end",
}
QUARTER_NUMBER = {"first": 1, "second": 2, "third": 3, "fourth": 4}


def parse_ge_vernova(text: str) -> dict[str, Any]:
    flat = re.sub(r"\s+", " ", text)
    out: dict[str, Any] = {}
    if m := QUARTER.search(flat):
        out["quarter"] = f"{m.group(2)}-Q{QUARTER_NUMBER[m.group(1).lower()]}"
    for key, pattern in PATTERNS.items():
        if m := re.search(pattern, flat, re.I):
            out[key] = float(m.group(1))
    return out


def ge_vernova() -> dict[str, Any]:
    release = edgar.latest_earnings_release(GE_VERNOVA_CIK)
    if not release:
        raise RuntimeError("no GE Vernova earnings release found")
    parsed = parse_ge_vernova(edgar.html_to_text(get(release["url"], sec=True, ttl_hours=24 * 7)))
    if "backlog_gw" not in parsed and "backlog_and_slots_gw" not in parsed:
        raise RuntimeError("GE Vernova's release no longer matches the backlog patterns")
    return {"company": "GE Vernova", **parsed, "filed": release["filed"], "source": release["url"], "method": "parsed"}


def years_of_backlog(entry: dict[str, Any]) -> float | None:
    """Backlog plus slot reservations over annualized shipments. Rough: shipments swing by quarter."""
    committed = entry.get("backlog_and_slots_gw") or (entry.get("backlog_gw", 0) + entry.get("slot_reservations_gw", 0))
    shipped = entry.get("shipped_gw_quarter")
    return round(committed / (4 * shipped), 1) if committed and shipped else None
