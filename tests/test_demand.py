import pytest

from radar import demand


def fact(start, end, val, filed="2026-07-29"):
    return {"start": start, "end": end, "val": val, "filed": filed}


# Microsoft-style fiscal year from July: Q1 reported directly, the rest only year-to-date.
FACTS = [
    fact("2025-07-01", "2025-09-30", 19, "2025-10-29"),
    fact("2025-07-01", "2025-12-31", 49, "2026-01-28"),
    fact("2025-07-01", "2026-03-31", 80, "2026-04-29"),
    fact("2025-07-01", "2026-06-30", 116, "2026-07-29"),
    fact("2026-01-01", "2026-03-31", 31, "2026-04-29"),
]


def test_quarterly_derives_quarters_from_year_to_date_values():
    quarters = demand.quarterly(FACTS)
    assert [(q["end"], q["value"], q["derived"]) for q in quarters] == [
        ("2025-09-30", 19, False),
        ("2025-12-31", 30, True),
        ("2026-03-31", 31, False),
        ("2026-06-30", 36, True),
    ]
    assert quarters[1]["start"] == "2025-10-01"


def test_quarterly_keeps_the_newest_filing_for_a_period():
    restated = FACTS + [fact("2025-07-01", "2025-09-30", 20, "2026-10-01")]
    assert demand.quarterly(restated)[0]["value"] == 20


def test_consecutive_tail_stops_at_a_gap():
    quarters = [
        {"start": "2024-01-01", "end": "2024-03-31", "value": 1},
        {"start": "2025-01-01", "end": "2025-03-31", "value": 2},
        {"start": "2025-04-01", "end": "2025-06-30", "value": 3},
    ]
    assert [q["value"] for q in demand.consecutive_tail(quarters)] == [2, 3]


def test_summarize_growth_figures():
    quarters = []
    for i, value in enumerate([10, 10, 10, 10, 20, 20, 20, 30]):
        year, q = divmod(i, 4)
        start_month = 3 * q + 1
        end = {1: "03-31", 4: "06-30", 7: "09-30", 10: "12-31"}[start_month]
        quarters.append({"start": f"{2024 + year}-{start_month:02d}-01", "end": f"{2024 + year}-{end}", "value": value})
    s = demand.summarize(quarters)
    assert s["ttm"] == 90 and s["prior_ttm"] == 40
    assert s["ttm_growth"] == pytest.approx(1.25)
    assert s["yoy"] == pytest.approx(2.0)
    assert s["qoq"] == pytest.approx(0.5)


def test_physical_conversion():
    a = {
        "datacenter_share_of_capex": {"value": 1.0},
        "capex_per_gw": {"value": 40e9},
        "it_power_share": {"value": 0.8},
        "kw_per_gpu": {"value": 2.0},
        "hbm_gb_per_gpu": {"value": 288},
        "sqft_per_mw": {"value": 3000},
        "mw_per_turbine": {"value": 400},
    }
    p = demand.physical(80e9, a)
    assert p["gw"] == pytest.approx(2.0)
    assert p["gpus"] == pytest.approx(800_000)
    assert p["hbm_gb"] == pytest.approx(800_000 * 288)
    assert p["sqft"] == pytest.approx(6_000_000)
    assert p["turbines_7ha"] == pytest.approx(5)


def test_prose_filter_drops_table_labels():
    assert demand._is_prose(
        "We anticipate 2026 capital expenditures, including principal payments on finance leases, "
        "to be in the range of $130-145 billion."
    )
    assert not demand._is_prose("Purchases of property and equipment; Principal payments on finance leases.")
    assert not demand._is_prose("Property and equipment, net of accumulated depreciation of $118,691 and $93,653")
