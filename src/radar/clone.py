"""Stage 1: clone a fund's long-stock book from its latest 13F-HR."""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from datetime import date
from typing import Any

from . import edgar, openfigi, prices
from .config import DATA, PRIVATE, month_key
from .http import get, get_json
from .store import latest, read_json, write_json, write_text

SITUATIONAL_AWARENESS = "0002045724"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_info_table(xml: bytes) -> list[dict[str, Any]]:
    """One dict per infoTable row. Values are in dollars (13F switched from thousands in 2023)."""
    rows = []
    for node in ET.fromstring(xml).iter():
        if _local(node.tag) != "infoTable":
            continue
        fields = {_local(child.tag): child.text.strip() for child in node.iter() if child.text and child.text.strip()}
        rows.append(
            {
                "name": fields["nameOfIssuer"],
                "title": fields.get("titleOfClass", ""),
                "cusip": fields["cusip"].upper(),
                "value": int(float(fields["value"])),
                "shares": int(float(fields["sshPrnamt"])),
                "share_type": fields.get("sshPrnamtType", "SH"),
                "put_call": fields["putCall"].title() if fields.get("putCall") else None,
            }
        )
    return rows


def aggregate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge rows that share a CUSIP and put/call flag. Funds split one holding across managers."""
    merged: dict[tuple, dict[str, Any]] = {}
    for row in rows:
        key = (row["cusip"], row["put_call"])
        if key in merged:
            merged[key]["value"] += row["value"]
            merged[key]["shares"] += row["shares"]
        else:
            merged[key] = dict(row)
    return sorted(merged.values(), key=lambda r: -r["value"])


def weights(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Weights across the long stock only. Calls and puts are dropped, as in the video's prompt, and so are
    convertible notes, which a 13F lists by principal amount (PRN) instead of shares."""
    stock = [row for row in rows if row["put_call"] is None and row.get("share_type", "SH") == "SH"]
    total = sum(row["value"] for row in stock)
    return [
        {
            "ticker": row.get("ticker"),
            "name": row["name"],
            "cusip": row["cusip"],
            "value": row["value"],
            "shares": row["shares"],
            "weight": round(row["value"] / total, 6),
        }
        for row in stock
    ]


def _info_table_url(cik: str, accession: str) -> str:
    listing = get_json(edgar.archive_url(cik, accession, "index.json"), sec=True)
    names = [item["name"] for item in listing["directory"]["item"]]
    tables = [n for n in names if n.lower().endswith(".xml") and n.lower() != "primary_doc.xml"]
    if not tables:
        raise SystemExit(f"No information table in filing {accession}")
    return edgar.archive_url(cik, accession, tables[0])


def build_book(cik: str = SITUATIONAL_AWARENESS, filing: dict[str, Any] | None = None) -> dict[str, Any]:
    """The long-stock book from one 13F-HR, the latest unless `filing` names another."""
    all_filings = edgar.filings(cik)
    filing = filing or next((f for f in all_filings if f["form"] == "13F-HR"), None)
    if filing is None:
        raise SystemExit(f"No 13F-HR found for CIK {cik}")
    accession = filing["accessionNumber"]
    source = _info_table_url(cik, accession)
    rows = aggregate(parse_info_table(get(source, sec=True, ttl_hours=24 * 30)))
    mapping = openfigi.tickers([r["cusip"] for r in rows])
    for row in rows:
        row["ticker"] = mapping.get(row["cusip"])
    total = sum(r["value"] for r in rows)
    book = weights(rows)
    stock_value = sum(w["value"] for w in book)
    return {
        "fund": edgar.submissions(cik)["name"],
        "cik": cik,
        "accession": accession,
        "filed": filing["filingDate"],
        "period": filing["reportDate"],
        "source": source,
        "total_value": total,
        "stock_value": stock_value,
        "stock_share": round(stock_value / total, 6) if total else None,
        "unmapped": [w["name"] for w in book if not w["ticker"]],
        "options": [r for r in rows if r["put_call"]],
        "amendments": [
            f["accessionNumber"]
            for f in all_filings
            if f["form"] == "13F-HR/A" and f["reportDate"] == filing["reportDate"]
        ],
        "weights": book,
    }


