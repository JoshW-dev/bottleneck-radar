"""Static dashboard: renders the public outputs in data/ into site/index.html for Vercel.

Plain HTML and CSS plus a small inline script for tooltips. Everything on the page
comes from data/, so nothing about your brokerage account can reach it.
"""

from __future__ import annotations

import html
import json
import math
from datetime import date
from typing import Any, Callable

import yaml

from .config import CONFIG, DATA, ROOT
from .store import read_json, write_text

SITE = ROOT / "site"
REPO = "https://github.com/JoshW-dev/bottleneck-radar"

BLUE, ORANGE, AQUA, GRAY = "#2a78d6", "#eb6834", "#1baf7a", "#c3c2b7"
BLUE_DARK, BLUE_LIGHT = "#256abf", "#86b6ef"
GROUPS = [  # colors for the fund's holdings, by the input each company makes
    ("Memory", BLUE, ["memory"]),
    ("Chips and packaging", AQUA, ["advanced_chips"]),
    ("Power and grid", ORANGE, ["gas_turbines", "grid_interconnection"]),
]
INPUT_LABELS = {
    "memory": "Memory chips",
    "advanced_chips": "Leading-edge chips",
    "gas_turbines": "Gas turbines",
    "grid_interconnection": "Grid connections",
}


# ---------- formatting ----------


def e(value: Any) -> str:
    return html.escape(str(value), quote=True)


def usd(value: float, digits: int = 1) -> str:
    for size, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
        if abs(value) >= size:
            return f"${value / size:,.{digits}f}{suffix}"
    return f"${value:,.0f}"


def pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:+.0%}"


def month_name(period: str) -> str:
    return date.fromisoformat(f"{period}-01").strftime("%B %Y")


def short_date(iso: str) -> str:
    return date.fromisoformat(iso[:10]).strftime("%b '%y")


def link(url: str | None, text: str = "source") -> str:
    return f'<a href="{e(url)}" rel="noopener">{e(text)}</a>' if url else ""


