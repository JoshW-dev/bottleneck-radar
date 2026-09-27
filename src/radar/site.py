"""Static dashboard: renders the public outputs in data/ into site/index.html for Vercel.

Design references live in docs/taste/ (stripe.com and ramp.com). Color is reserved for
data: the chrome stays in blue-tinted neutrals, and the validated series colors only
appear in charts and on the globe. Everything on the page comes from data/, so nothing
about your brokerage account can reach it.
"""

from __future__ import annotations

import csv
import html
import io
import json
import math
from datetime import date, datetime, timedelta
from typing import Any, Callable

import yaml

from . import geo
from .config import CONFIG, DATA, ROOT
from .store import read_json, write_text

SITE = ROOT / "site"
REPO = "https://github.com/JoshW-dev/bottleneck-radar"
GLOBE_JS = "https://cdn.jsdelivr.net/npm/globe.gl@2.46.2/dist/globe.gl.min.js"

# Series colors, checked with the dataviz validator on white and on the night band (#0a1428).
LIGHT = {"memory": "#2a78d6", "chips": "#1baf7a", "power": "#eb6834"}
NIGHT = {"memory": "#3987e5", "chips": "#199e70", "power": "#d95926", "demand": "#ffffff"}
CONTEXT = "#8c97a8"
OTHER = "#c5cdd8"
BLUE_DARK, BLUE_LIGHT = "#256abf", "#86b6ef"
GROUPS = [  # the fund's holdings, colored by the input each company makes
    ("Memory", LIGHT["memory"], ["memory"]),
    ("Chips and packaging", LIGHT["chips"], ["advanced_chips"]),
    ("Power and grid", LIGHT["power"], ["gas_turbines", "grid_interconnection"]),
]
INPUT_LABELS = {
    "memory": "Memory chips",
    "advanced_chips": "Leading-edge chips",
    "gas_turbines": "Gas turbines",
    "grid_interconnection": "Grid connections",
}
PLACES = {  # where each input is made, and two big US data center markets
    "korea": ("S. Korea", 37.27, 127.44),
    "taiwan": ("Taiwan", 24.80, 120.97),
    "GE Vernova": ("Greenville", 34.85, -82.40),
    "Siemens Energy": ("Berlin", 52.52, 13.40),
    "Mitsubishi Heavy Industries": ("Takasago", 34.75, 134.79),
    "texas": ("Texas", 32.45, -99.73),
    "virginia": ("N. Virginia", 39.04, -77.49),
}
INDEX = [
    ("Overview", [("call", "This month's call"), ("picks", "Picks and tracking"), ("predictions", "Predictions")]),
    ("Demand", [("physical", "What the capex buys"), ("capex", "Capex by company")]),
    ("Supply", [("memory", "Memory chips"), ("taiwan", "Taiwan export orders"), ("turbines", "Gas turbines"), ("grid", "Grid connections")]),
    ("Positioning", [("book", "The fund's book")]),
    ("Method", [("method", "How it's built")]),
]


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


def short_month(period: str) -> str:
    return date.fromisoformat(f"{period}-01").strftime("%B")


def short_date(iso: str) -> str:
    return date.fromisoformat(iso[:10]).strftime("%b '%y")


def day_label(iso: str) -> str:
    return date.fromisoformat(iso[:10]).strftime("%b %-d")


def link(url: str | None, text: str = "source") -> str:
    return f'<a href="{e(url)}" rel="noopener">{e(text)}</a>' if url else ""


def csv_text(headers: list[str], rows: list[list[Any]]) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(headers)
    writer.writerows(rows)
    return out.getvalue()


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


def eyebrow(text: str) -> str:
    return f'<div class="eyebrow">{e(text)}</div>'


def tile(label: str, value: str, sub: str = "") -> str:
    return (
        f'<div class="tile"><div class="tile-label">{e(label)}</div><div class="tile-value">{e(value)}</div>'
        + (f'<div class="tile-sub">{e(sub)}</div>' if sub else "")
        + "</div>"
    )


def table(headers: list[str], rows: list[list[str]], numeric: set[int] = frozenset()) -> str:
    head = "".join(f'<th{" class=num" if i in numeric else ""}>{e(h)}</th>' for i, h in enumerate(headers))
    body = "".join(
        "<tr>" + "".join(f'<td{" class=num" if i in numeric else ""}>{cell}</td>' for i, cell in enumerate(row)) + "</tr>"
        for row in rows
    )
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def table_view(headers: list[str], rows: list[list[str]], numeric: set[int] = frozenset()) -> str:
    return f'<details class="tv"><summary>Show as a table</summary>{table(headers, rows, numeric)}</details>'


def prov(source_html: str, data_csv: str | None = None) -> str:
    """The source line, a copy button and the name ride inside every chart, so a cropped chart keeps its provenance."""
    copy = f'<button type="button" class="copy" data-csv="{e(data_csv)}">Copy data</button>' if data_csv else ""
    return f'<div class="prov"><p>{source_html}</p><div class="prov-end">{copy}<span class="wordmark">Bottleneck Radar</span></div></div>'


def line_chart(
    x_labels: list[str],
    series: list[dict[str, Any]],
    fmt: Callable[[float], str],
    *,
    y_max: float | None = None,
    height: int = 200,
    compact: bool = False,
    tick_fmt: Callable[[float], str] | None = None,
    area: bool = False,
    ticks: list[float] | None = None,
    markers: list[tuple[int, str]] | None = None,
) -> str:
    """Lines in a stretched SVG with non-scaling strokes; every label is HTML so it stays readable on phones.

    A series may set `dashed` (context lines), `dashed_until` (an index: dashed up to it, solid after)
    and `width`. With `area`, the first series gets a 8% wash. `markers` draws labeled vertical rules.
    """
    n = len(x_labels)
    top = y_max or nice_max(max(v for s in series for v in s["values"] if v is not None))
    ticks = ticks or ([top / 2, top] if compact else nice_ticks(top))
    tick_fmt = tick_fmt or fmt

    def x(i: int) -> float:
        return 0.0 if n == 1 else i / (n - 1) * 100

    def y(v: float) -> float:
        return 100 - v / top * 100

    def polyline(pts: str, color: str, width: float, dashed: bool) -> str:
        dash = ' stroke-dasharray="6 4"' if dashed else ""
        return (f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="{width}"{dash} '
                'stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"/>')

    def coords(pairs: list[tuple[float, float]]) -> str:
        return " ".join(f"{px * 10:.1f},{py * 10:.1f}" for px, py in pairs)

    shapes, dots, ends = [], [], []
    for k, s in enumerate(series):
        points = [(x(i), y(v)) for i, v in enumerate(s["values"]) if v is not None]
        pts = coords(points)
        if area and k == 0:
            shapes.append(
                f'<polygon points="{points[0][0] * 10:.1f},1000 {pts} {points[-1][0] * 10:.1f},1000" '
                f'fill="{s["color"]}" fill-opacity="0.08" stroke="none"/>'
            )
        width = s.get("width", 2)
        split = s.get("dashed_until")
        if split is None:
            shapes.append(polyline(pts, s["color"], width, bool(s.get("dashed"))))
        else:
            head = [(x(i), y(v)) for i, v in enumerate(s["values"]) if v is not None and i <= split]
            tail = [(x(i), y(v)) for i, v in enumerate(s["values"]) if v is not None and i >= split]
            shapes.append(polyline(coords(head), s["color"], width, True))
            if len(tail) > 1:
                shapes.append(polyline(coords(tail), s["color"], width, False))
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
            f'<span class="lc-end" style="top:{py:.2f}%"><i style="background:{s["color"]}"></i>'
            f"<small>{e(s['name'])}</small> {e(fmt(last))}</span>"
            for py, s, last in ends
        )

    grid = "".join(f'<div class="lc-grid" style="bottom:{t / top * 100:.2f}%"><span>{e(tick_fmt(t))}</span></div>' for t in ticks)
    rules = "".join(f'<div class="lc-mark" style="left:{x(i):.2f}%"><span>{e(label)}</span></div>' for i, label in markers or [])
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
        f'<div class="lc-plot" style="height:{height}px"><div class="lc-base"></div>{grid}{rules}'
        f'<svg class="draw" viewBox="0 0 1000 1000" preserveAspectRatio="none" aria-hidden="true">{"".join(shapes)}</svg>'
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


def sub_block(anchor: str, title: str, note: str, body: str) -> str:
    return f'<div class="sub" id="{anchor}"><h3>{e(title)}</h3><p class="note">{note}</p>{body}</div>'


def block(block_id: str, kicker: str, title: str, lead: str, body: str) -> str:
    return (
        f'<section class="block" id="{block_id}"><header class="block-head">{eyebrow(kicker)}'
        f"<h2>{e(title)}</h2><p>{lead}</p></header>{body}</section>"
    )


# ---------- hero and globe ----------


def _turbine_total(turbines: list[dict[str, Any]]) -> float:
    return sum(t.get("backlog_and_slots_gw") or (t.get("backlog_gw", 0) + t.get("slot_reservations_gw", 0)) for t in turbines)


def stats(supply: dict[str, Any]) -> list[dict[str, Any]]:
    """The four input figures in the hero strip, each tied to the globe arcs it lights up."""
    out = []
    if m := supply.get("memory"):
        out.append({"input": "memory", "color": NIGHT["memory"], "value": m["memory_usd"] / 1e9, "prefix": "$", "suffix": "B", "decimals": 1,
                    "label": f"Korean memory chip exports in {short_month(m['period'])}", "delta": f"{pct(m['memory_yoy'])} y/y",
                    "arcs_from": ["korea"], "pov": {"lat": 30, "lng": -160}})
    if o := supply.get("export_orders"):
        el = o["electronics"]
        out.append({"input": "advanced_chips", "color": NIGHT["chips"], "value": el["usd_millions"] / 1e3, "prefix": "$", "suffix": "B", "decimals": 1,
                    "label": f"Taiwan electronics export orders in {short_month(el['period'])}", "delta": f"{pct(el.get('yoy'))} y/y",
                    "arcs_from": ["taiwan"], "pov": {"lat": 26, "lng": -168}})
    if turbines := supply.get("gas_turbines"):
        gev = next((t for t in turbines if t["company"] == "GE Vernova"), None)
        years = f"GE Vernova: {gev['years_of_backlog']:g} years of orders" if gev and gev.get("years_of_backlog") else ""
        out.append({"input": "gas_turbines", "color": NIGHT["power"], "value": _turbine_total(turbines), "prefix": "", "suffix": " GW", "decimals": 0,
                    "label": "Gas turbine backlogs and reservations at GE Vernova, Siemens Energy and MHI", "delta": years,
                    "arcs_from": [t["company"] for t in turbines], "pov": {"lat": 36, "lng": -58}})
    if grid := supply.get("grid"):
        g = grid[0]
        total = (g.get("base_load_gw") or 0) + (g.get("studied_load_gw") or 0)
        out.append({"input": "grid_interconnection", "color": NIGHT["demand"], "value": total, "prefix": "", "suffix": " GW", "decimals": 0,
                    "label": "Large loads qualified for ERCOT's Batch Zero study in Texas", "delta": f"Update of {g['as_of']}",
                    "arcs_to": ["texas"], "pov": {"lat": 30, "lng": -100}})
    return out


