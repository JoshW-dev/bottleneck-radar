"""Prices from Yahoo's chart endpoint (no key): a last price for the never-sent order list, and daily
closes in US dollars for the picks tracker."""

from __future__ import annotations

from bisect import bisect_right
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from urllib.parse import quote

from .http import get_json

CHART = "https://query1.finance.yahoo.com/v8/finance/chart/"
HEADERS = {"User-Agent": "Mozilla/5.0"}  # Yahoo answers 429 to fuller browser strings


def yahoo_symbol(ticker: str) -> str:
    """US tickers from filings mark share classes with / or . (BRK/B); Yahoo wants BRK-B."""
    return ticker.replace("/", "-").replace(".", "-")


def last_price(ticker: str) -> float | None:
    try:
        data = get_json(CHART + yahoo_symbol(ticker), params={"range": "5d", "interval": "1d"}, headers=HEADERS, ttl_hours=6)
        return float(data["chart"]["result"][0]["meta"]["regularMarketPrice"])
    except Exception:
        return None


def history(symbol: str, start: date, end: date | None = None) -> dict[str, Any]:
    """Daily closes adjusted for splits and dividends, keyed by the exchange's own date.

    A bar for a session that hasn't closed yet is dropped, so every value is a real close.
    """
    end = end or date.today()
    params = {
        "period1": int(datetime.combine(start, time(), timezone.utc).timestamp()),
        "period2": int(datetime.combine(end + timedelta(days=1), time(), timezone.utc).timestamp()),
        "interval": "1d",
        "events": "div,split",
        "includeAdjustedClose": "true",
    }
    result = get_json(CHART + quote(symbol), params=params, headers=HEADERS, ttl_hours=4)["chart"]["result"][0]
    meta = result["meta"]
    offset = meta.get("gmtoffset", 0)
    indicators = result.get("indicators", {})
    values = (indicators.get("adjclose") or [{}])[0].get("adjclose") or indicators["quote"][0]["close"]
    closes = {
        datetime.fromtimestamp(ts + offset, timezone.utc).date().isoformat(): float(v)
        for ts, v in zip(result.get("timestamp") or [], values)
        if v is not None
    }
    session = (meta.get("currentTradingPeriod") or {}).get("regular") or {}
    now = datetime.now(timezone.utc).timestamp()
    if session and session.get("start", 0) <= now < session.get("end", 0):
        today = datetime.fromtimestamp(now + offset, timezone.utc).date().isoformat()
        closes.pop(today, None)
    return {"symbol": symbol, "currency": meta.get("currency") or "USD", "closes": closes}


def asof(series: dict[str, float], days: list[str], day: str) -> float | None:
    """The last value on or before `day`. `days` is `series`' keys, sorted."""
    i = bisect_right(days, day)
    return series[days[i - 1]] if i else None


def to_usd(closes: dict[str, float], fx: dict[str, float], scale: float = 1.0) -> dict[str, float]:
    """Convert local closes with a {CCY}USD rate series (dollars per unit), using the rate on or before each day."""
    fx_days = sorted(fx)
    out = {}
    for day, value in closes.items():
        rate = asof(fx, fx_days, day)
        if rate:
            out[day] = value * rate * scale
    return out


def usd_history(symbol: str, start: date, end: date | None = None) -> dict[str, float]:
    """Daily closes in US dollars. Foreign listings are converted at Yahoo's daily {CCY}USD rate."""
    h = history(symbol, start, end)
    currency, scale = h["currency"], 1.0
    if currency == "USD":
        return h["closes"]
    if currency == "GBp":  # London quotes in pence
        currency, scale = "GBP", 0.01
    return to_usd(h["closes"], history(f"{currency}USD=X", start, end)["closes"], scale)