def nice_max(value: float) -> float:
    if value <= 0:
        return 1.0
    magnitude = 10 ** math.floor(math.log10(value))
    for step in (1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if value <= step * magnitude:
            return step * magnitude
    return 10 * magnitude


def nice_ticks(top: float, most: int = 5) -> list[float]:
    """Round gridline values up to `top`, at most `most` of them."""
    magnitude = 10 ** math.floor(math.log10(top / most))
    step = next(m * magnitude for m in (1, 2, 2.5, 5, 10) if top / (m * magnitude) <= most + 1e-9)
    return [step * i for i in range(1, int(top / step + 1e-9) + 1)]


# ---------- components ----------


def tile(label: str, value: str, sub: str = "", note: str = "") -> str:
    return (
        f'<div class="tile"><div class="tile-label">{e(label)}</div><div class="tile-value">{e(value)}</div>'
        + (f'<div class="tile-sub">{e(sub)}</div>' if sub else "")
        + (f'<div class="tile-note">{note}</div>' if note else "")
        + "</div>"
    )


def table(headers: list[str], rows: list[list[str]], numeric: set[int] = frozenset()) -> str:
    head = "".join(f'<th{" class=num" if i in numeric else ""}>{e(h)}</th>' for i, h in enumerate(headers))
    body = "".join(
        "<tr>" + "".join(f'<td{" class=num" if i in numeric else ""}>{cell}</td>' for i, cell in enumerate(row)) + "</tr>"
        for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def table_view(headers: list[str], rows: list[list[str]], numeric: set[int] = frozenset()) -> str:
    return f'<details class="tv"><summary>Show as a table</summary>{table(headers, rows, numeric)}</details>'


def line_chart(
    x_labels: list[str],
    series: list[dict[str, Any]],
    fmt: Callable[[float], str],
    *,
    y_max: float | None = None,
    height: int = 200,
    compact: bool = False,
    tick_fmt: Callable[[float], str] | None = None,
) -> str:
    """Lines drawn in a stretched SVG with non-scaling strokes; every label is HTML so it stays readable on phones."""
    n = len(x_labels)
    top = y_max or nice_max(max(v for s in series for v in s["values"] if v is not None))
    ticks = [top / 2, top] if compact else nice_ticks(top)
    tick_fmt = tick_fmt or fmt

    def x(i: int) -> float:
        return 0.0 if n == 1 else i / (n - 1) * 100

    def y(v: float) -> float:
        return 100 - v / top * 100

    polylines, dots, ends = [], [], []
    for s in series:
        points = [(x(i), y(v)) for i, v in enumerate(s["values"]) if v is not None]
        pts = " ".join(f"{px * 10:.1f},{py * 10:.1f}" for px, py in points)
        polylines.append(
            f'<polyline points="{pts}" fill="none" stroke="{s["color"]}" stroke-width="2" '
            'stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"/>'
        )
        px, py = points[-1]
        dots.append(f'<span class="lc-dot" style="left:{px:.2f}%;top:{py:.2f}%;background:{s["color"]}"></span>')
        ends.append([py, s, next(v for v in reversed(s["values"]) if v is not None)])

    labels = ""
    if not compact:  # end labels in the right gutter, pushed apart just enough not to overlap
        min_gap = 18 / height * 100
        ends.sort(key=lambda item: item[0])
        for a, b in zip(ends, ends[1:]):
            b[0] = max(b[0], a[0] + min_gap)
        labels = "".join(
            f'<span class="lc-end" style="top:{py:.2f}%"><i style="background:{s["color"]}"></i>{e(s["name"])} '
            f"<b>{e(fmt(last))}</b></span>"
            for py, s, last in ends
        )

    grid = "".join(f'<div class="lc-grid" style="bottom:{t / top * 100:.2f}%"><span>{e(tick_fmt(t))}</span></div>' for t in ticks)
    marks = [0, n - 1] if compact or n < 5 else [0, n // 2, n - 1]
    xaxis = "".join(
        f'<span style="left:{x(i):.2f}%" class="{"first" if i == 0 else "last" if i == n - 1 else ""}">{e(x_labels[i])}</span>'
        for i in marks
    )
    data = {
        "x": x_labels,
        "series": [
            {"name": s["name"], "color": s["color"], "display": [fmt(v) if v is not None else "n/a" for v in s["values"]]}
            for s in series
        ],
    }
    klass = "lc compact" if compact else "lc"
    return (
        f'<div class="{klass}" data-chart="{e(json.dumps(data))}">'
        f'<div class="lc-plot" style="height:{height}px"><div class="lc-base"></div>{grid}'
        f'<svg viewBox="0 0 1000 1000" preserveAspectRatio="none" aria-hidden="true">{"".join(polylines)}</svg>'
        f'{"".join(dots)}{labels}<div class="lc-cross" hidden></div></div>'
        f'<div class="lc-x">{xaxis}</div></div>'
    )


def hbars(rows: list[dict[str, Any]], max_total: float, fmt: Callable[[float], str]) -> str:
    """Horizontal bars, optionally stacked. Widths top out at 72% of the track so tip labels always fit."""
    out = ['<div class="hb">']
    for row in rows:
        total = sum(s["value"] for s in row["segments"])
        width = total / max_total * 72 if max_total else 0
        # flex-grow shares must sum to 1 or more, or a lone segment only fills part of its bar
        segments = "".join(
            f'<span style="flex:{s["value"] / total:.6f} 1 0;background:{s["color"]}"></span>'
            for s in row["segments"]
            if s["value"] > 0
        )
        tip = {"title": row["label"], "rows": [[fmt(s["value"]), s["name"], s["color"]] for s in row["segments"]]}
        sub = f'<small>{e(row["sub"])}</small>' if row.get("sub") else ""
        out.append(
            f'<div class="hb-row" tabindex="0" data-tip="{e(json.dumps(tip))}">'
            f'<div class="hb-label">{e(row["label"])}{sub}</div>'
            f'<div class="hb-track"><div class="hb-fill" style="width:{width:.2f}%">{segments}</div>'
            f'<span class="hb-value">{e(row.get("value_text", fmt(total)))}</span></div></div>'
        )
    out.append("</div>")
    return "".join(out)


def legend(items: list[tuple[str, str]], shape: str = "box") -> str:
    return '<div class="legend">' + "".join(f'<span><i class="{shape}" style="background:{c}"></i>{e(t)}</span>' for t, c in items) + "</div>"


# ---------- sections ----------


def section(section_id: str, title: str, caption: str, body: str) -> str:
    return f'<section id="{section_id}"><h2>{e(title)}</h2><p class="caption">{caption}</p>{body}</section>'


def call_section(call: dict[str, Any] | None, owners: dict[str, Any]) -> str:
    if not call:
        return (
            '<section id="call" class="call pending"><div class="eyebrow">This month\'s call</div>'
            "<p>The model's pick for the tightest input shows up here after the first run with an Anthropic API key. "
            "Until then, the figures below are the raw inputs it will read.</p></section>"
        )
    names = owners["companies"]

    def chips(ids: list[str]) -> str:
        return "".join(f'<span class="chip">{e(names[i]["name"])} <small>{e("/".join(names[i]["tickers"]))}</small></span>' for i in ids)

    ranking = "".join(
        f'<div class="rank"><span>{e(INPUT_LABELS[r["input"]])}</span>'
        f'<span class="meter" role="img" aria-label="tightness {r["tightness"]} of 5">'
        + "".join(f'<i class="{"on" if k < r["tightness"] else ""}"></i>' for k in range(5))
        + f'</span><b>{r["tightness"]}/5</b></div>'
        for r in call["ranking"]
    )
    falsifiers = table(["Figure", "Threshold", "Why it matters"], [[e(f["metric"]), e(f["threshold"]), e(f["why"])] for f in call["falsifiers"]])
    return (
        f'<section id="call" class="call"><div class="eyebrow">This month\'s call · {e(month_name(call["month"]))}</div>'
        f'<h2 class="call-title">{e(INPUT_LABELS[call["bottleneck"]])}</h2><p class="call-headline">{e(call["headline"])}</p>'
        f'<p>{e(call["why"])}</p><div class="call-grid"><div><h3>Tightness by input</h3>{ranking}</div>'
        f'<div><h3>Who makes it</h3><div class="chips">{chips(call["owners"])}</div>'
        f'<h3>The consensus trade</h3><div class="chips">{chips(call["consensus_trade"])}</div></div></div>'
        f'<h3>What would prove this wrong</h3>{falsifiers}'
        f'<p class="muted">Since last month: {e(call["change_vs_last_month"])}</p></section>'
    )


def signals_section(supply: dict[str, Any]) -> str:
    tiles = []
    if m := supply.get("memory"):
        tiles.append(tile("Memory chips", usd(m["memory_usd"]), f"Korean memory exports in {month_name(m['period'])}, {pct(m['memory_yoy'])} y/y",
                          f"DDR5 contract price {pct(m.get('ddr5_16gb_yoy'))} y/y · {link(m['source'], 'MOTIR')}"))
    if o := supply.get("export_orders"):
        el = o["electronics"]
        tiles.append(tile("Leading-edge chips", usd(el["usd_millions"] * 1e6), f"Taiwan electronics export orders, {month_name(el['period'])}, {pct(el.get('yoy'))} y/y",
                          f"A demand signal, since no direct supply series exists yet · {link(el['url'], 'MOEA')}"))
    if turbines := supply.get("gas_turbines"):
        gev = next((t for t in turbines if t["company"] == "GE Vernova"), turbines[0])
        committed = gev.get("backlog_and_slots_gw") or gev.get("backlog_gw", 0) + gev.get("slot_reservations_gw", 0)
        years = f", about {gev['years_of_backlog']:g} years of shipments" if gev.get("years_of_backlog") else ""
        tiles.append(tile("Gas turbines", f"{committed:g} GW", f"{gev['company']} backlog and slot reservations{years}",
                          f"{e(gev.get('quarter') or gev.get('as_of'))} · {link(gev['source'], 'release')}"))
    if grid := supply.get("grid"):
        g = grid[0]
        total = (g.get("base_load_gw") or 0) + (g.get("studied_load_gw") or 0)
        tiles.append(tile("Grid connections", f"{total:,.0f} GW", f"Large loads qualified for ERCOT's Batch Zero study",
                          f"Entered by hand from the {e(g['as_of'])} update · {link(g['source'], 'ERCOT')}"))
    caption = "One headline figure per input. The monthly call ranks these four."
    return section("signals", "The four inputs", caption, f'<div class="tiles four">{"".join(tiles)}</div>')


def demand_section(demand: dict[str, Any]) -> str:
    total, companies = demand["total"], demand["companies"]
    p, added = demand["physical"]["ttm"], demand["physical"]["added_vs_prior_ttm"]
    hero = (
        f'<div class="hero"><div class="hero-value">{e(usd(total["ttm"], 0))}</div>'
        f'<div class="hero-sub">Capex over the last four reported quarters at Amazon, Alphabet, Microsoft, Meta and Oracle, '
        f'{e(pct(total["ttm_growth"]))} on the {e(usd(total["prior_ttm"], 0))} spent the year before. '
        f'Latest quarters annualize to {e(usd(total["run_rate"], 0))}.</div></div>'
    )
    chain = "".join(
        [
            tile("Data center power", f"{p['gw']:.1f} GW", f"+{added['gw']:.1f} GW on the prior year"),
            tile("GPUs", f"{p['gpus'] / 1e6:.1f}M", f"+{added['gpus'] / 1e6:.1f}M on the prior year"),
            tile("HBM memory", f"{p['hbm_gb'] / 1e9:.2f}B GB", f"+{added['hbm_gb'] / 1e9:.2f}B GB on the prior year"),
            tile("Floor space", f"{p['sqft'] / 1e6:,.0f}M sq ft", f"+{added['sqft'] / 1e6:,.0f}M sq ft on the prior year"),
            tile("Gas turbine equivalents", f"{p['turbines_7ha']:,.0f}", "GE 7HA.03 units, simple cycle"),
        ]
    )
    unverified = [k for k, v in demand["assumptions"].items() if v.get("status") == "unverified"]
    chain_note = (
        f'<p class="muted">Converted with the factors in {link(REPO + "/blob/main/config/assumptions.yaml", "config/assumptions.yaml")}. '
        f"{len(unverified)} of them still lack a primary source, so treat these as rough.</p>"
    )

    order = sorted(companies, key=lambda t: -companies[t]["latest"]["value"])
    y_max = nice_max(max(q["value"] for c in companies.values() for q in c["quarters"]) / 1e9)
    panels, rows = [], []
    for t in order:
        c = companies[t]
        qs = c["quarters"]
        chart = line_chart([short_date(q["end"]) for q in qs], [{"name": c["name"], "color": BLUE, "values": [q["value"] / 1e9 for q in qs]}],
                           lambda v: f"${v:,.1f}B", y_max=y_max, height=110, compact=True, tick_fmt=lambda v: f"${v:,.0f}B")
        panels.append(
            f'<div class="sm"><div class="sm-head"><span>{e(c["name"])}</span><b>{e(usd(c["latest"]["value"]))}</b></div>'
            f'<div class="sm-sub">Quarter to {e(short_date(c["latest"]["end"]))}, {e(pct(c.get("yoy")))} y/y</div>{chart}</div>'
        )
        rows += [[e(c["name"]), e(q["end"]), e(usd(q["value"]))] for q in qs]
    fastest = max(order, key=lambda t: companies[t].get("yoy") or -1)
    quotes = "".join(
        f'<blockquote>{e(q)}<cite>{e(companies[t]["name"])}, {link(companies[t]["guidance"]["url"], "earnings release")} filed {e(companies[t]["guidance"]["filed"])}</cite></blockquote>'
        for t in order
        for q in companies[t]["guidance"].get("forward", [])
    )
    body = (
        hero
        + f'<div class="tiles five">{chain}</div>{chain_note}'
        + f'<h3>Quarterly capex by company</h3><p class="muted">Same scale in every panel. {e(companies[fastest]["name"])} grew fastest, '
        f'{e(pct(companies[fastest]["yoy"]))} on the same quarter a year earlier. Oracle\'s quarters end in Feb, May, Aug and Nov.</p>'
        + f'<div class="sm-grid">{"".join(panels)}</div>'
        + table_view(["Company", "Quarter end", "Capex"], rows, {2})
        + (f"<h3>Guidance in the filings</h3>{quotes}" if quotes else "")
    )
    caption = f"The five biggest cloud buyers spent {e(usd(total['ttm'], 0))} in a year. Here is what that buys in physical terms."
    return section("demand", "Demand", caption, body)


def supply_section(supply: dict[str, Any]) -> str:
    parts, captions = [], []
    if m := supply.get("memory"):
        multiple = m["memory_usd"] / m["memory_year_ago_usd"] if m.get("memory_year_ago_usd") else None
        tiles = [
            tile("Korean memory chip exports", usd(m["memory_usd"]), f"{month_name(m['period'])}, {pct(m['memory_yoy'])} on {usd(m['memory_year_ago_usd'])} a year earlier"),
            tile("All Korean chip exports", usd(m["chips_usd"]), f"{pct(m['chips_yoy'])} y/y"),
        ]
        if "ddr5_16gb_contract_usd" in m:
            tiles.append(tile("DDR5 16Gb contract price", f"${m['ddr5_16gb_contract_usd']:.2f}", f"{pct(m['ddr5_16gb_yoy'])} y/y"))
        if "nand_128gb_contract_usd" in m:
            tiles.append(tile("NAND 128Gb contract price", f"${m['nand_128gb_contract_usd']:.2f}", f"{pct(m['nand_128gb_yoy'])} y/y"))
        parts.append(f'<h3>Memory</h3><div class="tiles four">{"".join(tiles)}</div>'
                     f'<p class="muted">From the Korean trade ministry\'s monthly release ({link(m["source"], "page")}, {link(m["pdf"], "PDF")}).</p>')
        if multiple:
            captions.append(f"Korea shipped {multiple:.1f} times as much memory in {month_name(m['period'])} as a year earlier.")

    if o := supply.get("export_orders"):
        el, ict = o["electronics"], o["ict"]
        history = [(p, v) for p, v in el["history"]]
        ict_by_period = dict(ict["history"])
        x = [date.fromisoformat(p + "-01").strftime("%b '%y") for p, _ in history]
        chart = line_chart(
            x,
            [
                {"name": "Electronics", "color": BLUE, "values": [v / 1e3 for _, v in history]},
                {"name": "ICT products", "color": ORANGE, "values": [ict_by_period.get(p, 0) / 1e3 or None for p, _ in history]},
            ],
            lambda v: f"${v:,.1f}B",
            tick_fmt=lambda v: f"${v:,.0f}B",
        )
        rows = [[e(p), e(usd(v * 1e6)), e(usd(ict_by_period.get(p, 0) * 1e6))] for p, v in history]
        parts.append(
            f"<h3>Taiwan export orders</h3>{legend([('Electronics', BLUE), ('ICT products', ORANGE)], 'line')}{chart}"
            + table_view(["Month", "Electronics", "ICT products"], rows, {1, 2})
            + f'<p class="muted">US$ per month, from Taiwan\'s Ministry of Economic Affairs ({link(el["url"], "electronics")}, {link(ict["url"], "ICT")}). '
            "Orders measure demand for Taiwanese electronics, which makes them a proxy for chips.</p>"
        )

    if turbines := supply.get("gas_turbines"):
        rows, table_rows = [], []
        for t in turbines:
            firm = t.get("backlog_gw") or 0
            slots = t.get("slot_reservations_gw") or 0
            if not firm and t.get("backlog_and_slots_gw"):
                firm = t["backlog_and_slots_gw"]
            years = f"{t['years_of_backlog']:g} years of shipments" if t.get("years_of_backlog") else "shipments not disclosed"
            rows.append({
                "label": t["company"], "sub": years, "value_text": f"{firm + slots:g} GW",
                "segments": [{"name": "Firm backlog", "value": firm, "color": BLUE_DARK},
                             {"name": "Slot reservations", "value": slots, "color": BLUE_LIGHT}],
            })
            table_rows.append([e(t["company"]), e(f"{firm:g}"), e(f"{slots:g}"), e(t.get("quarter") or t.get("as_of")), link(t["source"], t["method"])])
        rows.sort(key=lambda r: -sum(s["value"] for s in r["segments"]))
        max_total = max(sum(s["value"] for s in r["segments"]) for r in rows)
        parts.append(
            "<h3>Gas turbine backlogs</h3>" + legend([("Firm backlog", BLUE_DARK), ("Slot reservations", BLUE_LIGHT)])
            + hbars(rows, max_total, lambda v: f"{v:g} GW")
            + table_view(["Maker", "Firm backlog (GW)", "Slot reservations (GW)", "As of", "Source"], table_rows, {1, 2})
            + '<p class="muted">Years of shipments divides backlog plus reservations by the latest quarter\'s shipments times four. '
            "MHI doesn't report reservations or shipments in GW. Siemens Energy and MHI are entered by hand from their slide decks.</p>"
        )
        lead = rows[0]
        captions.append(f"{lead['label']} has {lead['value_text']} of gas turbines committed, {lead['sub']} at its latest pace.")

    if grid := supply.get("grid"):
        g = grid[0]
        tiles = [
            tile("Qualified as base load", f"{g['base_load_gw']:g} GW", f"{g['base_load_projects']} projects"),
            tile("Qualified as studied load", f"{g['studied_load_gw']:g} GW", f"{g['studied_load_projects']} projects"),
        ]
        parts.append(
            f'<h3>Grid connections</h3><div class="tiles two">{"".join(tiles)}</div>'
            f'<p class="muted">ERCOT\'s Batch Zero update of {e(g["as_of"])} ({link(g["source"], "PDF")}), entered by hand. {e(g.get("note", ""))}</p>'
        )
    if errors := supply.get("errors"):
        parts.append('<p class="muted">Sources that failed this run: ' + e(", ".join(err["source"] for err in errors)) + ".</p>")
    return section("supply", "Supply", " ".join(e(c) for c in captions) or "Supply-side figures for each input.", "".join(parts))


def book_section(book: dict[str, Any], owners: dict[str, Any]) -> str:
    ticker_group: dict[str, tuple[str, str]] = {}
    for label, color, inputs in GROUPS:
        for name in inputs:
            for cid in owners["inputs"][name]["owners"]:
                for ticker in owners["companies"][cid]["tickers"]:
                    ticker_group.setdefault(ticker.upper(), (label, color))

    weights = book["weights"]
    shares: dict[str, float] = {}
    for w in weights:
        label, _ = ticker_group.get((w["ticker"] or "").upper(), ("Other", GRAY))
        shares[label] = shares.get(label, 0) + w["weight"]
    palette = {label: color for label, color, _ in GROUPS} | {"Other": GRAY}
    order = [label for label, _, _ in GROUPS if label in shares] + (["Other"] if "Other" in shares else [])
    stack = "".join(f'<span style="flex:{shares[k]:.6f} 1 0;background:{palette[k]}" data-tip="{e(json.dumps({"title": k, "rows": [[f"{shares[k]:.1%}", "of the long book", palette[k]]]}))}" tabindex="0"></span>' for k in order)
    stack_legend = legend([(f"{k} {shares[k]:.1%}", palette[k]) for k in order])

    top, rest = weights[:12], weights[12:]
    rows = []
    for w in top:
        label, color = ticker_group.get((w["ticker"] or "").upper(), ("Other", GRAY))
        rows.append({"label": w["ticker"] or w["name"], "sub": w["name"].title(), "value_text": f"{w['weight']:.1%}",
                     "segments": [{"name": label, "value": w["weight"], "color": color}]})
    if rest:
        rows.append({"label": f"{len(rest)} others", "sub": "Smaller positions", "value_text": f"{sum(w['weight'] for w in rest):.1%}",
                     "segments": [{"name": "Other", "value": sum(w["weight"] for w in rest), "color": GRAY}]})
    bars = hbars(rows, max(r["segments"][0]["value"] for r in rows), lambda v: f"{v:.1%}")
    table_rows = [[e(w["ticker"] or ""), e(w["name"].title()), e(usd(w["value"])), e(f"{w['weight']:.2%}")] for w in weights]
    caption = (f"{shares.get('Memory', 0):.0%} of {e(book['fund'])}'s long stock book sits with memory makers, as of "
               f"{e(date.fromisoformat(book['period']).strftime('%B %-d, %Y'))}.")
    body = (
        f'<div class="stack" role="img" aria-label="Share of the book by input">{stack}</div>{stack_legend}'
        + bars
        + table_view(["Ticker", "Company", "Value", "Weight"], table_rows, {2, 3})
        + f'<p class="muted">Long stock only, from the 13F filed {e(book["filed"])} ({link(book["source"], "information table")}). '
        "A 13F arrives 45 days after the quarter ends and leaves out shorts, cash and leverage.</p>"
    )
    return section("book", "The fund's book", caption, body)


FACTORS = {  # (label, how to show the value)
    "datacenter_share_of_capex": ("Share of capex spent on AI data centers", lambda v: f"{v:.0%}"),
    "capex_per_gw": ("Capex per GW of facility power", lambda v: usd(v)),
    "it_power_share": ("Share of power reaching IT (1/PUE)", lambda v: f"{v:.0%}"),
    "kw_per_gpu": ("IT power per GPU", lambda v: f"{v:g} kW"),
    "hbm_gb_per_gpu": ("HBM per GPU", lambda v: f"{v:g} GB"),
    "sqft_per_mw": ("Floor space per MW", lambda v: f"{v:,.0f} sq ft"),
    "mw_per_turbine": ("Power per gas turbine", lambda v: f"{v:g} MW"),
}


def sources_section(demand: dict[str, Any]) -> str:
    rows = []
    for key, a in demand["assumptions"].items():
        status = "unverified" if a.get("status") == "unverified" else "assumption" if a.get("status") == "assumption" else link(a.get("url"), "sourced")
        label, show = FACTORS.get(key, (key.replace("_", " "), lambda v: f"{v:,}"))
        rows.append([e(label), e(show(a["value"])), e(a.get("note") or a.get("source") or ""), status])
    return section(
        "method",
        "How it's built",
        "Code pulls every number. A model only writes the monthly call.",
        "<p>Each month a script pulls hyperscaler capex from SEC filings, memory exports from Korea's trade ministry, "
        "export orders from Taiwan's economics ministry and turbine backlogs from GE Vernova's earnings release, then "
        f"rebuilds this page. The code, the data and every past month are on {link(REPO, 'GitHub')}.</p>"
        "<h3>Conversion factors</h3>" + table(["Factor", "Value", "Note", "Status"], rows, {1}),
    )


# ---------- page ----------

CSS = """
:root{color-scheme:light;--bg:#fff;--ink:#0b0b0b;--ink-2:#52514e;--muted:#6f6e69;--line:#e1e0d9;--axis:#c3c2b7;--tint:#f4f8fd;--accent:#2a78d6}
*{box-sizing:border-box}html,body{background:var(--bg)}body{margin:0;color:var(--ink);font:16px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
a{color:var(--accent)}main{max-width:1060px;margin:0 auto;padding:40px 20px 64px}
header h1{font-size:30px;line-height:1.2;margin:0 0 8px;font-weight:650;letter-spacing:-.01em}header p{margin:0;color:var(--ink-2);max-width:720px}
.meta{margin-top:10px;font-size:14px;color:var(--muted)}
section{border-top:1px solid var(--line);margin-top:40px;padding-top:28px}h2{font-size:22px;margin:0 0 6px;font-weight:650}
h3{font-size:16px;margin:28px 0 10px;font-weight:600}.caption{margin:0 0 20px;color:var(--ink-2);max-width:760px}.muted{color:var(--muted);font-size:14px}
.call{background:var(--tint);border:1px solid #d7e5f7;border-radius:12px;padding:24px}.call.pending p{margin:6px 0 0;color:var(--ink-2)}
.eyebrow{font-size:13px;font-weight:600;color:var(--accent);text-transform:none}.call-title{font-size:28px;margin:6px 0}.call-headline{font-size:18px;font-weight:500}
.call-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:24px}
.rank{display:grid;grid-template-columns:150px 1fr auto;gap:10px;align-items:center;font-size:14px;margin:6px 0}
.meter{display:flex;gap:2px}.meter i{flex:1;height:8px;background:#cde2fb}.meter i.on{background:var(--accent)}.meter i:last-child{border-radius:0 4px 4px 0}
.chips{display:flex;flex-wrap:wrap;gap:6px}.chip{border:1px solid var(--line);border-radius:999px;padding:3px 10px;font-size:14px;background:#fff}.chip small{color:var(--muted)}
.tiles{display:grid;gap:12px}.tiles.two{grid-template-columns:repeat(auto-fit,minmax(220px,1fr))}.tiles.four{grid-template-columns:repeat(auto-fit,minmax(220px,1fr))}.tiles.five{grid-template-columns:repeat(auto-fit,minmax(170px,1fr))}
.tile{border:1px solid var(--line);border-radius:10px;padding:14px 16px}.tile-label{font-size:13px;color:var(--ink-2)}.tile-value{font-size:28px;font-weight:600;line-height:1.25;margin-top:2px}
.tile-sub{font-size:14px;color:var(--ink-2);margin-top:4px}.tile-note{font-size:13px;color:var(--muted);margin-top:6px}
.hero{margin:4px 0 20px}.hero-value{font-size:56px;font-weight:650;line-height:1.05;letter-spacing:-.02em}.hero-sub{color:var(--ink-2);max-width:700px;margin-top:6px}
.sm-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:20px 24px}.sm-head{display:flex;justify-content:space-between;font-size:15px}.sm-head b{font-weight:600}
.sm-sub{font-size:13px;color:var(--muted);margin-bottom:8px}
blockquote{margin:12px 0;padding:10px 16px;border-left:3px solid var(--line);color:var(--ink-2)}blockquote cite{display:block;margin-top:6px;font-size:13px;font-style:normal;color:var(--muted)}
.legend{display:flex;flex-wrap:wrap;gap:6px 18px;font-size:14px;color:var(--ink-2);margin:4px 0 10px}.legend span{display:inline-flex;align-items:center;gap:6px}
.legend i{display:inline-block}.legend i.box{width:12px;height:12px;border-radius:3px}.legend i.line{width:16px;height:2px}
.lc{position:relative;margin:14px 0 4px;padding-left:40px}.lc.compact{padding-left:32px}.lc:not(.compact){padding-right:176px}.lc-plot{position:relative;cursor:crosshair;touch-action:pan-y}
.lc-plot svg{position:absolute;inset:0;width:100%;height:100%;overflow:visible}
.lc-base{position:absolute;left:0;right:0;bottom:0;border-top:1px solid var(--axis)}
.lc-grid{position:absolute;left:0;right:0;border-top:1px solid var(--line)}.lc-grid span{position:absolute;right:100%;top:-7px;padding-right:6px;font-size:11px;line-height:14px;color:var(--muted);font-variant-numeric:tabular-nums;white-space:nowrap}
.lc-dot{position:absolute;width:8px;height:8px;border-radius:50%;transform:translate(-50%,-50%);box-shadow:0 0 0 2px #fff}
.lc-end{position:absolute;left:calc(100% + 12px);transform:translateY(-50%);font-size:13px;white-space:nowrap;color:var(--ink-2);display:flex;align-items:center;gap:6px}
.lc-end i{display:inline-block;width:12px;height:2px}.lc-end b{color:var(--ink);font-weight:600}
.lc-cross{position:absolute;top:0;bottom:0;width:0;border-left:1px solid var(--axis);pointer-events:none}
.lc-x{position:relative;height:20px;font-size:12px;color:var(--muted);font-variant-numeric:tabular-nums}.lc-x span{position:absolute;top:4px;transform:translateX(-50%);white-space:nowrap}
.lc-x span.first{transform:none}.lc-x span.last{transform:translateX(-100%)}
.hb{display:grid;gap:6px;margin:6px 0}.hb-row{display:grid;grid-template-columns:minmax(110px,170px) 1fr;gap:12px;align-items:center;border-radius:6px;padding:2px 0}
.hb-row:hover,.hb-row:focus{background:#f7f7f5;outline:none}.hb-label{font-size:14px;line-height:1.25}.hb-label small{display:block;color:var(--muted);font-size:12px}
.hb-track{display:flex;align-items:center;gap:8px;min-width:0}.hb-fill{display:flex;gap:2px;height:18px}.hb-fill span{height:100%}.hb-fill span:last-child{border-radius:0 4px 4px 0}
.hb-value{font-size:13px;color:var(--ink-2);white-space:nowrap;font-variant-numeric:tabular-nums}
.stack{display:flex;gap:2px;height:22px;margin:4px 0 8px}.stack span:last-child{border-radius:0 4px 4px 0}
.tv{margin:10px 0}.tv summary{cursor:pointer;font-size:14px;color:var(--accent)}
table{border-collapse:collapse;width:100%;font-size:14px;margin:8px 0}th,td{text-align:left;padding:7px 10px 7px 0;border-bottom:1px solid var(--line);vertical-align:top}
th{font-weight:600;color:var(--ink-2)}td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.tv table,.call table{display:block;overflow-x:auto}
footer{border-top:1px solid var(--line);margin-top:48px;padding-top:20px;font-size:14px;color:var(--muted)}
.tip{position:fixed;left:0;top:0;z-index:10;pointer-events:none;background:#fff;border:1px solid var(--line);border-radius:8px;box-shadow:0 4px 16px rgba(0,0,0,.08);padding:8px 10px;font-size:13px;min-width:120px}
.tip-title{color:var(--muted);margin-bottom:4px}.tip-row{display:flex;align-items:center;gap:8px}.tip-row strong{font-weight:600;color:var(--ink)}.tip-row span:last-child{color:var(--ink-2)}
.tip-key{display:inline-block;width:12px;height:2px}
@media (max-width:640px){main{padding:28px 16px 48px}.hero-value{font-size:44px}.lc:not(.compact){padding-right:0}.lc-end{display:none}.rank{grid-template-columns:120px 1fr auto}}
"""

JS = """
const tip=document.getElementById('tip');
function place(x,y){const r=tip.getBoundingClientRect();let l=x+14,t=y+14;if(l+r.width>innerWidth-8)l=x-r.width-14;if(t+r.height>innerHeight-8)t=y-r.height-14;tip.style.transform=`translate(${Math.max(8,l)}px,${Math.max(8,t)}px)`}
function fill(title,rows){tip.replaceChildren();const h=document.createElement('div');h.className='tip-title';h.textContent=title;tip.append(h);
for(const [value,label,color] of rows){const row=document.createElement('div');row.className='tip-row';const k=document.createElement('span');k.className='tip-key';k.style.background=color;
const v=document.createElement('strong');v.textContent=value;const l=document.createElement('span');l.textContent=label;row.append(k,v,l);tip.append(row)}tip.hidden=false}
function hide(){tip.hidden=true}
document.querySelectorAll('[data-tip]').forEach(el=>{const d=JSON.parse(el.dataset.tip);
el.addEventListener('pointermove',e=>{fill(d.title,d.rows);place(e.clientX,e.clientY)});el.addEventListener('pointerleave',hide);
el.addEventListener('focus',()=>{const r=el.getBoundingClientRect();fill(d.title,d.rows);place(r.left+r.width/2,r.bottom)});el.addEventListener('blur',hide)});
document.querySelectorAll('.lc').forEach(chart=>{const d=JSON.parse(chart.dataset.chart);const plot=chart.querySelector('.lc-plot');const cross=chart.querySelector('.lc-cross');const n=d.x.length;
plot.addEventListener('pointermove',e=>{const r=plot.getBoundingClientRect();const i=Math.max(0,Math.min(n-1,Math.round((e.clientX-r.left)/r.width*(n-1))));
cross.style.left=(n>1?i/(n-1)*100:0)+'%';cross.hidden=false;fill(d.x[i],d.series.map(s=>[s.display[i],s.name,s.color]));place(e.clientX,e.clientY)});
plot.addEventListener('pointerleave',()=>{cross.hidden=true;hide()})});
"""


def render(month: str, demand: dict, supply: dict, book: dict | None, call: dict | None, owners: dict) -> str:
    updated = supply.get("generated") or date.today().isoformat()
    sections = [call_section(call, owners), signals_section(supply), demand_section(demand), supply_section(supply)]
    if book:
        sections.append(book_section(book, owners))
    sections.append(sources_section(demand))
    description = "A monthly look at where AI data center demand is outrunning supply, built from SEC filings and Asian trade data."
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI supply bottleneck radar</title><meta name="description" content="{e(description)}">
<meta property="og:title" content="AI supply bottleneck radar"><meta property="og:description" content="{e(description)}">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Crect x='1' y='9' width='3' height='6' rx='1' fill='%2386b6ef'/%3E%3Crect x='6.5' y='5' width='3' height='10' rx='1' fill='%232a78d6'/%3E%3Crect x='12' y='1' width='3' height='14' rx='1' fill='%23256abf'/%3E%3C/svg%3E">
<style>{CSS}</style></head>
<body><main>
<header><h1>AI supply bottleneck radar</h1><p>{e(description)} It pulls the numbers in code each month and asks a model which input is tightest.</p>
<div class="meta">Data for {e(month_name(month))} · updated {e(updated)} · {link(REPO, "code and data on GitHub")}</div></header>
{"".join(sections)}
<footer>Research notes only. Nothing here is investment advice. Built with {link(REPO, "bottleneck-radar")}; the idea comes from a TikTok by {link("https://www.tiktok.com/@angusthenontechnical", "Angus the Nontechnical")}.</footer>
</main><div id="tip" class="tip" role="status" hidden></div><script>{JS}</script></body></html>
"""


def run() -> None:
    months = sorted(p.name for p in DATA.glob("20[0-9][0-9]-[01][0-9]") if (p / "demand.json").exists() and (p / "supply.json").exists())
    if not months:
        raise SystemExit("No month in data/ has demand.json and supply.json yet. Run `radar demand` and `radar supply` first.")
    month = months[-1]
    folder = DATA / month
    books = sorted(DATA.glob("13f/*/*.json"))
    call_path = folder / "bottleneck.json"
    owners = yaml.safe_load((CONFIG / "owners.yaml").read_text())
    page = render(
        month,
        read_json(folder / "demand.json"),
        read_json(folder / "supply.json"),
        read_json(books[-1]) if books else None,
        read_json(call_path) if call_path.exists() else None,
        owners,
    )
    path = write_text(SITE / "index.html", page)
    print(f"Dashboard for {month_name(month)}: {path.relative_to(ROOT)} ({len(page) / 1024:.0f} KB)")