def globe_payload(supply: dict[str, Any], figures: list[dict[str, Any]]) -> dict[str, Any]:
    nodes, arcs = [], []

    def node(node_id: str, place: str, color: str, radius: float, value: str, detail: str) -> None:
        label, lat, lng = PLACES[place]
        side = "l" if lng < -30 else "r"  # US labels point west, into the globe
        nodes.append({"id": node_id, "label": label, "lat": lat, "lng": lng, "side": side, "color": color, "r": round(radius, 3), "value": value, "detail": detail})

    if m := supply.get("memory"):
        node("korea", "korea", NIGHT["memory"], 0.62, usd(m["memory_usd"]), f"Memory chip exports, {month_name(m['period'])}")
        arcs += [{"from": "korea", "to": "texas", "color": NIGHT["memory"]}, {"from": "korea", "to": "virginia", "color": NIGHT["memory"]}]
    if o := supply.get("export_orders"):
        el = o["electronics"]
        node("taiwan", "taiwan", NIGHT["chips"], 0.62, usd(el["usd_millions"] * 1e6), f"Electronics export orders, {month_name(el['period'])}")
        arcs += [{"from": "taiwan", "to": "texas", "color": NIGHT["chips"]}, {"from": "taiwan", "to": "virginia", "color": NIGHT["chips"]}]
    turbines = supply.get("gas_turbines", [])
    most = max((_turbine_total([t]) for t in turbines), default=1)
    for t in turbines:
        if t["company"] not in PLACES:
            continue
        gw = _turbine_total([t])
        node(t["company"], t["company"], NIGHT["power"], 0.35 + 0.3 * math.sqrt(gw / most), f"{gw:g} GW", f"{t['company']} gas backlog and reservations")
        destinations = {"GE Vernova": ["texas", "virginia"], "Siemens Energy": ["virginia"], "Mitsubishi Heavy Industries": ["texas"]}[t["company"]]
        arcs += [{"from": t["company"], "to": d, "color": NIGHT["power"]} for d in destinations]
    if grid := supply.get("grid"):
        g = grid[0]
        node("texas", "texas", NIGHT["demand"], 0.6, f"{(g.get('base_load_gw') or 0) + (g.get('studied_load_gw') or 0):,.0f} GW", "Large loads in ERCOT's Batch Zero")
    else:
        node("texas", "texas", NIGHT["demand"], 0.5, "", "US data center market")
    node("virginia", "virginia", NIGHT["demand"], 0.45, "", "US data center market")

    for i, fig in enumerate(figures):
        fig["arcs"] = [
            k for k, a in enumerate(arcs) if a["from"] in fig.get("arcs_from", []) or a["to"] in fig.get("arcs_to", [])
        ]
        fig["nodes"] = sorted({arcs[k]["from"] for k in fig["arcs"]} | set(fig.get("arcs_to", [])))
    return {"nodes": nodes, "arcs": arcs, "figures": [{"arcs": f["arcs"], "nodes": f["nodes"], "pov": f["pov"]} for f in figures]}


def hero(demand: dict[str, Any], supply: dict[str, Any], call: dict[str, Any] | None, month: str) -> str:
    total = demand["total"]
    figures = stats(supply)
    payload = globe_payload(supply, figures)
    if call:
        head = f"{INPUT_LABELS[call['bottleneck']]} are this month's bottleneck."
        rest = call["headline"]
    else:
        head = "AI demand is outrunning supply."
        rest = "Every month this page follows the capex to find the tightest input."
    per_second = total["run_rate"] / (365.25 * 24 * 3600)
    cells = "".join(
        f'<button type="button" class="stat" data-i="{i}" aria-pressed="false">'
        f'<span class="stat-value" data-count="{f["value"]:.4f}" data-prefix="{e(f["prefix"])}" data-suffix="{e(f["suffix"])}" '
        f'data-decimals="{f["decimals"]}">{e(f["prefix"])}{f["value"]:,.{f["decimals"]}f}{e(f["suffix"])}</span>'
        f'<span class="stat-label"><i style="background:{f["color"]}"></i>{e(f["label"])}</span>'
        f'<span class="stat-delta">{e(f["delta"])}</span></button>'
        for i, f in enumerate(figures)
    )
    return f"""<section class="hero night" id="top"><div class="frame">
<div class="hero-grid">
<div class="hero-copy">
{eyebrow(f"Bottleneck radar · {month_name(month)}")}
<h1><span>{e(head)}</span> <span class="muted">{e(rest)}</span></h1>
<p class="lede">The five biggest cloud buyers spent <b>{e(usd(total["ttm"], 0))}</b> on capex over their last four reported quarters, {e(f"{total['ttm_growth']:.0%}")} more than the year before.</p>
<div class="ticker"><span class="tick-label" id="tick-label">Capex per second at the current run rate</span>
<span class="tick-value" id="ticker" data-rate="{per_second:.2f}">${per_second:,.0f}</span>
<span class="tick-note">Latest quarters annualize to {e(usd(total["run_rate"], 0))} a year.</span></div>
</div>
<div class="globe-panel" id="globe-panel" data-globe="{e(json.dumps(payload))}">
<div id="globe" role="img" aria-label="Globe with arcs from where memory chips, electronics and gas turbines are made to two US data center markets"></div>
<p class="globe-note">Arcs run from where each input is made to two big US data center markets. Drag to turn the globe.</p>
<p class="globe-fallback">The globe needs WebGL. The four figures below carry the same data.</p>
</div>
</div>
<div class="stats" id="stats">{cells}</div>
</div></section>"""


# ---------- sections ----------


def call_section(call: dict[str, Any] | None, owners: dict[str, Any]) -> str:
    if not call:
        return (
            f'<section class="call" id="call">{eyebrow("This month" + chr(39) + "s call")}'
            '<p class="call-pending">The model\'s pick for the tightest input shows up here after the first run with an Anthropic API key. '
            "Until then, the figures on this page are the raw inputs it will read.</p></section>"
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
    usage = call.get("usage") or {}
    when = f" on {day_label(call['generated'])}" if call.get("generated") else ""
    if usage.get("input_tokens") is not None:
        made = f"Made by {usage['model']}{when} ({usage['input_tokens']:,} tokens in, ${usage['cost_usd']:.2f})."
    elif usage:
        made = (f"Made by {usage['model']}{when} from this month's saved evidence packet, "
                "outside the monthly API run, and checked against the same schema.")
    else:
        made = ""
    return (
        f'<section class="call" id="call">{eyebrow("This month" + chr(39) + "s call · " + month_name(call["month"]))}'
        f'<h2 class="call-title"><span>{e(INPUT_LABELS[call["bottleneck"]])}.</span> <span class="muted">{e(call["headline"])}</span></h2>'
        f'<p class="call-why">{e(call["why"])}</p><div class="call-grid"><div><h3>Tightness by input</h3>{ranking}</div>'
        f'<div><h3>Who makes it</h3><div class="chips">{chips(call["owners"])}</div>'
        f'<h3>The consensus trade</h3><div class="chips">{chips(call["consensus_trade"])}</div></div></div>'
        f'<h3>What would prove this wrong</h3>{falsifiers}'
        f'<p class="note">Since last month: {e(call["change_vs_last_month"])} {e(made)}</p></section>'
    )


def index_rail(skip: set[str] = frozenset()) -> str:
    groups = "".join(
        f"<h4>{e(group)}</h4>" + "".join(f'<a href="#{anchor}">{e(label)}</a>' for anchor, label in items if anchor not in skip)
        for group, items in INDEX
    )
    return f'<nav class="index" aria-label="Indicators">{groups}</nav>'


STRATEGY_COLORS = {"picks": LIGHT["memory"], "clone": LIGHT["power"], "consensus": LIGHT["chips"], "sp500": CONTEXT}
MAKERS = {"memory": "memory", "advanced_chips": "chip", "gas_turbines": "gas turbine", "grid_interconnection": "grid equipment"}
COUNT_WORDS = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]


def ret(value: float | None, digits: int = 0) -> str:
    """A return as text; the page's own minus sign keeps negative numbers from reading as hyphens."""
    if value is None:
        return "n/a"
    return f"{value:+.{digits}%}".replace("-", "\u2212")


def next_weekday(iso: str) -> str:
    day = date.fromisoformat(iso) + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day.isoformat()