def order_list(book: dict[str, Any], account_value: float) -> dict[str, Any]:
    """Whole-share orders that copy the book's weights. Written to private/ and never sent anywhere."""
    orders = []
    invested = 0.0
    for w in book["weights"]:
        price = prices.last_price(w["ticker"]) if w["ticker"] else None
        stale = price is None and w["shares"] > 0
        if stale:
            price = w["value"] / w["shares"]  # the 13F's own quarter-end price
        target = w["weight"] * account_value
        shares = math.floor(target / price) if price else 0
        invested += shares * (price or 0)
        orders.append(
            {
                "ticker": w["ticker"] or w["name"],
                "weight": w["weight"],
                "target_value": round(target, 2),
                "price": round(price, 4) if price else None,
                "price_is_13f": stale,
                "shares": shares,
                "cost": round(shares * (price or 0), 2),
            }
        )
    return {
        "account_value": account_value,
        "invested": round(invested, 2),
        "cash_left": round(account_value - invested, 2),
        "book_period": book["period"],
        "orders": orders,
    }


def order_list_markdown(orders: dict[str, Any], book: dict[str, Any]) -> str:
    lines = [
        f"# Order list, {date.today():%Y-%m-%d}",
        "",
        f"Copies the long-stock weights of {book['fund']}'s 13F for {book['period']} (filed {book['filed']})"
        f" onto ${orders['account_value']:,.0f}. Nothing here gets sent to a broker.",
        "",
        "| Ticker | Weight | Target | Price | Shares | Cost |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for o in orders["orders"]:
        price = f"${o['price']:,.2f}" + (" (13F)" if o["price_is_13f"] else "") if o["price"] else "n/a"
        lines.append(
            f"| {o['ticker']} | {o['weight']:.1%} | ${o['target_value']:,.0f} | {price} | {o['shares']:,} | ${o['cost']:,.0f} |"
        )
    lines += ["", f"Invested ${orders['invested']:,.0f}, cash left ${orders['cash_left']:,.0f}."]
    return "\n".join(lines)


def latest_nav() -> float | None:
    path = latest(PRIVATE / "ibkr", "positions-*.json")
    return read_json(path).get("nav") if path else None


def backfill(cik: str = SITUATIONAL_AWARENESS, since: str | None = None) -> list[str]:
    """Save each original 13F-HR filed since `since` that data/ doesn't have yet.

    The picks tracker replays these in filing order, so it needs the book the fund had
    published before January as well as every one since. Defaults to October of last year.
    """
    since = since or f"{date.today().year - 1}-10-01"
    saved = []
    for filing in edgar.filings(cik):
        path = DATA / "13f" / cik / f"{filing['reportDate']}.json"
        if filing["form"] != "13F-HR" or filing["filingDate"] < since or path.exists():
            continue
        write_json(path, build_book(cik, filing))
        saved.append(filing["reportDate"])
    return saved


def run(cik: str = SITUATIONAL_AWARENESS, account_value: float | None = None) -> dict[str, Any]:
    book = build_book(cik)
    path = write_json(DATA / "13f" / cik / f"{book['period']}.json", book)
    if earlier := backfill(cik):
        print(f"  saved earlier books for the tracker: {', '.join(earlier)}")
    top = ", ".join(f"{w['ticker'] or w['name']} {w['weight']:.1%}" for w in book["weights"][:3])
    print(f"13F {book['period']} (filed {book['filed']}): {len(book['weights'])} stock positions, "
          f"${book['stock_value'] / 1e9:.1f}B, {book['stock_share']:.1%} of reported value. Top: {top}")
    print(f"  wrote {path.relative_to(DATA.parent)}")
    if book["unmapped"]:
        print(f"  no ticker for: {', '.join(book['unmapped'])}")

    account_value = account_value or latest_nav()
    if account_value:
        orders = order_list(book, account_value)
        out = PRIVATE / month_key() / "order-list"
        write_json(out.with_suffix(".json"), orders)
        write_text(out.with_suffix(".md"), order_list_markdown(orders, book))
        print(f"  order list for ${account_value:,.0f} in {out.with_suffix('.md').relative_to(PRIVATE.parent)}")
    else:
        print("  no account value yet, so no order list (pass --account-value or run `radar ibkr` first)")
    return book
