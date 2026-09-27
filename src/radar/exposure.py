"""Stage 4: how much of the portfolio sits with the bottleneck's owners, and how much in the consensus trade.

Pure arithmetic on your IBKR positions and this month's bottleneck.json. Output
goes to private/, since it describes your account.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from .bottleneck import load_owners
from .config import DATA, PRIVATE, month_key
from .store import latest, read_json, write_json, write_text


def symbol_index(owners: dict[str, Any]) -> dict[str, str]:
    return {ticker.upper(): cid for cid, company in owners["companies"].items() for ticker in company["tickers"]}


def compute(statement: dict[str, Any], call: dict[str, Any], owners: dict[str, Any]) -> dict[str, Any]:
    index = symbol_index(owners)
    bottleneck_ids, consensus_ids = set(call["owners"]), set(call["consensus_trade"])
    rows, totals = [], defaultdict(float)
    for p in statement["positions"]:
        value = p.get("value_base") or 0.0
        symbol = (p.get("underlying") or p.get("symbol") or "").upper()  # options count toward their underlying
        company = index.get(symbol)
        bucket = "bottleneck" if company in bottleneck_ids else "consensus" if company in consensus_ids else "other"
        totals[bucket] += value
        rows.append({"symbol": p.get("symbol"), "company": company, "bucket": bucket, "value_base": value})
    invested = sum(totals.values())
    denominator = statement.get("nav") or invested
    shares = {bucket: totals[bucket] / denominator if denominator else 0.0 for bucket in ("bottleneck", "consensus", "other")}
    if statement.get("nav"):
        shares["cash_and_rest"] = 1 - sum(shares.values())
    return {
        "as_of": statement.get("period_end"),
        "bottleneck": call["bottleneck"],
        "denominator": denominator,
        "denominator_is_nav": bool(statement.get("nav")),
        "shares": shares,
        "rows": sorted(rows, key=lambda r: -abs(r["value_base"])),
    }


def markdown(result: dict[str, Any], call: dict[str, Any], owners: dict[str, Any]) -> str:
    label = owners["inputs"][call["bottleneck"]]["label"]
    names = owners["companies"]
    shares = result["shares"]
    base = "net asset value" if result["denominator_is_nav"] else "the value of your positions"
    lines = [
        f"# Exposure, {date.today():%Y-%m-%d}",
        "",
        f"This month's bottleneck: {label}. Shares of {base} (${result['denominator']:,.0f}) as of {result['as_of']}.",
        "",
        "| Bucket | Share |",
        "|---|---:|",
        f"| Owners of the bottleneck | {shares['bottleneck']:.1%} |",
        f"| Consensus AI trade | {shares['consensus']:.1%} |",
        f"| Everything else | {shares['other']:.1%} |",
    ]
    if "cash_and_rest" in shares:
        lines.append(f"| Cash and the rest | {shares['cash_and_rest']:.1%} |")
    lines += ["", "| Position | Company | Bucket | Value |", "|---|---|---|---:|"]
    for r in result["rows"]:
        company = names[r["company"]]["name"] if r["company"] else ""
        lines.append(f"| {r['symbol']} | {company} | {r['bucket']} | ${r['value_base']:,.0f} |")
    lines += ["", "No orders were placed. The Flex token this reads with can't place them."]
    return "\n".join(lines)


def run() -> dict[str, Any]:
    month = month_key()
    call_path = DATA / month / "bottleneck.json"
    positions_path = latest(PRIVATE / "ibkr", "positions-*.json")
    if not call_path.exists():
        raise SystemExit(f"No {call_path.relative_to(DATA.parent)} yet. Run `radar bottleneck` first.")
    if not positions_path:
        raise SystemExit("No IBKR positions yet. Run `radar ibkr` first.")
    call, statement, owners = read_json(call_path), read_json(positions_path), load_owners()
    result = compute(statement, call, owners)
    out = PRIVATE / month / "exposure"
    write_json(out.with_suffix(".json"), result)
    write_text(out.with_suffix(".md"), markdown(result, call, owners))
    s = result["shares"]
    print(f"Exposure: {s['bottleneck']:.1%} with the bottleneck's owners, {s['consensus']:.1%} in the consensus trade")
    print(f"  wrote {out.with_suffix('.md').relative_to(PRIVATE.parent)}")
    return result