def picks_section(perf: dict[str, Any] | None) -> str:
    """The frozen picks with a reason for each, then this year's record against the 13F clone and two benchmarks."""
    if not perf or not perf.get("picks"):
        return ""
    p, series, days = perf["picks"], perf["series"], perf["days"]
    live = p["live_from"]
    starts = day_label(p["entry"] or next_weekday(p["published"]))
    rows = p["rows"]
    count = COUNT_WORDS[len(rows)] if len(rows) < len(COUNT_WORDS) else str(len(rows))
    maker = MAKERS.get(p.get("bottleneck", ""), "")
    if live:
        lead = (f"Since the {day_label(p['published'])} call the picks are {ret(series['picks']['since_call'], 1)}, against "
                f"{ret(series['consensus']['since_call'], 1)} for the consensus basket and {ret(series['sp500']['since_call'], 1)} for the S&P 500.")
    else:
        lead = (f"The {count} {maker} makers named in the {month_name(p['month'])} call, at equal weight. "
                f"They're up {ret(p['basket_ytd'])} this year in dollars, but the call came on {day_label(p['published'])}, after most of that move, "
                f"so their live record starts at the {starts} close.")

    table_rows = [
        [f'<span class="tick">{e(r["quote"])}</span>', f'{e(r["name"])}<span class="why">{e(r["role"])}</span>', e(f"{r['weight']:.0%}"),
         e(ret(r["ytd"])), e(ret(r["since_pick"], 1)) if r["since_pick"] is not None else f'<span class="muted">Starts {e(starts)}</span>']
        for r in rows
    ]
    listing = sub_block(
        "picks-list", "Who's in it",
        f"{e(p['rule'])} Research notes only. Nothing here is investment advice.",
        table(["Ticker", "Company and why it's in", "Weight", f"{perf['year']} so far", "Since the call"], table_rows, {2, 3, 4}),
    )

    order = ["picks", "clone", "consensus", "sp500"]
    shown = [k for k in order if k in series and any(v is not None for v in series[k]["values"])]
    live_index = days.index(live) if live else None
    chart_series = []
    for k in shown:
        item = {"name": series[k]["label"], "color": STRATEGY_COLORS[k], "values": series[k]["values"], "width": 2.5 if k == "picks" else 2}
        if k == "picks":
            item["dashed_until"] = live_index if live_index is not None else len(days) - 1
        if k == "sp500":
            item["dashed"], item["width"] = True, 1.75
        chart_series.append(item)
    top = nice_max(max(v for s_ in chart_series for v in s_["values"] if v is not None))
    step = nice_ticks(top - 100)[0] if top > 100 else top / 2
    ticks = [100 + step * i for i in range(int((top - 100) / step + 1e-9) + 1)]
    marker = (live_index, f"Called {day_label(p['published'])}") if live_index is not None else (len(days) - 1, f"Called {day_label(p['published'])}")
    chart = line_chart(
        [day_label(d) for d in days], chart_series, lambda v: ret(v / 100 - 1, 1),
        y_max=top, height=300, tick_fmt=lambda v: "0%" if abs(v - 100) < 1e-9 else ret(v / 100 - 1), ticks=ticks, markers=[marker],
    )
    consensus_names = ", ".join(r["quote"] for r in (perf.get("consensus") or {}).get("rows", []))
    labels = {"picks": "The picks, equal weight", "clone": "13F clone", "consensus": f"Consensus AI ({consensus_names})", "sp500": "S&P 500 (SPY)"}
    score_rows = []
    for k in shown:
        dd = series[k].get("max_drawdown") or {}
        drop = f"{ret(dd['change'])} ({day_label(dd['peak'])} to {day_label(dd['low'])})" if dd.get("peak") else "none"
        since = ret(series[k]["since_call"], 1) if series[k].get("since_call") is not None else ("Starts " + starts if k == "picks" else "")
        score_rows.append([f'<i class="key" style="background:{STRATEGY_COLORS[k]}"></i>{e(labels[k])}', e(ret(series[k]["ytd"])), e(drop), e(since)])
    month_ends = [i for i, d in enumerate(days) if i == 0 or i == len(days) - 1 or d[:7] != days[i + 1][:7]]
    tv_rows = [[e(days[i])] + [e(ret(series[k]["values"][i] / 100 - 1, 1)) if series[k]["values"][i] is not None else "" for k in shown] for i in month_ends]
    csv_rows = [[d] + [series[k]["values"][i] for k in shown] for i, d in enumerate(days)]
    books = (perf.get("clone") or {}).get("books", [])
    book_rows = [[e(b["period"]), e(b["filed"]), e(day_label(b["bought_on"])), e(str(b["positions"])), e(f"{b['bought']:.0%}")] for b in books]
    gaps = sorted({m for b in books for m in b["missing"]})
    clone_note = (f" Left out for lack of a price: {e(', '.join(gaps))}." if gaps else "")
    tracking = sub_block(
        "tracking", f"{perf['year']} so far, in dollars",
        f"The picks line is dashed before the call because nobody had picked those stocks yet. The 13F clone has no hindsight in it: "
        f"it buys each of {e((perf.get('clone') or {}).get('fund') or 'the fund')}'s filings at the first close after the filing date.",
        legend([(labels[k].split(" (")[0], STRATEGY_COLORS[k]) for k in shown], "line")
        + chart
        + table(["Line", f"{perf['year']} so far", "Largest drop", "Since the call"], score_rows, {1})
        + table_view(["Date"] + [series[k]["label"] for k in shown], tv_rows, set(range(1, len(shown) + 1)))
        + (f'<h3 class="gap">Filings the clone followed</h3>' + table(["Book", "Filed", "Bought at the close of", "Positions", "Priced"], book_rows, {3, 4})
           if book_rows else "")
        + prov(f"Daily closes from Yahoo Finance, adjusted for dividends and splits, to the {e(day_label(perf['as_of']))} close. Seoul and Tokyo "
               f"listings are converted to dollars at each day's rate. 13F books from EDGAR.{clone_note}",
               csv_text(["date"] + [f"{k}_index" for k in shown], csv_rows)),
    )
    return block("picks", f"Picks · updated each US trading day", "The picks", e(lead), listing + tracking)


STATUS = {  # reserved for prediction results, apart from the series colors
    "right": ("#138a5e", "Came true", "✓"),
    "wrong": ("#cf3a2f", "Missed", "✗"),
    "void": (OTHER, "Void, no data", ""),
    "open": (CONTEXT, "Open", ""),
}
QUESTIONS = {
    "memory": "Is memory still short?",
    "buildout": "Is the buildout still growing?",
    "power": "Is power the next squeeze?",
    "call": "Do the call and the fund stay on memory?",
    "picks": "Do the picks pay?",
}


def fmt_prediction(unit: str, value: Any) -> str:
    if value is None:
        return ""
    if unit == "pct":
        return ret(value, 1 if abs(value) < 0.1 else 0)
    if unit == "points":
        return f"{value * 100:+.1f} pts".replace("-", "−")
    if unit == "usd":
        return f"${value:,.2f}"
    if unit == "usd_b":
        return usd(value)
    if unit == "gw":
        return f"{value:g} GW"
    if unit == "share":
        return f"{value:.0%}"
    return INPUT_LABELS.get(value, str(value))


def utc_label(stamp: str) -> str:
    moment = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ")
    return f"{moment:%H:%M} UTC on {moment:%b %-d, %Y}"


