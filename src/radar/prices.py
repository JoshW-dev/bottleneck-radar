"""Recent prices from Yahoo's chart endpoint (no key). Only used to size the never-sent order list."""

from __future__ import annotations

from .http import get_json


def last_price(ticker: str) -> float | None:
    symbol = ticker.replace("/", "-").replace(".", "-")
    try:
        data = get_json(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
            params={"range": "5d", "interval": "1d"},
            headers={"User-Agent": "Mozilla/5.0"},  # Yahoo answers 429 to fuller browser strings
            ttl_hours=6,
        )
        return float(data["chart"]["result"][0]["meta"]["regularMarketPrice"])
    except Exception:
        return None
