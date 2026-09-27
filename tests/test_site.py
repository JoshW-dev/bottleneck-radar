import pytest

from radar import site
from radar.bottleneck import load_owners

OWNERS = load_owners()


def quarters(values, first_end_month=9, year=2024):
    out = []
    for i, v in enumerate(values):
        month = (first_end_month - 1 + 3 * i) % 12 + 1
        y = year + (first_end_month - 1 + 3 * i) // 12
        day = {3: 31, 6: 30, 9: 30, 12: 31}[month]
        out.append({"start": f"{y}-{month - 2:02d}-01", "end": f"{y}-{month:02d}-{day}", "value": v * 1e9})
    return out


def company(name, values):
    qs = quarters(values)
    return {"name": name, "quarters": qs, "latest": qs[-1], "yoy": values[-1] / values[-5] - 1, "guidance": {"forward": []}}


PHYSICAL = {"gw": 15.5, "gpus": 6.5e6, "hbm_gb": 1.88e9, "sqft": 51e6, "turbines_7ha": 36}
DEMAND = {
    "total": {"ttm": 586e9, "prior_ttm": 319e9, "ttm_growth": 0.84, "run_rate": 774e9},
    "companies": {"AMZN": company("Amazon", [20, 22, 24, 26, 30, 34, 40, 54]), "META": company("Meta", [10, 11, 12, 13, 15, 18, 22, 30])},
    "physical": {"ttm": PHYSICAL, "run_rate": PHYSICAL, "added_vs_prior_ttm": PHYSICAL},
    "assumptions": {"capex_per_gw": {"value": 37.9e9, "url": "https://epoch.ai"}, "kw_per_gpu": {"value": 1.9, "status": "unverified"}},
}
SUPPLY = {
    "generated": "2026-09-26",
    "memory": {"period": "2026-08", "memory_usd": 40.94e9, "memory_year_ago_usd": 10.49e9, "memory_yoy": 2.902,
               "chips_usd": 46.65e9, "chips_yoy": 2.09, "source": "https://example.test/motir", "pdf": "https://example.test/pdf"},
    "export_orders": {
        "electronics": {"period": "2026-08", "usd_millions": 45755, "yoy": 0.84, "url": "https://example.test/e",
                        "history": [["2026-06", 40000], ["2026-07", 42000], ["2026-08", 45755]]},
        "ict": {"period": "2026-08", "usd_millions": 34210, "yoy": 1.0, "url": "https://example.test/i",
                "history": [["2026-06", 30000], ["2026-07", 33000], ["2026-08", 34210]]},
    },
    "gas_turbines": [{"company": "GE Vernova", "backlog_gw": 53, "slot_reservations_gw": 63, "backlog_and_slots_gw": 116,
                      "shipped_gw_quarter": 3, "years_of_backlog": 9.7, "quarter": "2026-Q2", "source": "https://example.test/gev", "method": "parsed"}],
    "grid": [{"name": "ERCOT", "as_of": "2026-09-11", "base_load_gw": 66.4, "base_load_projects": 204, "studied_load_gw": 127.9,
              "studied_load_projects": 158, "source": "https://example.test/ercot", "note": ""}],
    "errors": [],
}
BOOK = {
    "fund": "Example Fund LP", "period": "2026-06-30", "filed": "2026-08-14", "source": "https://example.test/13f",
    "weights": [
        {"ticker": "MU", "name": "MICRON TECHNOLOGY INC", "value": 6e9, "weight": 0.6},
        {"ticker": "GEV", "name": "GE VERNOVA INC", "value": 3e9, "weight": 0.3},
        {"ticker": "XYZ", "name": "<SCRIPT>ALERT(1)</SCRIPT>", "value": 1e9, "weight": 0.1},
    ],
}
CALL = {
    "month": "2026-09", "bottleneck": "memory", "headline": "Memory is the tightest input.", "why": "Exports rose 290%.",
    "ranking": [{"input": "memory", "tightness": 5, "demand_signal": "a", "supply_signal": "b"},
                {"input": "gas_turbines", "tightness": 4, "demand_signal": "c", "supply_signal": "d"}],
    "owners": ["micron", "sk_hynix"], "consensus_trade": ["nvidia"],
    "falsifiers": [{"metric": "Korean memory exports", "threshold": "below +100% y/y", "why": "demand cooling"}],
    "change_vs_last_month": "This is the first note.", "data_gaps": [],
}


def test_nice_ticks():
    assert site.nice_ticks(50) == [10, 20, 30, 40, 50]
    assert site.nice_ticks(60) == [20, 40, 60]
    assert site.nice_max(45.8) == 50


