"""SEC EDGAR: filing lists, filing documents, XBRL facts and plain text from HTML exhibits."""

from __future__ import annotations

import html
import re
from typing import Any

from .http import get, get_json

WWW = "https://www.sec.gov"


def cik10(cik: str | int) -> str:
    return f"{int(cik):010d}"


def submissions(cik: str | int) -> dict[str, Any]:
    return get_json(f"https://data.sec.gov/submissions/CIK{cik10(cik)}.json", sec=True, ttl_hours=6)


def filings(cik: str | int) -> list[dict[str, Any]]:
    """Recent filings, newest first, one dict per filing."""
    recent = submissions(cik)["filings"]["recent"]
    return [dict(zip(recent, row)) for row in zip(*recent.values())]


def archive_url(cik: str | int, accession: str, name: str = "") -> str:
    return f"{WWW}/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/{name}"


def documents(cik: str | int, accession: str) -> list[dict[str, str]]:
    """The document table on a filing's index page: description, file name, type and URL."""
    page = get(archive_url(cik, accession, f"{accession}-index.htm"), sec=True).decode("utf-8", "replace")
    rows = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S | re.I):
        cells = [strip_tags(cell) for cell in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S | re.I)]
        link = re.search(r'href="([^"]+)"', row)
        if len(cells) >= 4 and link:
            href = link.group(1).replace("/ix?doc=", "")
            rows.append({"description": cells[1], "document": cells[2], "type": cells[3], "url": WWW + href})
    return rows


def latest_earnings_release(cik: str | int, max_filings: int = 3) -> dict[str, str] | None:
    """The press release exhibit of the newest 8-K filed under Item 2.02 (results of operations).

    Most filers type it EX-99.1; some (GE Vernova) use plain EX-99.
    """
    candidates = [f for f in filings(cik) if f["form"] == "8-K" and "2.02" in (f.get("items") or "")]
    for filing in candidates[:max_filings]:
        exhibits = [d for d in documents(cik, filing["accessionNumber"]) if d["type"].upper() in ("EX-99.1", "EX-99")]
        exhibits.sort(key=lambda d: d["type"].upper() != "EX-99.1")
        if exhibits:
            return {"filed": filing["filingDate"], "accession": filing["accessionNumber"], "url": exhibits[0]["url"]}
    return None


def concept(cik: str | int, tag: str, taxonomy: str = "us-gaap") -> dict[str, Any]:
    url = f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik10(cik)}/{taxonomy}/{tag}.json"
    return get_json(url, sec=True, ttl_hours=6)


def html_to_text(raw: bytes | str) -> str:
    text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
    text = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", text)
    text = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h[1-6]|table)>", "\n", text)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text)).replace("\xa0", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    return re.sub(r" *\n[\n ]*", "\n", text).strip()


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\"“(])|\n", text)
    return [part.strip() for part in parts if part.strip()]


def strip_tags(fragment: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", fragment)).replace("\xa0", " ").strip()
