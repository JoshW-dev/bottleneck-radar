"""Taiwan export orders from the Ministry of Economic Affairs open-data CSVs.

Values are US$ millions per month, released around the 20th for the prior month.
"""

from __future__ import annotations

import csv
import io
from typing import Any

from ..http import get

SERIES = {
    "total": "https://service.moea.gov.tw/EE520/opendata/b.csv",
    "electronics": "https://service.moea.gov.tw/EE520/opendata/經濟部統計處_外銷訂單_電子產品.csv",
    "ict": "https://service.moea.gov.tw/EE520/opendata/經濟部統計處_外銷訂單_資訊通訊產品.csv",
}


def roc_period(code: str) -> str:
    """'11508' -> '2026-08'. Taiwan numbers years from 1912, so ROC year 115 is 2026."""
    code = code.strip()
    return f"{int(code[:-2]) + 1911:04d}-{int(code[-2:]):02d}"


def parse_csv(raw: bytes) -> list[tuple[str, float]]:
    """(period, US$ millions) pairs, oldest first.

    The total file has one USD value column. The product files add a product
    column and repeat each month in USD and NT$, marked in the first column.
    """
    rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
    header, body = rows[0], rows[1:]
    period_col = next(i for i, name in enumerate(header) if "資料期" in name)
    value_col = next(i for i, name in enumerate(header) if "統計值" in name)
    if any("美元" in r[0] for r in body if r):
        body = [r for r in body if r and "美元" in r[0]]
    out = [
        (roc_period(r[period_col]), float(r[value_col].replace(",", "")))
        for r in body
        if len(r) > value_col and r[period_col].strip().isdigit()
    ]
    return sorted(out)


def summarize(series: list[tuple[str, float]]) -> dict[str, Any]:
    values = dict(series)
    period, latest = series[-1]
    year, month = map(int, period.split("-"))
    year_ago = values.get(f"{year - 1:04d}-{month:02d}")
    last3 = [v for _, v in series[-3:]]
    prior3 = [values.get(f"{int(p[:4]) - 1:04d}{p[4:]}") for p, _ in series[-3:]]
    out: dict[str, Any] = {"period": period, "usd_millions": latest}
    if year_ago:
        out["yoy"] = latest / year_ago - 1
    if all(prior3):
        out["yoy_3m"] = sum(last3) / sum(prior3) - 1
    return out


def fetch() -> dict[str, Any]:
    result: dict[str, Any] = {"source": "Taiwan Ministry of Economic Affairs, Department of Statistics (data.gov.tw)"}
    for name, url in SERIES.items():
        result[name] = {**summarize(parse_csv(get(url, browser=True, ttl_hours=24))), "url": url}
    return result
