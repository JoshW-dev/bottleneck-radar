"""Stage 3a: supply-side inputs. Each source fails on its own, so one broken parser doesn't stop the run."""

from __future__ import annotations

import traceback
from datetime import date
from typing import Any, Callable

import yaml

from ..config import CONFIG, DATA, month_key
from ..store import write_json
from . import korea, taiwan, turbines

STALE_DAYS = 120


def _attempt(name: str, fn: Callable[[], Any], errors: list[dict[str, str]]) -> Any:
    try:
        return fn()
    except Exception as exc:  # a failed source becomes a data gap in the memo
        errors.append({"source": name, "error": f"{type(exc).__name__}: {exc}"})
        traceback.print_exc()
        return None


def manual_entries() -> dict[str, list[dict[str, Any]]]:
    entries = yaml.safe_load((CONFIG / "manual.yaml").read_text()) or {}
    today = date.today()
    for group in entries.values():
        for entry in group:
            as_of = entry["as_of"] if isinstance(entry["as_of"], date) else date.fromisoformat(str(entry["as_of"]))
            entry["age_days"] = (today - as_of).days
            entry["stale"] = entry["age_days"] > STALE_DAYS
            entry["method"] = "manual"
    return entries


def run() -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    manual = manual_entries()

    turbine_rows = [row for row in [_attempt("ge_vernova", turbines.ge_vernova, errors)] if row]
    turbine_rows += manual.get("gas_turbines", [])
    for row in turbine_rows:
        row["years_of_backlog"] = turbines.years_of_backlog(row)

    result = {
        "generated": date.today().isoformat(),
        "memory": _attempt("korea_memory_exports", korea.fetch, errors),
        "export_orders": _attempt("taiwan_export_orders", taiwan.fetch, errors),
        "gas_turbines": turbine_rows,
        "grid": manual.get("grid", []),
        "errors": errors,
    }
    path = write_json(DATA / month_key() / "supply.json", result)

    if memory := result["memory"]:
        print(f"Korea memory chip exports {memory['period']}: ${memory['memory_usd'] / 1e9:.1f}B "
              f"({memory['memory_yoy']:+.0%} y/y); all chips ${memory['chips_usd'] / 1e9:.1f}B ({memory['chips_yoy']:+.0%})")
    if orders := result["export_orders"]:
        e = orders["electronics"]
        print(f"Taiwan export orders {orders['total']['period']}: ${orders['total']['usd_millions'] / 1e3:.1f}B "
              f"({orders['total'].get('yoy', 0):+.0%} y/y); electronics {e.get('yoy', 0):+.0%}")
    for row in turbine_rows:
        committed = row.get("backlog_and_slots_gw") or row.get("backlog_gw", 0) + row.get("slot_reservations_gw", 0)
        years = f", {row['years_of_backlog']} years at current shipments" if row["years_of_backlog"] else ""
        print(f"{row['company']}: {committed:g} GW committed ({row['method']}){years}")
    for row in result["grid"]:
        print(f"{row['name']}: {row.get('base_load_gw')} GW base + {row.get('studied_load_gw')} GW studied (manual, {row['age_days']} days old)")
    for err in errors:
        print(f"  FAILED {err['source']}: {err['error']}")
    print(f"  wrote {path.relative_to(DATA.parent)}")
    return result