def test_page_renders_every_section_with_a_call():
    page = site.render("2026-09", DEMAND, SUPPLY, BOOK, CALL, OWNERS)
    for fragment in ('id="call"', "Memory chips are this month", "Micron Technology", "$586B", "Taiwan export orders",
                     "GE Vernova", "Example Fund LP", "What would prove this wrong", 'id="globe-panel"', "land-dots.json"):
        assert fragment in page
    assert "<SCRIPT>" not in page  # names from filings are escaped


def test_globe_payload_ties_each_figure_to_its_arcs():
    figures = site.stats(SUPPLY)
    payload = site.globe_payload(SUPPLY, figures)
    ids = {n["id"] for n in payload["nodes"]}
    assert {"korea", "taiwan", "GE Vernova", "texas", "virginia"} <= ids
    memory = payload["figures"][0]
    assert memory["arcs"] and all(payload["arcs"][k]["from"] == "korea" for k in memory["arcs"])
    grid = payload["figures"][-1]
    assert grid["arcs"] and all(payload["arcs"][k]["to"] == "texas" for k in grid["arcs"])
    assert [f["value"] for f in figures] == [40.94, 45.755, 116.0, pytest.approx(194.3)]


def test_page_renders_without_a_call():
    page = site.render("2026-09", DEMAND, SUPPLY, None, None, OWNERS)
    assert "shows up here after the first run" in page


def test_book_shares_group_holdings_by_input():
    page = site.book_section(BOOK, OWNERS)
    assert "Memory 60.0%" in page and "Power and grid 30.0%" in page and "Other 10.0%" in page


@pytest.mark.parametrize("value,text", [(586e9, "$586.0B"), (1.2e12, "$1.2T"), (40.94e6, "$40.9M")])
def test_usd(value, text):
    assert site.usd(value) == text


def perf(live: bool) -> dict:
    days = ["2025-12-31", "2026-06-30", "2026-09-25", "2026-09-28"]

    def line(label, values, since):
        return {"label": label, "values": values, "ytd": values[-1] / 100 - 1, "since_call": since if live else None,
                "max_drawdown": {"change": -0.25, "peak": "2026-06-30", "low": "2026-09-25"}}

    rows = [
        {"id": "micron", "name": "Micron Technology", "quote": "MU", "weight": 0.5, "role": "Memory <b>maker</b>", "ytd": 3.0, "since_pick": 0.05 if live else None},
        {"id": "sk_hynix", "name": "SK Hynix", "quote": "000660.KS", "weight": 0.5, "role": "HBM", "ytd": 2.0, "since_pick": 0.01 if live else None},
    ]
    return {
        "generated": "2026-09-28", "as_of": "2026-09-28", "year": 2026, "base": "2025-12-31", "days": days, "failed": [],
        "series": {
            "picks": line("Picks", [100, 400, 300, 315], 0.05),
            "clone": line("13F clone", [100, 200, 170, 175], 0.03),
            "consensus": line("Consensus AI", [100, 105, 110, 111], 0.01),
            "sp500": line("S&P 500", [100, 108, 112, 113], 0.009),
        },
        "picks": {"month": "2026-09", "published": "2026-09-27", "bottleneck": "memory", "label": "Memory chips (HBM, DRAM, NAND)",
                  "headline": "Memory is tight.", "rule": "Equal weight.", "first_published": "2026-09-27",
                  "entry": "2026-09-28" if live else None, "live_from": "2026-09-28" if live else None, "basket_ytd": 2.15, "rows": rows},
        "consensus": {"rows": [{"quote": "NVDA", "name": "Nvidia", "ytd": 0.2, "since_pick": None}]},
        "clone": {"fund": "Example Fund LP", "books": [{"period": "2026-06-30", "filed": "2026-08-14", "bought_on": "2026-08-17",
                                                        "positions": 3, "bought": 0.98, "missing": ["Gone Corp (no ticker)"]}]},
    }


def test_picks_section_before_the_live_record_starts():
    page = site.render("2026-09", DEMAND, SUPPLY, BOOK, CALL, OWNERS, perf(live=False))
    for fragment in ('id="picks"', 'href="#picks"', "The two memory makers named in the September 2026 call", "Starts Sep 28",
                     "Called Sep 27", "Memory &lt;b&gt;maker&lt;/b&gt;", "Gone Corp (no ticker)", "Consensus AI (NVDA)", "−25% (Jun 30 to Sep 25)"):
        assert fragment in page
    assert "<b>maker</b>" not in page


def test_picks_section_once_live():
    page = site.render("2026-09", DEMAND, SUPPLY, BOOK, CALL, OWNERS, perf(live=True))
    assert "Since the Sep 27 call the picks are +5.0%, against +1.0% for the consensus basket and +0.9% for the S&amp;P 500." in page
    assert "Starts Sep 28" not in page


def test_page_without_performance_leaves_the_picks_out():
    page = site.render("2026-09", DEMAND, SUPPLY, BOOK, CALL, OWNERS)
    assert 'id="picks"' not in page and 'href="#picks"' not in page
