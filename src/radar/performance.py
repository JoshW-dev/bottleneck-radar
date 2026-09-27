"""How the picks, the 13F clone and two benchmarks have done this year, in US dollars.

Every portfolio here buys at the first close after the thing it copies was published: a 13F on the
trading day after its filing date, a set of picks on the trading day after its call. Before the
first call, the picks line is hindsight (nobody had picked those stocks yet), and the page draws
that stretch dashed. Foreign listings use their last close on or before each US trading day,
converted at that day's exchange rate. Closes are adjusted for dividends and splits.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from . import picks as picks_stage
from . import prices
from .clone import SITUATIONAL_AWARENESS
from .config import DATA
from .store import read_json, write_json

BENCHMARK = "SPY"
OUT = DATA / "performance.json"


class Closes:
    """US-dollar closes per symbol, looked up as of a day (the last close on or before it)."""

    def __init__(self, series: dict[str, dict[str, float]]):
        self.series = series
        self.days = {symbol: sorted(values) for symbol, values in series.items()}

    def at(self, symbol: str, day: str | None) -> float | None:
        if day is None or symbol not in self.series:
            return None
        return prices.asof(self.series[symbol], self.days[symbol], day)

    def change(self, symbol: str, start: str | None, end: str) -> float | None:
        a, b = self.at(symbol, start), self.at(symbol, end)
        return round(b / a - 1, 4) if a and b else None


def next_day(iso: str) -> str:
    return (date.fromisoformat(iso) + timedelta(days=1)).isoformat()


def simulate(
    books: list[dict[str, Any]], closes: Closes, days: list[str], start_value: float = 100.0
) -> tuple[list[float | None], list[dict[str, Any]]]:
    """Value on each day of a portfolio that switches to each book at the first close on or after its trade day.

    A book is {"trade": day, "weights": {symbol: weight}, "tag": label}. Symbols without a price that
    day are skipped and the rest scaled up; each fill records the share of the book that could be
    bought. Only the latest book already in force on the first day is used. Days before the first
    book are None.
    """
    books = sorted(books, key=lambda b: b["trade"])
    in_force = [b for b in books if b["trade"] <= days[0]][-1:]
    books = in_force + [b for b in books if b["trade"] > days[0]]
    values: list[float | None] = []
    fills: list[dict[str, Any]] = []
    units: dict[str, float] = {}
    value, k = start_value, 0
    for day in days:
        if units:
            value = sum(n * closes.at(s, day) for s, n in units.items())
        while k < len(books) and books[k]["trade"] <= day:
            weights = books[k]["weights"]
            priced = {s: w for s, w in weights.items() if w > 0 and closes.at(s, day)}
            total = sum(priced.values())
            if total:
                units = {s: value * w / total / closes.at(s, day) for s, w in priced.items()}
            fills.append({
                "tag": books[k].get("tag"),
                "day": day,
                "bought": round(total / sum(weights.values()), 4) if weights else 0.0,
                "missing": sorted(s for s, w in weights.items() if w > 0 and s not in priced),
            })
            k += 1
        values.append(round(value, 4) if units else None)
    return values, fills


def _weights(basket: list[dict[str, Any]]) -> dict[str, float]:
    return {p["quote"]: p["weight"] for p in basket}


def _clone_weights(book: dict[str, Any]) -> dict[str, float]:
    """Yahoo symbols for a 13F book. Positions without a ticker stay in, unpriceable, so the fill reports them."""
    out: dict[str, float] = {}
    for w in book["weights"]:
        symbol = prices.yahoo_symbol(w["ticker"]) if w.get("ticker") else f"{w['name'].title()} (no ticker)"
        out[symbol] = out.get(symbol, 0.0) + w["weight"]
    return out


def max_drawdown(values: list[float | None]) -> tuple[float | None, int | None, int | None]:
    """The worst fall from a running peak, with the index of that peak and of the low."""
    worst, peak_i, worst_at = 0.0, None, (None, None)
    for i, v in enumerate(values):
        if v is None:
            continue
        if peak_i is None or v > values[peak_i]:
            peak_i = i
        drop = v / values[peak_i] - 1
        if drop < worst:
            worst, worst_at = drop, (peak_i, i)
    return (round(worst, 4) if peak_i is not None else None), *worst_at


def _growth(values: list[float | None], start: int | None) -> float | None:
    if start is None or not values or values[start] is None or values[-1] is None:
        return None
    return round(values[-1] / values[start] - 1, 4)


def compute(today: date | None = None, cik: str = SITUATIONAL_AWARENESS) -> dict[str, Any]:
    today = today or date.today()
    year = today.year
    snaps = picks_stage.snapshots()
    latest = snaps[-1] if snaps else None
    filings = [read_json(p) for p in sorted((DATA / "13f" / cik).glob("*.json"))]
    clone_books = [{"trade": next_day(b["filed"]), "weights": _clone_weights(b), "tag": b["period"]} for b in filings]

    symbols = {BENCHMARK}
    for snap in snaps:
        symbols |= {p["quote"] for p in snap["picks"]}
    if latest:
        symbols |= {p["quote"] for p in latest["consensus"]}
    for book in clone_books:
        symbols |= set(book["weights"])

    series: dict[str, dict[str, float]] = {}
    failed: list[str] = []
    for symbol in sorted(symbols):
        if symbol.endswith("(no ticker)"):
            continue
        try:
            series[symbol] = prices.usd_history(symbol, date(year - 1, 12, 1), today)
        except Exception:  # a delisted or renamed symbol shouldn't stop the rest
            failed.append(symbol)
    if not series.get(BENCHMARK):
        raise SystemExit("Yahoo returned no S&P 500 prices, so there's no trading calendar to track against. Try again later.")
    closes = Closes(series)
    calendar = sorted(series[BENCHMARK])
    base = max(d for d in calendar if d < f"{year}-01-01")
    days = [d for d in calendar if d >= base]
    last = days[-1]

    out: dict[str, Any] = {
        "generated": today.isoformat(),
        "as_of": last,
        "year": year,
        "base": base,
        "days": days,
        "series": {},
        "picks": None,
        "consensus": None,
        "clone": None,
        "failed": failed,
    }

    sp500, _ = simulate([{"trade": base, "weights": {BENCHMARK: 1.0}}], closes, days)
    clone, clone_fills = simulate(clone_books, closes, days)
    series_out = {"sp500": {"label": "S&P 500", "values": sp500}, "clone": {"label": "13F clone", "values": clone}}
    live_index = None

    if latest:
        first = snaps[0]
        hindsight, _ = simulate([{"trade": base, "weights": _weights(first["picks"])}], closes, days)
        live_books = [{"trade": next_day(s["published"]), "weights": _weights(s["picks"]), "tag": s["month"]} for s in snaps]
        live_index = next((i for i, d in enumerate(days) if d >= next_day(first["published"])), None)
        if live_index is None:
            values = hindsight
        elif live_index == 0:
            values, _ = simulate(live_books, closes, days)
        else:
            live, _ = simulate(live_books, closes, days[live_index:], start_value=hindsight[live_index])
            values = hindsight[:live_index] + live
        consensus, _ = simulate([{"trade": base, "weights": _weights(latest["consensus"])}], closes, days)
        basket, _ = simulate([{"trade": base, "weights": _weights(latest["picks"])}], closes, days)
        series_out = {
            "picks": {"label": "Picks", "values": values},
            "clone": series_out["clone"],
            "consensus": {"label": "Consensus AI", "values": consensus},
            "sp500": series_out["sp500"],
        }
        entry = next((d for d in days if d >= next_day(latest["published"])), None)

        def rows(basket_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
            return [
                {**p, "ytd": closes.change(p["quote"], base, last), "since_pick": closes.change(p["quote"], entry, last) if entry else None}
                for p in basket_rows
            ]

        out["picks"] = {
            "month": latest["month"],
            "published": latest["published"],
            "bottleneck": latest["bottleneck"],
            "label": latest["label"],
            "headline": latest["headline"],
            "rule": latest["rule"],
            "first_published": first["published"],
            "entry": entry,
            "live_from": days[live_index] if live_index is not None else None,
            "basket_ytd": _growth(basket, 0),
            "rows": rows(latest["picks"]),
        }
        out["consensus"] = {"rows": rows(latest["consensus"])}

    for key, s in series_out.items():
        s["ytd"] = _growth(s["values"], 0)
        s["since_call"] = _growth(s["values"], live_index)
        drop, peak, low = max_drawdown(s["values"])
        s["max_drawdown"] = {"change": drop, "peak": days[peak] if peak is not None else None, "low": days[low] if low is not None else None}
        s["values"] = [None if v is None else round(v, 2) for v in s["values"]]
    out["series"] = series_out

    by_period = {b["period"]: b for b in filings}
    out["clone"] = {
        "fund": filings[-1]["fund"] if filings else None,
        "books": [
            {
                "period": f["tag"],
                "filed": by_period[f["tag"]]["filed"],
                "bought_on": f["day"],
                "positions": len(by_period[f["tag"]]["weights"]),
                "bought": f["bought"],
                "missing": f["missing"],
            }
            for f in clone_fills
        ],
    }
    return out


def run() -> dict[str, Any]:
    result = compute()
    write_json(OUT, result)
    s = result["series"]
    summary = ", ".join(f"{v['label']} {v['ytd']:+.1%}" for v in s.values() if v.get("ytd") is not None)
    print(f"{result['year']} so far, to the {result['as_of']} close: {summary}")
    if p := result["picks"]:
        if p["live_from"]:
            print(f"  live since {p['live_from']}: picks {s['picks']['since_call']:+.1%}")
        else:
            print(f"  picks published {p['published']}; the live record starts at the first close after that")
    if result["failed"]:
        print(f"  no prices for: {', '.join(result['failed'])}")
    print(f"  wrote {OUT.relative_to(DATA.parent)}")
    return result
