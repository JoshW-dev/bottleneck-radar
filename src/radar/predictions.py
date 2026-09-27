"""Dated predictions that the code checks against the data when they come due.

A set is frozen once: the time it was made, who made it and a SHA-256 of its predictions go in
the file, and the file is never edited. `radar predictions` checks every open prediction against
the pipeline's data, fetching what's missing once a prediction is due, and records each result
with the time it was checked. A result is never changed once recorded, even if the data is later
revised, so the scorecard only ever grows.
"""

from __future__ import annotations

import hashlib
import json
import operator
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from . import prices
from .clone import SITUATIONAL_AWARENESS
from .config import DATA
from .performance import BENCHMARK, Closes, max_drawdown
from .store import read_json, write_json

SETS = DATA / "predictions"
RESULTS = DATA / "prediction-results.json"
GRACE_DAYS = 30  # after its due date, a prediction with no data to check is marked void
GROUPS = {
    "memory": "Is memory still short?",
    "buildout": "Is the buildout still growing?",
    "power": "Is power the next squeeze?",
    "call": "Do the call and the fund stay on memory?",
    "picks": "Do the picks pay?",
}
OPS: dict[str, Callable[[Any, Any], bool]] = {
    ">=": operator.ge, ">": operator.gt, "<=": operator.le, "<": operator.lt, "==": operator.eq,
}
UNITS = {"pct", "points", "usd", "usd_b", "gw", "share", "text"}


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fingerprint(predictions: list[dict[str, Any]]) -> str:
    """SHA-256 of the predictions in a canonical form, so any later edit to the file shows."""
    canonical = json.dumps(predictions, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


# ---------- freezing a set ----------


def validate(predictions: list[dict[str, Any]], taken: set[str] = frozenset()) -> None:
    problems = []
    seen: set[str] = set()
    for p in predictions:
        pid = p.get("id", "?")
        for key in ("id", "group", "statement", "why", "confidence", "due", "check"):
            if key not in p:
                problems.append(f"{pid}: missing {key}")
        if pid in seen or pid in taken:
            problems.append(f"{pid}: id already used")
        seen.add(pid)
        if p.get("group") not in GROUPS:
            problems.append(f"{pid}: unknown group {p.get('group')}")
        if not isinstance(p.get("confidence"), (int, float)) or not 0.5 <= p["confidence"] < 1:
            problems.append(f"{pid}: confidence must be at least 0.5 and under 1 (state the side you think is likelier)")
        try:
            date.fromisoformat(p.get("due", ""))
        except ValueError:
            problems.append(f"{pid}: due must be an ISO date")
        check = p.get("check") or {}
        if check.get("metric") not in METRICS:
            problems.append(f"{pid}: unknown metric {check.get('metric')}")
        if check.get("metric") not in ("prices.beat", "prices.drawdown") and check.get("op") not in OPS:
            problems.append(f"{pid}: unknown op {check.get('op')}")
        if p.get("unit") not in UNITS:
            problems.append(f"{pid}: unit must be one of {sorted(UNITS)}")
    if problems:
        raise SystemExit("Predictions rejected:\n  " + "\n  ".join(problems))


def sets() -> list[dict[str, Any]]:
    return [read_json(p) for p in sorted(SETS.glob("20[0-9][0-9]-[01][0-9].json"))]


def freeze(import_path: str, made_by: str, name: str | None = None) -> dict[str, Any]:
    """Write a new set from a JSON file. Refuses to touch a set that already exists."""
    raw = json.loads(Path(import_path).read_text())
    predictions = raw["predictions"] if isinstance(raw, dict) else raw
    name = name or f"{date.today():%Y-%m}"
    path = SETS / f"{name}.json"
    if path.exists():
        raise SystemExit(f"{path.relative_to(DATA.parent)} is frozen. Put new predictions in a new set with --name.")
    validate(predictions, {p["id"] for s in sets() for p in s["predictions"]})
    frozen = {
        "set": name,
        "made_at": now(),
        "made_by": made_by,
        "note": raw.get("note", "") if isinstance(raw, dict) else "",
        "sha256": "",
        "predictions": sorted(predictions, key=lambda p: (p["due"], p["id"])),
    }
    frozen["sha256"] = fingerprint(frozen["predictions"])
    write_json(path, frozen)
    print(f"Froze {len(predictions)} predictions as {path.relative_to(DATA.parent)} at {frozen['made_at']} (sha256 {frozen['sha256'][:12]})")
    return frozen


# ---------- observing the data ----------


@dataclass
class Obs:
    value: Any
    observed: str  # the day the number became known (a release, a filing or a close)
    source: str | None = None
    final: bool = True  # False for price checks still running: the value is how it stands so far


class Context:
    """What one checking pass knows: the committed data files, plus live fetches made once each."""

    def __init__(self, today: date):
        self.today = today
        self.supply = [read_json(p) for p in sorted(DATA.glob("20[0-9][0-9]-[01][0-9]/supply.json"))]
        self.demand = [read_json(p) for p in sorted(DATA.glob("20[0-9][0-9]-[01][0-9]/demand.json"))]
        self.waiting: dict[str, str] = {}
        self._live: dict[str, Any] = {}
        self._series: dict[str, dict[str, float]] = {}
        self._begin: date | None = None
        self._closes: Closes | None = None
        self.calendar: list[str] = []

    def live(self, name: str, fetch: Callable[[], Any]) -> Any:
        if name not in self._live:
            try:
                self._live[name] = fetch()
            except (Exception, SystemExit) as err:  # a missing SEC_USER_AGENT raises SystemExit
                self._live[name] = None
                self.waiting[name] = str(err).splitlines()[0][:200]
        return self._live[name]

    def closes(self, symbols: set[str], start: str) -> Closes:
        """Closes for `symbols` from shortly before `start`, fetching only what earlier checks didn't."""
        begin = date.fromisoformat(start) - timedelta(days=10)
        if self._begin is None or begin < self._begin:
            self._series, self._begin = {}, begin
        for symbol in sorted(symbols | {BENCHMARK}):
            if symbol in self._series:
                continue
            try:
                self._series[symbol] = prices.usd_history(symbol, self._begin, self.today)
            except Exception as err:
                self._series[symbol] = {}
                self.waiting[f"prices {symbol}"] = str(err)[:200]
        self._closes = Closes({k: v for k, v in self._series.items() if v})
        self.calendar = sorted(self._series.get(BENCHMARK, {}))
        return self._closes


def _korea(check: dict[str, Any], ctx: Context, due: bool) -> Obs | None:
    def match(m: dict[str, Any] | None) -> Obs | None:
        if m and m.get("period") == check["period"] and check["field"] in m:
            return Obs(m[check["field"]], m.get("released") or f"{_next_month(check['period'])}-01", m.get("source"))
        return None

    for s in ctx.supply:
        if found := match(s.get("memory")):
            return found
    if due:
        from .supply import korea
        return match(ctx.live("korea", korea.fetch))
    return None


def _taiwan(check: dict[str, Any], ctx: Context, due: bool) -> Obs | None:
    history: dict[str, float] = {}
    url = None
    for s in ctx.supply:
        series = (s.get("export_orders") or {}).get(check["series"]) or {}
        history.update(dict(series.get("history", [])))
        url = series.get("url") or url
    if check["period"] not in history and due:
        from .supply import taiwan
        fresh = ctx.live("taiwan", taiwan.fetch) or {}
        series = fresh.get(check["series"]) or {}
        history.update(dict(series.get("history", [])))
        url = series.get("url") or url
    year, month = check["period"].split("-")
    year_ago = f"{int(year) - 1}-{month}"
    if check["period"] in history and history.get(year_ago):
        return Obs(round(history[check["period"]] / history[year_ago] - 1, 4), f"{_next_month(check['period'])}-20", url)
    return None


def _ge_vernova(check: dict[str, Any], ctx: Context, due: bool) -> Obs | None:
    def match(row: dict[str, Any] | None) -> Obs | None:
        if row and row.get("company") == "GE Vernova" and row.get("quarter") == check["quarter"] and check["field"] in row:
            return Obs(row[check["field"]], row.get("filed") or ctx.today.isoformat(), row.get("source"))
        return None

    for s in ctx.supply:
        for row in s.get("gas_turbines", []):
            if found := match(row):
                return found
    if due:
        from .supply import turbines
        return match(ctx.live("ge_vernova", turbines.ge_vernova))
    return None


def _capex(check: dict[str, Any], ctx: Context, due: bool) -> Obs | None:
    """Total capex for the quarter ending `quarter_end` across `companies`, once all of them have filed it."""
    end = check["quarter_end"]
    found: dict[str, float] = {}
    known = ctx.today.isoformat()
    for d in ctx.demand:
        for ticker in check["companies"]:
            for q in d["companies"].get(ticker, {}).get("quarters", []):
                if q["end"] == end and ticker not in found:
                    found[ticker] = q["value"]
                    known = d["generated"]
    if len(found) < len(check["companies"]) and due:
        from . import demand, edgar
        for ticker in check["companies"]:
            if ticker in found:
                continue
            info = demand.HYPERSCALERS[ticker]
            facts = ctx.live(f"capex {ticker}", lambda info=info: edgar.concept(info["cik"], info["tag"])["units"]["USD"])
            for q in demand.quarterly(facts or []):
                if q["end"] == end:
                    found[ticker] = q["value"]
    if len(found) == len(check["companies"]):
        return Obs(sum(found.values()), known, "https://www.sec.gov/edgar/search/")
    return None


def _call(check: dict[str, Any], ctx: Context, due: bool) -> Obs | None:
    path = DATA / check["month"] / "bottleneck.json"
    if not path.exists():
        return None
    call = read_json(path)
    return Obs(call[check["field"]], call["generated"], f"data/{check['month']}/memo.md")


def _fund(check: dict[str, Any], ctx: Context, due: bool) -> Obs | None:
    cik = check.get("cik", SITUATIONAL_AWARENESS)
    path = DATA / "13f" / cik / f"{check['period']}.json"
    if not path.exists() and due:
        from . import clone
        ctx.live(f"13f {cik}", lambda: clone.backfill(cik))
    if not path.exists():
        return None
    book = read_json(path)
    share = sum(w["weight"] for w in book["weights"] if w.get("ticker") in check["tickers"])
    return Obs(round(share, 4), book["filed"], book.get("source"))


def _basket(closes: Closes, symbols: list[str], entry: str, day: str) -> float | None:
    """Buy-and-hold value of an equal-weight basket bought at the `entry` close, as a growth multiple."""
    ratios = []
    for s in symbols:
        a, b = closes.at(s, entry), closes.at(s, day)
        if not (a and b):
            return None
        ratios.append(b / a)
    return sum(ratios) / len(ratios)


def _window(check: dict[str, Any], ctx: Context) -> tuple[Closes, str | None, str | None, list[str]]:
    symbols = set(check.get("a", [])) | set(check.get("b", [])) | set(check.get("basket", []))
    closes = ctx.closes(symbols, check["start"])
    entry = next((d for d in ctx.calendar if d >= check["start"]), None)
    exit_ = next((d for d in ctx.calendar if d >= check["end"]), None)
    days = [d for d in ctx.calendar if entry and entry <= d <= (exit_ or ctx.calendar[-1])]
    return closes, entry, exit_, days


def _beat(check: dict[str, Any], ctx: Context, due: bool) -> Obs | None:
    """How far basket a finished ahead of basket b (in percentage points), bought at the first close on or after `start`."""
    closes, entry, exit_, days = _window(check, ctx)
    if not days:
        return None
    last = exit_ or days[-1]
    a, b = _basket(closes, check["a"], entry, last), _basket(closes, check["b"], entry, last)
    if a is None or b is None:
        return None
    return Obs(round(a - b, 4), last, "Yahoo Finance daily closes in US dollars", final=bool(exit_))


def _drawdown(check: dict[str, Any], ctx: Context, due: bool) -> Obs | None:
    """The worst fall from a running high since `start`. Final as soon as it reaches the threshold."""
    closes, entry, exit_, days = _window(check, ctx)
    if not days:
        return None
    values = [_basket(closes, check["basket"], entry, d) for d in days]
    worst, _, low = max_drawdown(values)
    hit = worst is not None and worst <= check["value"]
    day = days[low] if hit and low is not None else days[-1]
    return Obs(worst or 0.0, day, "Yahoo Finance daily closes in US dollars", final=hit or bool(exit_))


METRICS: dict[str, Callable[[dict[str, Any], Context, bool], Obs | None]] = {
    "korea": _korea,
    "taiwan": _taiwan,
    "ge_vernova": _ge_vernova,
    "capex": _capex,
    "call": _call,
    "fund": _fund,
    "prices.beat": _beat,
    "prices.drawdown": _drawdown,
}


def _next_month(period: str) -> str:
    year, month = map(int, period.split("-"))
    return f"{year + month // 12}-{month % 12 + 1:02d}"


# ---------- checking ----------


def outcome(check: dict[str, Any], value: Any) -> bool:
    if check["metric"] == "prices.beat":
        return value > 0
    if check["metric"] == "prices.drawdown":
        return value <= check["value"]
    return OPS[check["op"]](value, check["value"])


def check_one(p: dict[str, Any], ctx: Context, stamp: str) -> dict[str, Any]:
    due = ctx.today >= date.fromisoformat(p["due"])
    base = {"id": p["id"], "checked_at": stamp}
    obs = METRICS[p["check"]["metric"]](p["check"], ctx, due)
    if obs and obs.final:
        right = outcome(p["check"], obs.value)
        return {**base, "status": "right" if right else "wrong", "value": obs.value, "observed": obs.observed,
                "source": obs.source, "resolved_at": stamp}
    if ctx.today > date.fromisoformat(p["due"]) + timedelta(days=GRACE_DAYS):
        return {**base, "status": "void", "resolved_at": stamp, "note": f"No data to check it against by {ctx.today.isoformat()}."}
    out = {**base, "status": "open"}
    if obs:  # a price check still running: how it stands so far
        out.update(so_far=obs.value, observed=obs.observed, leaning="right" if outcome(p["check"], obs.value) else "wrong")
    return out


def summarize(predictions: list[dict[str, Any]], results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Counts, the hit rate and a Brier score over the resolved predictions (void ones don't count)."""
    by_status = {s: 0 for s in ("right", "wrong", "open", "void")}
    scored = []
    for p in predictions:
        r = results.get(p["id"], {"status": "open"})
        by_status[r["status"]] += 1
        if r["status"] in ("right", "wrong"):
            scored.append((p["confidence"], 1.0 if r["status"] == "right" else 0.0))
    resolved = len(scored)
    return {
        **by_status,
        "total": len(predictions),
        "resolved": resolved,
        "hit_rate": round(by_status["right"] / resolved, 4) if resolved else None,
        "expected_right": round(sum(c for c, _ in scored), 2) if resolved else None,
        "brier": round(sum((c - o) ** 2 for c, o in scored) / resolved, 4) if resolved else None,
        "mean_confidence": round(sum(p["confidence"] for p in predictions) / len(predictions), 4) if predictions else None,
    }


def verify(s: dict[str, Any]) -> bool:
    return fingerprint(s["predictions"]) == s["sha256"]


def run(today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    stamp = now()
    all_sets = sets()
    previous = read_json(RESULTS)["results"] if RESULTS.exists() else {}
    ctx = Context(today)
    results: dict[str, dict[str, Any]] = {}
    for s in all_sets:
        for p in s["predictions"]:
            old = previous.get(p["id"])
            if old and old["status"] in ("right", "wrong", "void"):
                results[p["id"]] = old  # settled results never change
            else:
                results[p["id"]] = check_one(p, ctx, stamp)
    everything = [p for s in all_sets for p in s["predictions"]]
    out = {
        "checked_at": stamp,
        "sets": [{"set": s["set"], "made_at": s["made_at"], "made_by": s["made_by"], "sha256": s["sha256"], "intact": verify(s),
                  "summary": summarize(s["predictions"], results)} for s in all_sets],
        "summary": summarize(everything, results),
        "waiting": ctx.waiting,
        "results": results,
    }
    write_json(RESULTS, out)
    t = out["summary"]
    print(f"Predictions checked at {stamp}: {t['right']} right, {t['wrong']} wrong, {t['open']} open, {t['void']} void")
    for s in out["sets"]:
        if not s["intact"]:
            print(f"  WARNING: set {s['set']} no longer matches its sha256; the file was edited after it was frozen")
    newly = [r for r in results.values() if r.get("resolved_at") == stamp]
    for r in newly:
        print(f"  {r['id']}: {r['status']} ({r.get('value', r.get('note'))})")
    for name, why in ctx.waiting.items():
        print(f"  couldn't fetch {name}: {why}")
    print(f"  wrote {RESULTS.relative_to(DATA.parent)}")
    return out