def prediction_timeline(numbered: list[tuple[int, dict[str, Any]]], results: dict[str, Any], start: str, today: str) -> str:
    """Each prediction as a numbered dot on its due date, filled in once it's checked."""
    first = date.fromisoformat(start)
    last = max(date.fromisoformat(p["due"]) for _, p in numbered) + timedelta(days=6)
    span = (last - first).days

    def left(day: date) -> str:
        return f"{(day - first).days / span * 100:.2f}%"

    levels: list[date] = []  # the latest due date placed on each row, so close dates stack instead of overlapping
    dots = []
    for n, p in numbered:
        due = date.fromisoformat(p["due"])
        level = next((i for i, d in enumerate(levels) if (due - d).days >= 4), len(levels))
        if level == len(levels):
            levels.append(due)
        levels[level] = due
        status = results.get(p["id"], {}).get("status", "open")
        color, label, _ = STATUS[status]
        tip = {"title": f"{n}. Due {day_label(p['due'])}", "rows": [[f"{p['confidence']:.0%}", p["statement"], color], ["", label, "transparent"]]}
        dots.append(
            f'<span class="pt-dot {status}" style="left:{left(due)};bottom:{level * 24}px;--c:{color}" tabindex="0" '
            f'data-tip="{e(json.dumps(tip))}">{n}</span>'
        )
    months = []
    day = date(first.year, first.month, 1)
    while day <= last:
        if day >= first:
            months.append(f'<span style="left:{left(day)}">{day:%b}</span>')
        day = date(day.year + day.month // 12, day.month % 12 + 1, 1)
    now_mark = ""
    t = date.fromisoformat(today)
    if first <= t <= last:
        now_mark = f'<span class="pt-now" style="left:{left(t)}"><b>Today</b></span>'
    height = len(levels) * 24 + 8
    return (
        f'<div class="pt-wrap"><div class="pt" role="img" aria-label="Due dates of the predictions">'
        f'<div class="pt-plot" style="height:{height}px">{now_mark}{"".join(dots)}</div>'
        f'<div class="pt-axis">{"".join(months)}</div></div></div>'
    )


def predictions_section(preds: dict[str, Any] | None) -> str:
    """The dated predictions, when each comes due, and how many have come true against how many were expected to."""
    if not preds or not preds.get("sets"):
        return ""
    sets, checked = preds["sets"], preds.get("results") or {}
    results, summary = checked.get("results", {}), checked.get("summary") or {}
    numbered = list(enumerate([p for s in sets for p in s["predictions"]], start=1))
    total = len(numbered)
    first = sets[0]
    made = utc_label(first["made_at"])
    lead = (f"Each of these {total} predictions has a due date and a stated chance of coming true, and they were made at {made}, "
            "before any of them could be checked. The code checks each one against the data when it comes due and stamps the result "
            "with the time. A result never changes once it's recorded.")

    resolved, right = summary.get("resolved") or 0, summary.get("right") or 0
    open_ones = sorted((p["due"], p["id"]) for _, p in numbered if results.get(p["id"], {}).get("status", "open") == "open")
    if open_ones:
        next_due = open_ones[0][0]
        same = sum(1 for d, _ in open_ones if d == next_due)
        next_note = f"Next: {COUNT_WORDS[same] if same < len(COUNT_WORDS) else same} due {day_label(next_due)}"
    else:
        next_note = "All checked"
    confidence_sum = sum(p["confidence"] for _, p in numbered)
    tiles = '<div class="tiles three">' + "".join([
        tile("Checked", f"{resolved} of {total}", next_note),
        tile("Came true", f"{right} of {resolved}" if resolved else "None yet",
             f"About {summary['expected_right']:.1f} should have, going by the chances" if resolved
             else f"About {confidence_sum:.1f} of {total} should, going by the chances"),
        tile("Brier score", f"{summary['brier']:.2f}" if resolved else "None yet",
             "0 is perfect. Saying 50% every time scores 0.25."),
    ]) + "</div>"

    today = (checked.get("checked_at") or first["made_at"])[:10]
    legend_html = ('<div class="legend">' + "".join(
        f'<span><i class="pt-key {k}" style="--c:{STATUS[k][0]}"></i>{e(STATUS[k][1])}</span>' for k in ("open", "right", "wrong", "void")
    ) + "</div>")
    timeline = sub_block(
        "prediction-dates", "When each one comes due",
        "Each dot is a prediction, numbered as in the table below, placed on the day its data is due. It fills in once the code has checked it.",
        legend_html + prediction_timeline(numbered, results, first["made_at"][:10], today),
    )

    rows_html = []
    for group, question in QUESTIONS.items():
        members = [(n, p) for n, p in numbered if p["group"] == group]
        if not members:
            continue
        rows_html.append(f'<tr class="grp"><th colspan="5" scope="colgroup">{e(question)}</th></tr>')
        for n, p in members:
            r = results.get(p["id"], {"status": "open"})
            status = r["status"]
            color, label, mark = STATUS[status]
            if status in ("right", "wrong"):
                detail = fmt_prediction(p["unit"], r.get("value"))
                when = f", {day_label(r['observed'])}" if r.get("observed") else ""
                result = f'<b class="res" style="color:{color}">{mark} {e(label)}</b><span class="why">{e(detail + when)}</span>'
            elif status == "void":
                result = f'<span class="muted">{e(label)}</span><span class="why">{e(r.get("note", ""))}</span>'
            elif r.get("so_far") is not None:
                result = f'<span class="muted">Open</span><span class="why">{e(fmt_prediction(p["unit"], r["so_far"]))} so far</span>'
            else:
                result = '<span class="muted">Open</span>'
            rows_html.append(
                f'<tr><td class="num">{n}</td><td>{e(p["statement"])}<span class="why">{e(p["why"])}</span></td>'
                f'<td class="num nowrap">{e(day_label(p["due"]))}</td><td class="num">{p["confidence"]:.0%}</td><td>{result}</td></tr>'
            )
    head = '<tr><th class="num">#</th><th>Prediction</th><th class="num">Due</th><th class="num">Chance</th><th>Result</th></tr>'
    listing_table = f'<div class="table-wrap"><table class="preds"><thead>{head}</thead><tbody>{"".join(rows_html)}</tbody></table></div>'

    csv_rows = [[n, p["id"], p["group"], p["due"], p["confidence"], results.get(p["id"], {}).get("status", "open"),
                 results.get(p["id"], {}).get("value", ""), results.get(p["id"], {}).get("resolved_at", ""), p["statement"]] for n, p in numbered]
    set_notes = []
    for s in sets:
        path = f"data/predictions/{s['set']}.json"
        intact = next((x.get("intact", True) for x in checked.get("sets", []) if x["set"] == s["set"]), True)
        warning = "" if intact else " <b>The file no longer matches this fingerprint, so it was edited after it was frozen.</b>"
        set_notes.append(
            f"Set {e(s['set'])} was made by {e(s['made_by'])} at {e(utc_label(s['made_at']))}. {e(s.get('note', ''))} "
            f"SHA-256 {e(s['sha256'][:16])}: the checker recomputes it on every run, and the {link(f'{REPO}/commits/main/{path}', 'file history')} "
            f"on GitHub shows when it was committed.{warning}"
        )
    last_check = f" Last checked at {e(utc_label(checked['checked_at']))}." if checked.get("checked_at") else ""
    listing = sub_block(
        "prediction-list", "The predictions",
        "Chance is how likely each one looked when it was made. A good forecaster's 70% calls come true about 70% of the time, "
        "so the score to watch is how the count that came true compares with the count expected. Research notes only. Nothing here is investment advice.",
        listing_table + prov(" ".join(set_notes) + last_check,
                             csv_text(["n", "id", "group", "due", "confidence", "status", "value", "resolved_at", "statement"], csv_rows)),
    )
    return block("predictions", "Predictions · checked each US trading day", "Predictions", e(lead), tiles + timeline + listing)


def demand_section(demand: dict[str, Any]) -> str:
    total, companies = demand["total"], demand["companies"]
    p, added = demand["physical"]["ttm"], demand["physical"]["added_vs_prior_ttm"]
    steps = [
        ("Capex, last 4 quarters", usd(total["ttm"], 0), f"{pct(total['ttm_growth'])} y/y"),
        ("Data center power", f"{p['gw']:.1f} GW", f"+{added['gw']:.1f} GW on the prior year"),
        ("GPUs", f"{p['gpus'] / 1e6:.1f}M", f"+{added['gpus'] / 1e6:.1f}M on the prior year"),
        ("HBM memory", f"{p['hbm_gb'] / 1e9:.2f}B GB", f"+{added['hbm_gb'] / 1e9:.2f}B GB on the prior year"),
        ("Gas turbine equivalents", f"{p['turbines_7ha']:,.0f}", "GE 7HA.03 units, simple cycle"),
    ]
    chain = '<div class="chain">' + "".join(
        f'<div class="chain-step"><div class="chain-label">{e(label)}</div><div class="chain-value">{e(value)}</div><div class="chain-sub">{e(sub)}</div></div>'
        for label, value, sub in steps
    ) + "</div>"
    unverified = [k for k, a in demand["assumptions"].items() if a.get("status") == "unverified"]
    physical = sub_block(
        "physical",
        "What the capex buys",
        f"Each step converts the one before it with a factor from {link(REPO + '/blob/main/config/assumptions.yaml', 'config/assumptions.yaml')}. "
        f"{len(unverified)} of the factors still lack a primary source, so read these as rough sizes.",
        chain + prov("Capex: SEC XBRL cash-flow facts, latest 10-Q or 10-K per company. Conversion factors: Epoch AI, NVIDIA, GE Vernova, Crusoe."),
    )

    order = sorted(companies, key=lambda t: -companies[t]["latest"]["value"])
    y_max = nice_max(max(q["value"] for c in companies.values() for q in c["quarters"]) / 1e9)
    panels, rows, csv_rows = [], [], []
    for t in order:
        c = companies[t]
        qs = c["quarters"]
        chart = line_chart(
            [short_date(q["end"]) for q in qs],
            [{"name": c["name"], "color": LIGHT["memory"], "values": [q["value"] / 1e9 for q in qs]}],
            lambda v: f"${v:,.1f}B", y_max=y_max, height=120, compact=True, tick_fmt=lambda v: f"${v:,.0f}B", area=True,
        )
        panels.append(
            f'<div class="sm"><div class="sm-head"><span>{e(c["name"])}</span><b>{e(usd(c["latest"]["value"]))}</b></div>'
            f'<div class="sm-sub">Quarter to {e(short_date(c["latest"]["end"]))} · {e(pct(c.get("yoy")))} y/y</div>{chart}</div>'
        )
        rows += [[e(c["name"]), e(q["end"]), e(usd(q["value"]))] for q in qs]
        csv_rows += [[c["name"], q["start"], q["end"], q["value"]] for q in qs]
    fastest = max(order, key=lambda t: companies[t].get("yoy") or -1)
    quotes = "".join(
        f'<blockquote>{e(q)}<cite>{e(companies[t]["name"])}, {link(companies[t]["guidance"]["url"], "earnings release")} filed {e(companies[t]["guidance"]["filed"])}</cite></blockquote>'
        for t in order
        for q in companies[t]["guidance"].get("forward", [])
    )
    capex = sub_block(
        "capex",
        "Capex by company",
        f"Quarterly cash capex on one scale. {e(companies[fastest]['name'])} grew fastest, {e(pct(companies[fastest]['yoy']))} on the same quarter a year earlier. "
        "Oracle's quarters end in Feb, May, Aug and Nov.",
        f'<div class="sm-grid">{"".join(panels)}</div>'
        + table_view(["Company", "Quarter end", "Capex"], rows, {2})
        + prov("SEC XBRL company facts: PaymentsToAcquirePropertyPlantAndEquipment (Amazon: PaymentsToAcquireProductiveAssets). "
               "Year-to-date values are differenced into quarters.", csv_text(["company", "quarter_start", "quarter_end", "capex_usd"], csv_rows))
        + (f'<div class="quotes"><h4>Guidance in the filings</h4>{quotes}</div>' if quotes else ""),
    )
    lead = (f"The five biggest cloud buyers spent {e(usd(total['ttm'], 0))} in a year, {e(pct(total['ttm_growth']))} on the year before. "
            "Here is what that money buys in physical terms.")
    return block("demand", "Demand · SEC filings", "Demand", lead, physical + capex)


def supply_section(supply: dict[str, Any]) -> str:
    parts, leads = [], []
    if m := supply.get("memory"):
        tiles = [
            tile("Korean memory chip exports", usd(m["memory_usd"]), f"{month_name(m['period'])} · {pct(m['memory_yoy'])} on {usd(m['memory_year_ago_usd'])}"),
            tile("All Korean chip exports", usd(m["chips_usd"]), f"{pct(m['chips_yoy'])} y/y"),
        ]
        if "ddr5_16gb_contract_usd" in m:
            tiles.append(tile("DDR5 16Gb contract price", f"${m['ddr5_16gb_contract_usd']:.2f}", f"{pct(m['ddr5_16gb_yoy'])} y/y"))
        if "nand_128gb_contract_usd" in m:
            tiles.append(tile("NAND 128Gb contract price", f"${m['nand_128gb_contract_usd']:.2f}", f"{pct(m['nand_128gb_yoy'])} y/y"))
        multiple = m["memory_usd"] / m["memory_year_ago_usd"] if m.get("memory_year_ago_usd") else None
        parts.append(sub_block(
            "memory", "Memory chips",
            f"Korea shipped {multiple:.1f} times as much memory in {short_month(m['period'])} as a year earlier." if multiple else "",
            f'<div class="tiles four">{"".join(tiles)}</div>'
            + prov(f"Korean trade ministry (MOTIR) monthly release, {link(m['source'], 'page')} and {link(m['pdf'], 'PDF')}. Figures converted from 억 달러 (US$100M)."),
        ))
        if multiple:
            leads.append(f"Korean memory exports are up {multiple:.1f}x on the year")

    if o := supply.get("export_orders"):
        el, ict = o["electronics"], o["ict"]
        history = list(el["history"])
        ict_by_period = dict(ict["history"])
        x = [date.fromisoformat(p + "-01").strftime("%b '%y") for p, _ in history]
        chart = line_chart(
            x,
            [
                {"name": "Electronics", "color": LIGHT["memory"], "values": [v / 1e3 for _, v in history], "width": 2.5},
                {"name": "ICT", "color": CONTEXT, "values": [ict_by_period.get(p, 0) / 1e3 or None for p, _ in history], "dashed": True, "width": 1.75},
            ],
            lambda v: f"${v:,.1f}B",
            tick_fmt=lambda v: f"${v:,.0f}B",
            height=240,
            area=True,
        )
        rows = [[e(p), e(usd(v * 1e6)), e(usd(ict_by_period.get(p, 0) * 1e6))] for p, v in history]
        csv_rows = [[p, v, ict_by_period.get(p)] for p, v in history]
        parts.append(sub_block(
            "taiwan", "Taiwan export orders",
            f"Electronics orders were {e(usd(el['usd_millions'] * 1e6))} in {short_month(el['period'])}, {e(pct(el.get('yoy')))} on the year. "
            "Orders measure demand for Taiwanese electronics, so they stand in for chips until a direct supply series exists.",
            legend([("Electronics", LIGHT["memory"]), ("ICT products", CONTEXT)], "line") + chart
            + table_view(["Month", "Electronics", "ICT products"], rows, {1, 2})
            + prov(f"Taiwan Ministry of Economic Affairs open data, US$ millions a month ({link(el['url'], 'electronics')}, {link(ict['url'], 'ICT')}).",
                   csv_text(["month", "electronics_usd_millions", "ict_usd_millions"], csv_rows)),
        ))

    if turbines := supply.get("gas_turbines"):
        rows, table_rows, csv_rows = [], [], []
        for t in turbines:
            firm = t.get("backlog_gw") or 0
            slots = t.get("slot_reservations_gw") or 0
            if not firm and t.get("backlog_and_slots_gw"):
                firm = t["backlog_and_slots_gw"]
            years = f"{t['years_of_backlog']:g} years of shipments" if t.get("years_of_backlog") else "shipments not disclosed"
            rows.append({
                "label": t["company"], "sub": years, "value_text": f"{firm + slots:g} GW",
                "segments": [{"name": "Firm backlog", "value": firm, "color": BLUE_DARK}, {"name": "Slot reservations", "value": slots, "color": BLUE_LIGHT}],
            })
            table_rows.append([e(t["company"]), e(f"{firm:g}"), e(f"{slots:g}"), e(t.get("quarter") or t.get("as_of")), link(t["source"], t["method"])])
            csv_rows.append([t["company"], firm, slots, t.get("quarter") or t.get("as_of"), t["source"]])
        rows.sort(key=lambda r: -sum(s["value"] for s in r["segments"]))
        max_total = max(sum(s["value"] for s in r["segments"]) for r in rows)
        lead_row = rows[0]
        parts.append(sub_block(
            "turbines", "Gas turbines",
            f"{e(lead_row['label'])} has {e(lead_row['value_text'])} committed, {e(lead_row['sub'])} at its latest quarterly pace. "
            "Years of shipments divides backlog plus reservations by the latest quarter's shipments times four.",
            legend([("Firm backlog", BLUE_DARK), ("Slot reservations", BLUE_LIGHT)])
            + hbars(rows, max_total, lambda v: f"{v:g} GW")
            + table_view(["Maker", "Firm backlog (GW)", "Slot reservations (GW)", "As of", "Source"], table_rows, {1, 2})
            + prov("GE Vernova: earnings release on EDGAR, parsed. Siemens Energy and MHI: entered by hand from their results decks. "
                   "MHI doesn't report reservations or shipments in GW.",
                   csv_text(["maker", "firm_backlog_gw", "slot_reservations_gw", "as_of", "source"], csv_rows)),
        ))
        if " years" in lead_row["sub"]:
            leads.append(f"{lead_row['label']} has about {lead_row['sub'].split(' years')[0]} years of turbine orders booked")

    if grid := supply.get("grid"):
        g = grid[0]
        tiles = [
            tile("Qualified as base load", f"{g['base_load_gw']:g} GW", f"{g['base_load_projects']} projects"),
            tile("Qualified as studied load", f"{g['studied_load_gw']:g} GW", f"{g['studied_load_projects']} projects"),
        ]
        parts.append(sub_block(
            "grid", "Grid connections",
            e(g.get("note", "")),
            f'<div class="tiles two">{"".join(tiles)}</div>' + prov(f"ERCOT Batch Zero update of {e(g['as_of'])} ({link(g['source'], 'PDF')}), entered by hand."),
        ))
    if errors := supply.get("errors"):
        parts.append('<p class="note">Sources that failed this run: ' + e(", ".join(err["source"] for err in errors)) + ".</p>")
    lead = (". ".join(leads) + ".") if leads else "Supply-side figures for each input."
    return block("supply", "Supply · trade data and filings", "Supply", e(lead), "".join(parts))


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
        label, _ = ticker_group.get((w["ticker"] or "").upper(), ("Other", OTHER))
        shares[label] = shares.get(label, 0) + w["weight"]
    palette = {label: color for label, color, _ in GROUPS} | {"Other": OTHER}
    order = [label for label, _, _ in GROUPS if label in shares] + (["Other"] if "Other" in shares else [])
    stack = "".join(
        f'<span style="flex:{shares[k]:.6f} 1 0;background:{palette[k]}" tabindex="0" '
        f'data-tip="{e(json.dumps({"title": k, "rows": [[f"{shares[k]:.1%}", "of the long book", palette[k]]]}))}"></span>'
        for k in order
    )
    top, rest = weights[:12], weights[12:]
    rows = []
    for w in top:
        label, color = ticker_group.get((w["ticker"] or "").upper(), ("Other", OTHER))
        rows.append({"label": w["ticker"] or w["name"], "sub": w["name"].title(), "value_text": f"{w['weight']:.1%}",
                     "segments": [{"name": label, "value": w["weight"], "color": color}]})
    if rest:
        rows.append({"label": f"{len(rest)} others", "sub": "Smaller positions", "value_text": f"{sum(w['weight'] for w in rest):.1%}",
                     "segments": [{"name": "Other", "value": sum(w["weight"] for w in rest), "color": OTHER}]})
    bars = hbars(rows, max(r["segments"][0]["value"] for r in rows), lambda v: f"{v:.1%}")
    table_rows = [[e(w["ticker"] or ""), e(w["name"].title()), e(usd(w["value"])), e(f"{w['weight']:.2%}")] for w in weights]
    lead = (f"{shares.get('Memory', 0):.0%} of {e(book['fund'])}'s long stock book sits with memory makers, as of "
            f"{e(date.fromisoformat(book['period']).strftime('%B %-d, %Y'))}.")
    body = (
        f'<div class="sub" id="book-mix"><h3>Book by input</h3><div class="stack" role="img" aria-label="Share of the book by input">{stack}</div>'
        + legend([(f"{k} {shares[k]:.1%}", palette[k]) for k in order])
        + '<h3 class="gap">Largest positions</h3>'
        + bars
        + table_view(["Ticker", "Company", "Value", "Weight"], table_rows, {2, 3})
        + prov(f"13F information table filed {e(book['filed'])} ({link(book['source'], 'EDGAR')}), tickers from OpenFIGI. "
               "A 13F arrives 45 days after the quarter ends and leaves out shorts, cash and leverage.",
               csv_text(["ticker", "company", "value_usd", "weight"], [[w["ticker"], w["name"], w["value"], w["weight"]] for w in weights]))
        + "</div>"
    )
    return block("book", "Positioning · 13F", "The fund's book", lead, body)


FACTORS = {  # (label, how to show the value)
    "datacenter_share_of_capex": ("Share of capex spent on AI data centers", lambda v: f"{v:.0%}"),
    "capex_per_gw": ("Capex per GW of facility power", lambda v: usd(v)),
    "it_power_share": ("Share of power reaching IT (1/PUE)", lambda v: f"{v:.0%}"),
    "kw_per_gpu": ("IT power per GPU", lambda v: f"{v:g} kW"),
    "hbm_gb_per_gpu": ("HBM per GPU", lambda v: f"{v:g} GB"),
    "sqft_per_mw": ("Floor space per MW", lambda v: f"{v:,.0f} sq ft"),
    "mw_per_turbine": ("Power per gas turbine", lambda v: f"{v:g} MW"),
}


def method_section(demand: dict[str, Any]) -> str:
    rows = []
    for key, a in demand["assumptions"].items():
        status = "unverified" if a.get("status") == "unverified" else "assumption" if a.get("status") == "assumption" else link(a.get("url"), "sourced")
        label, show = FACTORS.get(key, (key.replace("_", " "), lambda v: f"{v:,}"))
        rows.append([e(label), e(show(a["value"])), e(a.get("note") or a.get("source") or ""), status])
    body = (
        "<p>Each month a script pulls hyperscaler capex from SEC filings, memory exports from Korea's trade ministry, export orders "
        "from Taiwan's economics ministry and turbine backlogs from GE Vernova's earnings release, then rebuilds this page. "
        f"The code, the data and every past month are on {link(REPO, 'GitHub')}.</p>"
        f'<div class="sub" id="factors"><h3>Conversion factors</h3>{table(["Factor", "Value", "Note", "Status"], rows, {1})}</div>'
    )
    return block("method", "Method", "How it's built", "Code pulls every number. A model only writes the monthly call.", body)


# ---------- page ----------

FONTS = "https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Host+Grotesk:wght@300;400;500;600&display=swap"

CSS = """
:root{color-scheme:light;--paper:#fff;--alt:#f7f9fc;--ink:#07182e;--slate:#52627a;--muted:#6b7a90;--rule:#e4ebf3;--grid:#eef2f7;
--night:#0a1428;--night-rule:#1a2745;--night-slate:#8fa2c6;--night-idle:#6f84b3;--night-label:#aebfdc;--night-mono:#7f95c4;
--series:#2a78d6;--sans:"Host Grotesk",ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;
--mono:"DM Mono",ui-monospace,"SF Mono",Menlo,Consolas,monospace;--frame:1200px;--gutter:24px}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:76px}
body{margin:0;background:var(--paper);color:var(--ink);font:400 16px/1.6 var(--sans);-webkit-font-smoothing:antialiased}
a{color:inherit;text-decoration:underline;text-decoration-color:#b9c6d6;text-underline-offset:3px;transition:text-decoration-color .24s,color .24s}
a:hover{text-decoration-color:currentColor}
:focus-visible{outline:2px solid var(--series);outline-offset:3px;border-radius:2px}
h1,h2,h3{text-wrap:balance}
.frame{max-width:calc(var(--frame) + 2 * var(--gutter));margin:0 auto;padding-inline:var(--gutter);border-inline:1px solid var(--rule)}
.eyebrow{font:500 12px/1.4 var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--slate)}
.muted{color:var(--slate)}
.nav{position:sticky;top:0;z-index:30;background:rgba(255,255,255,.88);-webkit-backdrop-filter:saturate(1.4) blur(12px);backdrop-filter:saturate(1.4) blur(12px);border-bottom:1px solid var(--rule)}
.nav .frame{display:flex;align-items:center;gap:14px;height:60px}
.brand{font:600 16px/1 var(--sans);letter-spacing:-.01em;text-decoration:none}
.tag{font:500 11px/1 var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--slate);border:1px solid var(--rule);border-radius:4px;padding:5px 7px}
.nav-links{margin-left:auto;display:flex;gap:24px;font-size:14px}.nav-links a{text-decoration:none;color:var(--slate)}.nav-links a:hover{color:var(--ink)}
.night{background:var(--night);color:#fff;overflow-x:clip}.night .frame{border-color:var(--night-rule)}
.hero-grid{display:grid;grid-template-columns:minmax(0,1.05fr) minmax(0,.95fr);gap:24px;align-items:stretch}
.hero-copy{padding-block:88px 56px;position:relative;z-index:2}
.hero .eyebrow{color:var(--night-mono)}
.hero h1{font:300 clamp(36px,4.4vw,56px)/1.08 var(--sans);letter-spacing:-.022em;margin:20px 0 24px}
.hero h1 .muted{color:var(--night-slate)}
.lede{font:300 18px/1.6 var(--sans);color:#c7d3e8;max-width:540px;margin:0}.lede b{font-weight:500;color:#fff}
.ticker{margin-top:32px;display:grid;gap:4px;padding:16px 18px;border:1px solid var(--night-rule);border-radius:6px;max-width:440px}
.tick-label{font:500 11px/1.4 var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--night-mono)}
.tick-value{font:400 30px/1.2 var(--mono);font-variant-numeric:tabular-nums;letter-spacing:-.01em}
.tick-note{font-size:13px;color:var(--night-slate)}
.globe-panel{position:relative;min-height:600px;margin-right:calc(-1 * var(--gutter));clip-path:inset(-40px -400px 0 -400px)}
#globe{position:absolute;top:0;right:-90px;bottom:-210px;left:-90px;cursor:grab}#globe:active{cursor:grabbing}
.globe-note{position:absolute;right:var(--gutter);top:28px;margin:0;font:400 11px/1.5 var(--mono);color:var(--night-mono);max-width:230px;text-align:right;z-index:2;pointer-events:none}
.globe-fallback{display:none;position:absolute;inset:auto 0 50% 0;margin:0;color:var(--night-slate);font-size:14px}
.no-globe .globe-fallback{display:block}.no-globe .globe-note{display:none}
.gl-pin{position:relative;width:0;height:0;pointer-events:none}
.gl-label{position:absolute;left:0;top:0;font:500 10.5px/1 var(--mono);letter-spacing:.06em;text-transform:uppercase;color:#8ea3cc;white-space:nowrap;transform:translate(10px,-50%);transition:color .4s,opacity .4s}
.gl-label.l{transform:translate(calc(-100% - 10px),-50%)}.gl-label.on{color:#fff}.gl-label:not(.on){opacity:.45}
.stats{display:grid;grid-template-columns:repeat(4,1fr);border-top:1px solid var(--night-rule)}
.stat{appearance:none;background:none;border:0;border-left:1px solid var(--night-rule);color:inherit;font:inherit;text-align:left;padding:30px 24px 36px;cursor:pointer;position:relative;display:flex;flex-direction:column;justify-content:flex-start}
.stat:first-child{border-left:0;padding-left:0}
.stat::before{content:"";position:absolute;left:0;right:0;top:-1px;height:1px;background:#fff;opacity:0;transition:opacity .4s}
.stat:first-child::before{left:0}.stat.is-lit::before,.all-lit .stat::before{opacity:.9}
.stat-value{display:block;font:300 clamp(34px,3.4vw,48px)/1.08 var(--sans);letter-spacing:-.02em;color:var(--night-idle);transition:color .4s;white-space:nowrap}
.stat.is-lit .stat-value,.all-lit .stat-value{color:#fff}
.stat-label{display:block;margin-top:12px;font-size:14px;line-height:1.45;color:var(--night-label)}
.stat-label i{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:8px;vertical-align:1px}
.stat-delta{display:block;margin-top:8px;font:500 12px/1.4 var(--mono);color:var(--night-mono)}
.call{max-width:var(--frame);margin:0 auto;padding-block:72px 64px}
.call-pending{font:300 22px/1.5 var(--sans);color:var(--slate);max-width:760px;margin:14px 0 0}
.call-title{font:300 clamp(30px,3.4vw,44px)/1.15 var(--sans);letter-spacing:-.02em;margin:14px 0 18px}.call-title .muted{color:var(--slate)}
.call-why{font:300 18px/1.6 var(--sans);max-width:760px}
.call-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:32px;margin-top:8px}
.call h3,.sub h3{font:500 18px/1.3 var(--sans);margin:28px 0 8px}
.rank{display:grid;grid-template-columns:150px 1fr auto;gap:12px;align-items:center;font-size:14px;margin:8px 0}
.meter{display:flex;gap:2px}.meter i{flex:1;height:6px;background:#dbe5f3}.meter i.on{background:var(--ink)}.meter i:last-child{border-radius:0 3px 3px 0}
.chips{display:flex;flex-wrap:wrap;gap:6px}.chip{border:1px solid var(--rule);border-radius:4px;padding:3px 9px;font-size:14px}.chip small{font-family:var(--mono);color:var(--muted)}
.body{display:grid;grid-template-columns:200px minmax(0,1fr);gap:64px;padding-block:24px 96px;border-top:1px solid var(--rule)}
.content{min-width:0}
.index{position:sticky;top:84px;align-self:start;padding-top:48px;font-size:14px}
.index h4{font:500 11px/1.4 var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin:22px 0 6px}.index h4:first-child{margin-top:0}
.index a{display:block;padding:5px 0 5px 12px;border-left:1px solid var(--rule);color:var(--slate);text-decoration:none;transition:color .24s,border-color .24s}
.index a:hover{color:var(--ink)}.index a.on{color:var(--ink);border-left-color:var(--ink)}
.block{padding-block:48px 72px;border-bottom:1px solid var(--rule)}.block:last-child{border-bottom:0}
.block-head h2{font:300 clamp(30px,3.2vw,40px)/1.12 var(--sans);letter-spacing:-.02em;margin:12px 0 12px}
.block-head p{font:300 18px/1.6 var(--sans);color:var(--slate);max-width:700px;margin:0}
.sub{margin-top:56px}.sub .note,.note{color:var(--slate);font-size:15px;margin:0 0 18px;max-width:700px}
.chain{display:flex;border:1px solid var(--rule);border-radius:6px}
.chain-step{flex:1 1 0;padding:20px 18px 22px;position:relative;min-width:0;transition:background .24s}
.chain-step:hover{background:var(--alt)}
.chain-step+.chain-step{border-left:1px solid var(--rule)}
.chain-step+.chain-step::before{content:"\\203A";position:absolute;left:-10px;top:50%;width:18px;height:18px;margin-top:-9px;border:1px solid var(--rule);border-radius:50%;background:#fff;font:500 13px/16px var(--mono);text-align:center;color:var(--slate)}
.chain-label{font:500 11px/1.4 var(--mono);letter-spacing:.06em;text-transform:uppercase;color:var(--muted);min-height:31px}
.chain-value{font:300 32px/1.15 var(--sans);letter-spacing:-.02em;margin-top:10px;white-space:nowrap}
.chain-sub{font-size:13px;color:var(--slate);margin-top:6px}
.tiles{display:grid;gap:12px}.tiles.two{grid-template-columns:repeat(auto-fit,minmax(220px,1fr))}.tiles.four{grid-template-columns:repeat(auto-fit,minmax(200px,1fr))}
.tile{border:1px solid var(--rule);border-radius:6px;padding:18px 20px 20px;transition:background .24s}.tile:hover{background:var(--alt)}
.tile-label{font:500 11px/1.4 var(--mono);letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
.tile-value{font:300 32px/1.2 var(--sans);letter-spacing:-.02em;margin-top:10px}.tile-sub{font-size:14px;color:var(--slate);margin-top:6px}
.sm-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:28px 28px}
.sm-head{display:flex;justify-content:space-between;align-items:baseline;font-size:15px}.sm-head b{font:400 15px var(--mono)}
.sm-sub{font:400 12px/1.5 var(--mono);color:var(--muted);margin:2px 0 6px}
.quotes{margin-top:36px}.quotes h4{font:500 11px/1.4 var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin:0 0 10px}
blockquote{margin:0 0 12px;padding:4px 0 4px 18px;border-left:1px solid var(--ink);font:300 18px/1.55 var(--sans)}
blockquote cite{display:block;margin-top:8px;font:400 12px/1.5 var(--mono);font-style:normal;color:var(--muted)}
.legend{display:flex;flex-wrap:wrap;gap:6px 18px;font-size:13px;color:var(--slate);margin:4px 0 12px}.legend span{display:inline-flex;align-items:center;gap:7px}
.legend i{display:inline-block}.legend i.box{width:10px;height:10px;border-radius:2px}.legend i.line{width:16px;height:2px}
.lc{position:relative;margin:14px 0 4px;padding-left:48px}.lc.compact{padding-left:36px}.lc:not(.compact){padding-right:168px}
.lc-plot{position:relative;cursor:crosshair;touch-action:pan-y}.lc-plot svg{position:absolute;inset:0;width:100%;height:100%;overflow:visible}
.lc-base{position:absolute;left:0;right:0;bottom:0;border-top:1px solid #d5deea}
.lc-grid{position:absolute;left:0;right:0;border-top:1px solid var(--grid)}
.lc-grid span{position:absolute;right:100%;top:-7px;padding-right:8px;font:400 11px/14px var(--mono);color:var(--muted);font-variant-numeric:tabular-nums;white-space:nowrap}
.lc-dot{position:absolute;width:8px;height:8px;border-radius:50%;transform:translate(-50%,-50%);box-shadow:0 0 0 2px #fff}
.lc-end{position:absolute;left:calc(100% + 12px);transform:translateY(-50%);font:500 12px/1 var(--mono);white-space:nowrap;display:flex;align-items:center;gap:7px;font-variant-numeric:tabular-nums}
.lc-end i{display:inline-block;width:12px;height:2px}.lc-end small{font:400 12px var(--mono);color:var(--slate)}
.lc-cross{position:absolute;top:0;bottom:0;width:0;border-left:1px solid #b9c6d6;pointer-events:none}
.lc-mark{position:absolute;top:0;bottom:0;width:0;border-left:1px dashed #9aabbf;pointer-events:none}
.lc-mark span{position:absolute;top:0;right:8px;font:500 11px/1.4 var(--mono);color:var(--slate);white-space:nowrap;background:#fff;padding:0 4px}
td .tick{font:500 13px var(--mono)}td .why{display:block;max-width:460px;margin-top:2px;font-size:13px;line-height:1.5;color:var(--slate)}td .muted{font-size:13px}
td i.key{display:inline-block;width:12px;height:2px;margin-right:8px;vertical-align:4px}
.lc-x{position:relative;height:20px;font:400 11px/1 var(--mono);color:var(--muted)}.lc-x span{position:absolute;top:6px;transform:translateX(-50%);white-space:nowrap}
.lc-x span.first{transform:none}.lc-x span.last{transform:translateX(-100%)}
.hb{display:grid;gap:4px;margin:6px 0}.hb-row{display:grid;grid-template-columns:minmax(110px,180px) 1fr;gap:14px;align-items:center;border-radius:4px;padding:4px 6px;margin:0 -6px;transition:background .24s}
.hb-row:hover,.hb-row:focus-visible{background:var(--alt)}.hb-label{font-size:14px;line-height:1.3}.hb-label small{display:block;color:var(--muted);font-size:12px}
.hb-track{display:flex;align-items:center;gap:10px;min-width:0}.hb-fill{display:flex;gap:2px;height:16px}.hb-fill span{height:100%}.hb-fill span:last-child{border-radius:0 4px 4px 0}
.hb-value{font:400 12px/1 var(--mono);color:var(--slate);white-space:nowrap;font-variant-numeric:tabular-nums}
.stack{display:flex;gap:2px;height:20px;margin:4px 0 10px}.stack span:last-child{border-radius:0 4px 4px 0}
h3.gap{margin-top:36px}
.tiles.three{grid-template-columns:repeat(auto-fit,minmax(220px,1fr))}
.pt-wrap{overflow-x:auto;margin:6px 0 4px}.pt{min-width:640px;padding:0 14px}
.pt-plot{position:relative;box-sizing:content-box;padding-top:22px;border-bottom:1px solid #d5deea}
.pt-dot{position:absolute;width:20px;height:20px;margin:0 0 4px -10px;border-radius:50%;display:grid;place-items:center;font:500 10.5px/1 var(--mono);
background:var(--c);color:#fff;box-shadow:0 0 0 2px #fff;cursor:default}
.pt-dot.open{background:#fff;color:var(--slate);border:1.5px solid var(--c)}.pt-dot.void{color:var(--ink)}
.pt-now{position:absolute;top:0;bottom:0;border-left:1px dashed #9aabbf}.pt-now b{position:absolute;top:0;left:6px;font:500 11px/1.4 var(--mono);color:var(--slate);white-space:nowrap}
.pt-axis{position:relative;height:22px;font:400 11px/1 var(--mono);color:var(--muted)}.pt-axis span{position:absolute;top:7px;padding-left:4px;border-left:1px solid #d5deea;height:15px}
.legend i.pt-key{width:10px;height:10px;border-radius:50%;background:var(--c)}.legend i.pt-key.open{background:#fff;border:1.5px solid var(--c)}
table.preds tr.grp th{padding-top:26px;font:500 15px/1.4 var(--sans);letter-spacing:0;text-transform:none;color:var(--ink)}
table.preds tbody tr:first-child.grp th{padding-top:10px}
td .res{font-weight:500;white-space:nowrap}td.nowrap{white-space:nowrap}
.tip{max-width:320px}
.prov{display:flex;justify-content:space-between;align-items:flex-start;gap:16px 24px;flex-wrap:wrap;border-top:1px solid var(--rule);margin-top:18px;padding-top:12px;font-size:13px;line-height:1.55;color:var(--slate)}
.prov p{margin:0;max-width:640px}.prov-end{display:flex;align-items:center;gap:14px;margin-left:auto}
.copy{font:500 11px/1 var(--mono);letter-spacing:.06em;text-transform:uppercase;border:1px solid var(--rule);background:#fff;color:var(--ink);border-radius:4px;padding:7px 9px;cursor:pointer;transition:border-color .24s}
.copy:hover{border-color:var(--ink)}.wordmark{font:600 12px/1 var(--sans);letter-spacing:-.01em;color:var(--muted)}
.tv{margin:12px 0 0}.tv summary{cursor:pointer;font:500 11px/1.4 var(--mono);letter-spacing:.06em;text-transform:uppercase;color:var(--slate)}
.table-wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:14px;margin:10px 0}
th,td{text-align:left;padding:8px 12px 8px 0;border-bottom:1px solid var(--rule);vertical-align:top}th{font:500 11px/1.4 var(--mono);letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.foot{border-top:1px solid var(--rule)}.foot .frame{padding-block:40px 56px;display:flex;flex-wrap:wrap;gap:12px 32px;justify-content:space-between;font-size:14px;color:var(--slate)}
.foot p{margin:0;max-width:640px}
.tip{position:fixed;left:0;top:0;z-index:40;pointer-events:none;background:#fff;border:1px solid var(--rule);border-radius:6px;box-shadow:0 8px 24px rgba(7,24,46,.10),0 2px 6px rgba(7,24,46,.06);padding:9px 11px;font-size:13px;min-width:130px}
.tip-title{font:400 11px/1.4 var(--mono);color:var(--muted);margin-bottom:5px}.tip-row{display:flex;align-items:center;gap:8px;line-height:1.6}
.tip-row strong{font:500 13px var(--mono);color:var(--ink)}.tip-row span:last-child{color:var(--slate)}.tip-key{display:inline-block;width:12px;height:2px}
@media (prefers-reduced-motion:no-preference){@supports (animation-timeline:view()){
.block-head,.sub>h3,.sub>.note,.tile,.chain{animation:rise both cubic-bezier(.2,.7,.2,1);animation-timeline:view();animation-range:entry 0% cover 16%}
.lc svg.draw{animation:wipe both ease-out;animation-timeline:view();animation-range:entry 20% cover 45%}
.hb-fill,.stack{transform-origin:left;animation:grow both cubic-bezier(.2,.7,.2,1);animation-timeline:view();animation-range:entry 10% cover 35%}
@keyframes rise{from{opacity:.25;transform:translateY(18px)}to{opacity:1;transform:none}}
@keyframes wipe{from{clip-path:inset(0 100% 0 0)}to{clip-path:inset(0 0 0 0)}}
@keyframes grow{from{transform:scaleX(.03)}to{transform:none}}}}
@media (max-width:992px){.body{grid-template-columns:1fr;gap:0}
.index{position:static;display:flex;gap:6px;overflow-x:auto;padding:20px 0 4px;margin:0 calc(-1 * var(--gutter));padding-inline:var(--gutter);scrollbar-width:none}
.index h4{display:none}.index a{flex:0 0 auto;border:1px solid var(--rule);border-radius:999px;padding:6px 12px;white-space:nowrap}.index a.on{border-color:var(--ink)}}
@media (max-width:900px){.hero-grid{grid-template-columns:1fr}.hero-copy{padding-block:56px 8px}
.globe-panel{min-height:380px;margin-inline:calc(-1 * var(--gutter))}#globe{inset:0 0 -150px 0}.globe-note{right:var(--gutter);top:8px}
.stats{grid-template-columns:1fr 1fr}.stat:nth-child(odd){border-left:0;padding-left:0}.stat:nth-child(n+3){border-top:1px solid var(--night-rule)}
.chain{flex-direction:column}.chain-step+.chain-step{border-left:0;border-top:1px solid var(--rule)}.chain-step+.chain-step::before{left:18px;top:-10px;margin-top:0;transform:rotate(90deg)}}
@media (max-width:640px){:root{--gutter:16px}.frame{border-inline:0}.nav-links a:not(.gh){display:none}.lc:not(.compact){padding-right:0}.lc-end{display:none}
.rank{grid-template-columns:120px 1fr auto}.stat{padding:22px 12px 26px}.stat-value{font-size:30px}}
"""

JS = """
const reduce=matchMedia('(prefers-reduced-motion: reduce)').matches;
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
document.querySelectorAll('.copy').forEach(btn=>btn.addEventListener('click',async()=>{const label=btn.textContent;
try{await navigator.clipboard.writeText(btn.dataset.csv);btn.textContent='Copied'}catch(_){const ta=document.createElement('textarea');ta.value=btn.dataset.csv;document.body.append(ta);ta.select();
try{document.execCommand('copy');btn.textContent='Copied'}catch(__){btn.textContent='Copy failed'}ta.remove()}setTimeout(()=>{btn.textContent=label},1600)}));
function fmtCount(el,v){const d=+el.dataset.decimals||0;return (el.dataset.prefix||'')+v.toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d})+(el.dataset.suffix||'')}
if(!reduce)document.querySelectorAll('[data-count]').forEach((el,i)=>{const target=+el.dataset.count,t0=performance.now()+250+i*160,dur=1500;el.textContent=fmtCount(el,0);
const step=now=>{const p=Math.min(1,Math.max(0,(now-t0)/dur)),k=1-Math.pow(1-p,3);el.textContent=fmtCount(el,target*k);if(p<1)requestAnimationFrame(step)};requestAnimationFrame(step)});
const ticker=document.getElementById('ticker');
if(ticker&&!reduce){const rate=+ticker.dataset.rate,t0=performance.now();document.getElementById('tick-label').textContent='Capex spent since you opened this page';let last=0;
const loop=now=>{if(now-last>60){ticker.textContent='$'+Math.floor(rate*(now-t0)/1000).toLocaleString('en-US');last=now}requestAnimationFrame(loop)};requestAnimationFrame(loop)}
const statsEl=document.getElementById('stats');const cells=[...document.querySelectorAll('.stat')];const listeners=[];let active=0,pinned=false;
function light(i){active=i;cells.forEach((c,j)=>{c.classList.toggle('is-lit',j===i);c.setAttribute('aria-pressed',j===i?'true':'false')});listeners.forEach(f=>f(i))}
if(cells.length){if(reduce){statsEl.classList.add('all-lit')}else{light(0);setInterval(()=>{if(!pinned&&!document.hidden)light((active+1)%cells.length)},4200)}
cells.forEach((c,i)=>{const pin=()=>{pinned=true;light(i)};c.addEventListener('mouseenter',pin);c.addEventListener('focus',pin);c.addEventListener('click',pin);
c.addEventListener('mouseleave',()=>{pinned=false});c.addEventListener('blur',()=>{pinned=false})})}
const links=[...document.querySelectorAll('.index a')];const targets=links.map(a=>document.getElementById(a.hash.slice(1))).filter(Boolean);
if('IntersectionObserver' in window){const spy=new IntersectionObserver(es=>es.forEach(en=>{if(en.isIntersecting)links.forEach(a=>a.classList.toggle('on',a.hash==='#'+en.target.id))}),{rootMargin:'-40% 0px -55% 0px'});targets.forEach(t=>spy.observe(t))}
const panel=document.getElementById('globe-panel');
function webgl(){try{const c=document.createElement('canvas');return !!(c.getContext('webgl2')||c.getContext('webgl'))}catch(_){return false}}
function initGlobe(){const el=document.getElementById('globe');if(typeof Globe!=='function'||!webgl()){panel.classList.add('no-globe');return}
const data=JSON.parse(panel.dataset.globe);const byId=Object.fromEntries(data.nodes.map(n=>[n.id,n]));data.arcs.forEach((a,k)=>a.k=k);
let focusArcs=new Set(),focusNodes=new Set();const lit=id=>focusNodes.has(id)||[...focusArcs].some(k=>data.arcs[k].to===id);const hex=(c,a)=>c+Math.round(a*255).toString(16).padStart(2,'0');
const world=Globe({animateIn:!reduce})(el).backgroundColor('rgba(0,0,0,0)').showAtmosphere(true).atmosphereColor('#2c57c9').atmosphereAltitude(.13)
.particleLat(d=>d[0]).particleLng(d=>d[1]).particleAltitude(.003).particlesSize(1.8).particlesSizeAttenuation(false).particlesColor(()=> 'rgba(150,176,228,0.6)')
.arcsData(data.arcs).arcStartLat(a=>byId[a.from].lat).arcStartLng(a=>byId[a.from].lng).arcEndLat(a=>byId[a.to].lat).arcEndLng(a=>byId[a.to].lng)
.arcAltitudeAutoScale(.36).arcDashLength(reduce?1:.42).arcDashGap(reduce?0:1.15).arcDashInitialGap(a=>(a.k*.37)%1).arcDashAnimateTime(reduce?0:2400)
.pointsData(data.nodes).pointLat('lat').pointLng('lng').pointAltitude(.012).pointRadius('r').pointColor('color').pointResolution(24)
.ringLat('lat').ringLng('lng').ringColor(n=>t=>hex(n.color,Math.max(0,1-t)*.85)).ringMaxRadius(n=>n.r*5.5).ringPropagationSpeed(1.3).ringRepeatPeriod(1500)
.htmlElementsData(data.nodes).htmlLat('lat').htmlLng('lng').htmlAltitude(.015)
.htmlElement(n=>{const w=document.createElement('div');w.className='gl-pin';const t=document.createElement('span');t.className='gl-label'+(n.side==='l'?' l':'');t.dataset.id=n.id;t.textContent=n.label;t.classList.toggle('on',lit(n.id));w.append(t);return w})
.onPointHover(n=>{if(n){fill(n.label,[[n.value||'·',n.detail,n.color]])}else hide()});
if(world.htmlElementVisibilityModifier)world.htmlElementVisibilityModifier((node,visible)=>{node.style.opacity=visible?'':0});
el.addEventListener('pointermove',e=>{if(!tip.hidden)place(e.clientX,e.clientY)});el.addEventListener('pointerleave',hide);
const mat=world.globeMaterial();mat.color.set('#0e1b3b');mat.shininess=4;
const controls=world.controls();controls.enableZoom=false;controls.enablePan=false;controls.rotateSpeed=.6;
const size=()=>{world.width(el.clientWidth);world.height(el.clientHeight)};size();new ResizeObserver(size).observe(el);
function focus(i){const f=data.figures[i];if(!f)return;focusArcs=new Set(f.arcs);focusNodes=new Set(f.nodes);
world.arcColor(a=>focusArcs.has(a.k)?[hex(a.color,.2),a.color]:[hex(a.color,.04),hex(a.color,.16)]).arcStroke(a=>focusArcs.has(a.k)?.6:.28);
world.ringsData(reduce?[]:data.nodes.filter(n=>focusNodes.has(n.id)));
document.querySelectorAll('.gl-label').forEach(l=>l.classList.toggle('on',lit(l.dataset.id)));
world.pointOfView({lat:f.pov.lat,lng:f.pov.lng,altitude:2.25},reduce?0:2200)}
world.pointOfView({lat:24,lng:-160,altitude:2.25});
if(reduce){world.arcColor(a=>[hex(a.color,.25),a.color]).arcStroke(.42)}else{listeners.push(focus);focus(active)}
fetch('land-dots.json').then(r=>r.json()).then(dots=>world.particlesData([dots])).catch(()=>{});
if('IntersectionObserver' in window)new IntersectionObserver(([en])=>{en.isIntersecting?world.resumeAnimation():world.pauseAnimation()}).observe(panel)}
function loadGlobe(){const s=document.createElement('script');s.src=panel.dataset.src;s.async=true;s.onload=initGlobe;s.onerror=()=>panel.classList.add('no-globe');document.head.append(s)}
if(panel){'requestIdleCallback' in window?requestIdleCallback(loadGlobe,{timeout:1200}):setTimeout(loadGlobe,300)}
"""


def render(month: str, demand: dict, supply: dict, book: dict | None, call: dict | None, owners: dict, perf: dict | None = None,
           preds: dict | None = None) -> str:
    updated = supply.get("generated") or date.today().isoformat()
    picks_html = picks_section(perf)
    preds_html = predictions_section(preds)
    sections = [picks_html, preds_html, demand_section(demand), supply_section(supply)]
    if book:
        sections.append(book_section(book, owners))
    sections.append(method_section(demand))
    description = "A monthly read on where AI data center demand is outrunning supply, built from SEC filings and Asian trade data."
    links = [("call", "The call"), ("picks", "Picks"), ("predictions", "Predictions"), ("demand", "Demand"), ("supply", "Supply"),
             ("book", "Book"), ("method", "Method")]
    shown = {"picks": bool(picks_html), "predictions": bool(preds_html)}
    nav_links = "".join(f'<a href="#{a}">{e(t)}</a>' for a, t in links if shown.get(a, True))
    hero_html = hero(demand, supply, call, month).replace('id="globe-panel"', f'id="globe-panel" data-src="{GLOBE_JS}"', 1)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bottleneck Radar</title><meta name="description" content="{e(description)}">
<meta property="og:title" content="Bottleneck Radar"><meta property="og:description" content="{e(description)}">
<meta name="theme-color" content="#0a1428">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin><link rel="stylesheet" href="{FONTS}">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Crect width='16' height='16' rx='3' fill='%230a1428'/%3E%3Crect x='3' y='9' width='2' height='4' rx='.5' fill='%2386b6ef'/%3E%3Crect x='7' y='6' width='2' height='7' rx='.5' fill='%233987e5'/%3E%3Crect x='11' y='3' width='2' height='10' rx='.5' fill='%23fff'/%3E%3C/svg%3E">
<style>{CSS}</style></head>
<body>
<header class="nav"><div class="frame"><a class="brand" href="#top">Bottleneck Radar</a><span class="tag">{e(short_date(month + "-01"))}</span>
<nav class="nav-links" aria-label="Sections">{nav_links}<a class="gh" href="{REPO}" rel="noopener">GitHub</a></nav></div></header>
<main>
{hero_html}
<div class="frame">
{call_section(call, owners)}
<div class="body">{index_rail({a for a, on in shown.items() if not on})}<div class="content">{"".join(sections)}</div></div>
</div>
</main>
<footer class="foot"><div class="frame"><p>Research notes only. Nothing here is investment advice. Data updated {e(updated)}{f", prices to the {e(day_label(perf['as_of']))} close" if perf else ""}; built with {link(REPO, "bottleneck-radar")}.</p>
<p>The idea comes from a TikTok by {link("https://www.tiktok.com/@angusthenontechnical", "Angus the Nontechnical")}.</p></div></footer>
<div id="tip" class="tip" role="status" hidden></div><script>{JS}</script></body></html>
"""


def run() -> None:
    months = sorted(p.name for p in DATA.glob("20[0-9][0-9]-[01][0-9]") if (p / "demand.json").exists() and (p / "supply.json").exists())
    if not months:
        raise SystemExit("No month in data/ has demand.json and supply.json yet. Run `radar demand` and `radar supply` first.")
    month = months[-1]
    folder = DATA / month
    books = sorted(DATA.glob("13f/*/*.json"))
    call_path = folder / "bottleneck.json"
    perf_path = DATA / "performance.json"
    pred_sets = [read_json(p) for p in sorted((DATA / "predictions").glob("20[0-9][0-9]-[01][0-9].json"))]
    pred_results = DATA / "prediction-results.json"
    owners = yaml.safe_load((CONFIG / "owners.yaml").read_text())
    geo.ensure_land_dots(SITE / "land-dots.json")
    page = render(
        month,
        read_json(folder / "demand.json"),
        read_json(folder / "supply.json"),
        read_json(books[-1]) if books else None,
        read_json(call_path) if call_path.exists() else None,
        owners,
        read_json(perf_path) if perf_path.exists() else None,
        {"sets": pred_sets, "results": read_json(pred_results) if pred_results.exists() else None} if pred_sets else None,
    )
    path = write_text(SITE / "index.html", page)
    print(f"Dashboard for {month_name(month)}: {path.relative_to(ROOT)} ({len(page) / 1024:.0f} KB)")
