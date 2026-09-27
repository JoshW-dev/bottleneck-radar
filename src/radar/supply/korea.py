"""Korean memory chip exports from the trade ministry's monthly release.

MOTIR (the ministry was MOTIE until 2026) publishes "수출입동향" (export-import
trends) on the 1st of each month. The English version has no memory split, so
this reads the Korean PDF, where one line gives memory and system chip exports.
Figures are in 억 달러 (units of US$100 million).
"""

from __future__ import annotations

import html
import io
import re
from typing import Any

from pypdf import PdfReader

from ..http import get

SITE = "https://www.motir.go.kr"
BOARD = f"{SITE}/kor/article/ATCL3f49a5a8c"
EOK = 100_000_000  # 억 = 10^8
NUM = r"([\d.,]+)"
PCT = r"\(\s*([+\-△]?[\d.,]+)\s*%?\s*\)"

TITLE = re.compile(r"(?:(\d{4})년\s*)?(\d{1,2})월.*수출입\s*동향")
MEMORY = re.compile(rf"메모리\s*/\s*시스템\s*반도체\s*수출액\s*:\s*{NUM}\s*→\s*{NUM}\s*{PCT}\s*/\s*{NUM}\s*→\s*{NUM}\s*{PCT}")
CHIPS = re.compile(
    rf"반도체\s*수출액\s*/\s*증감률\s*\(\s*억\s*달러\s*\)\s*:\s*\(\s*[’']?(\d{{2}})\.(\d{{1,2}})\.?\s*\)\s*{NUM}\s*{PCT}"
    rf"\s*→\s*\(\s*[’']?(\d{{2}})\.(\d{{1,2}})\.?\s*\)\s*{NUM}\s*{PCT}"
)
PRICE = re.compile(rf"(DDR5\s*16Gb|NAND\s*128G)b?\s*{NUM}\s*→\s*{NUM}\s*→\s*{NUM}\s*{PCT}")


def _num(text: str) -> float:
    return float(text.replace(",", ""))


def _pct(text: str) -> float:
    """'+290.2' -> 2.902 and '△5' -> -0.05 (Korean statistics mark declines with △)."""
    return -_num(text.lstrip("△")) / 100 if text.startswith("△") else _num(text.lstrip("+")) / 100


def parse_release(text: str) -> dict[str, Any]:
    flat = re.sub(r"\s+", " ", text)
    out: dict[str, Any] = {}
    if m := CHIPS.search(flat):
        out["period"] = f"20{m.group(5)}-{int(m.group(6)):02d}"
        out["chips_usd"] = _num(m.group(7)) * EOK
        out["chips_yoy"] = _pct(m.group(8))
    if m := MEMORY.search(flat):
        out["memory_year_ago_usd"] = _num(m.group(1)) * EOK
        out["memory_usd"] = _num(m.group(2)) * EOK
        out["memory_yoy"] = _pct(m.group(3))
        out["system_chips_usd"] = _num(m.group(5)) * EOK
        out["system_chips_yoy"] = _pct(m.group(6))
    for m in PRICE.finditer(flat):
        key = "ddr5_16gb" if m.group(1).startswith("DDR5") else "nand_128gb"
        out[f"{key}_contract_usd"] = _num(m.group(4))
        out[f"{key}_yoy"] = _pct(m.group(5))
    return out


def latest_release() -> dict[str, str]:
    """The newest monthly release on the ministry's press board: its page and PDF link."""
    for keyword in ("수출입동향", "수출입 동향"):
        page = get(BOARD, params={"searchCondition": "1", "searchKeyword": keyword}, browser=True, ttl_hours=6)
        for href, title in re.findall(r'href="(/kor/article/ATCL3f49a5a8c/\d+/view[^"]*)"[^>]*>(.*?)</a>', page.decode("utf-8", "replace"), re.S):
            title = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", title))).strip()
            if TITLE.search(title):
                return {"title": title, "url": SITE + html.unescape(href)}
    raise RuntimeError("no export-import release found on the MOTIR press board")


def _pdf_link(view_url: str) -> str:
    page = get(view_url, browser=True, ttl_hours=24).decode("utf-8", "replace")
    for m in re.finditer(r'href="(/attach/down/[^"]+)"', page):
        name = re.search(r"([^<>\"/]+\.(pdf|hwpx|hwp))", page[m.end() : m.end() + 600], re.I)
        if name and name.group(2).lower() == "pdf":
            return SITE + html.unescape(m.group(1))
    raise RuntimeError(f"no PDF attached to {view_url}")


def fetch() -> dict[str, Any]:
    release = latest_release()
    pdf_url = _pdf_link(release["url"])
    raw = get(pdf_url, browser=True, headers={"Referer": release["url"]}, ttl_hours=24 * 7)
    text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(raw)).pages)
    parsed = parse_release(text)
    if "memory_usd" not in parsed:
        raise RuntimeError(f"memory export line not found in {release['title']}")
    return {**parsed, "title": release["title"], "source": release["url"], "pdf": pdf_url}
