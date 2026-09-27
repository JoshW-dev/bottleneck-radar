"""Positions from an IBKR Flex Query through the Flex Web Service.

A Flex token can only pull reports, so this path has no way to place an order.
Setup is in the README. Output goes to private/ibkr/, which git ignores.
"""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from datetime import date
from typing import Any

import httpx

from .config import PRIVATE, require_env
from .http import get
from .store import write_json

SEND_URL = "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/SendRequest"
IN_PROGRESS = "1019"  # "Statement generation in progress. Please try again shortly."
HINT = "Create a Flex token and an Open Positions query in IBKR's Client Portal (see README)."


class FlexError(RuntimeError):
    pass


def _get(url: str, params: dict[str, str]) -> ET.Element:
    try:
        return ET.fromstring(get(url, params=params, ttl_hours=0))
    except httpx.HTTPStatusError as exc:  # re-raise without the request, which carries the token
        raise FlexError(f"IBKR returned HTTP {exc.response.status_code}") from None


def fetch_statement(token: str, query_id: str, attempts: int = 20, wait: float = 3.0) -> bytes:
    root = _get(SEND_URL, {"t": token, "q": query_id, "v": "3"})
    if root.findtext("Status") != "Success":
        raise FlexError(f"{root.findtext('ErrorCode')}: {root.findtext('ErrorMessage')}")
    reference, url = root.findtext("ReferenceCode"), root.findtext("Url")
    for _ in range(attempts):
        time.sleep(wait)
        body = get(url, params={"t": token, "q": reference, "v": "3"}, ttl_hours=0)
        root = ET.fromstring(body)
        if root.tag == "FlexQueryResponse":
            return body
        code = root.findtext("ErrorCode") or ""
        message = root.findtext("ErrorMessage") or (root[0].text if len(root) else "") or ""
        if code == IN_PROGRESS or "in progress" in message.lower():
            continue
        raise FlexError(f"{code}: {message}")
    raise FlexError(f"statement still not ready after {attempts} tries")


def _num(value: str | None) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None


def mask(account: str | None) -> str | None:
    return account and account[:1] + "*" * max(len(account) - 4, 0) + account[-3:]


def parse_statement(xml: bytes) -> dict[str, Any]:
    root = ET.fromstring(xml)
    statement = root.find(".//FlexStatement")
    if statement is None:
        raise FlexError("no FlexStatement in the response")
    positions = []
    for node in root.iter("OpenPosition"):
        a = node.attrib
        if a.get("levelOfDetail", "SUMMARY").upper() != "SUMMARY":
            continue  # lot-level rows repeat the summary
        value = _num(a.get("positionValue"))
        fx = _num(a.get("fxRateToBase")) or 1.0
        positions.append(
            {
                "symbol": a.get("symbol"),
                "underlying": a.get("underlyingSymbol") or None,
                "description": a.get("description"),
                "asset_class": a.get("assetCategory"),
                "currency": a.get("currency"),
                "exchange": a.get("listingExchange"),
                "isin": a.get("isin") or None,
                "quantity": _num(a.get("position")),
                "mark_price": _num(a.get("markPrice")),
                "value": value,
                "value_base": value * fx if value is not None else None,
            }
        )
    nav = None
    if summaries := list(root.iter("EquitySummaryByReportDateInBase")):
        nav = _num(summaries[-1].attrib.get("total"))
    if nav is None and (change := root.find(".//ChangeInNAV")) is not None:
        nav = _num(change.attrib.get("endingValue"))
    return {
        "account": mask(statement.attrib.get("accountId")),
        "period_end": statement.attrib.get("toDate"),
        "generated": statement.attrib.get("whenGenerated"),
        "nav": nav,
        "positions": positions,
    }


def run() -> dict[str, Any]:
    token = require_env("IBKR_FLEX_TOKEN", HINT)
    query_id = require_env("IBKR_FLEX_QUERY_ID", HINT)
    statement = parse_statement(fetch_statement(token, query_id))
    path = write_json(PRIVATE / "ibkr" / f"positions-{date.today():%Y-%m-%d}.json", statement)
    nav = f"${statement['nav']:,.0f}" if statement["nav"] else "unknown (add Net Asset Value to the query)"
    print(f"IBKR {statement['account']}: {len(statement['positions'])} positions, NAV {nav}")
    print(f"  wrote {path.relative_to(PRIVATE.parent)}")
    return statement
