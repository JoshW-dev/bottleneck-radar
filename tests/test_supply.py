import pytest

from radar.supply import korea, taiwan, turbines

# Lines copied from the August 2026 MOTIR release PDF, as pypdf extracts them.
KOREA_TEXT = """
* 반도체 수출액/증감률(억 달러) : (’25.8.) 151.0(+27.1%) → (’26.8.) 466.5(+209.0%)
   ↳ 메모리/시스템 반도체 수출액: 104.9 → 409.4(+290.2%) / 41.3 → 51.3(+24.4%)
* 주요 메모리 제품 고정가격 및 증감률(’26.6월 → 7월 → 8월 $, %) :
       DDR5 16Gb40.00 → 45.00 → 46.50(+786.2) / NAND 128G28.82 → 30.05 → 30.48(+792.5)
"""

# Sentences from GE Vernova's Q2 2026 earnings release (EDGAR, Exhibit 99).
GEV_TEXT = """GE Vernova reports second quarter 2026 financial results
• Gas Power equipment backlog and slot reservation agreements grew from 100 to 116 GW; now anticipate
reaching at least 125 GW by year-end 2026
Converted 10 GW of existing slot reservation agreements to orders and shipped 3 GW of equipment; resulting in
backlog growth from 44 to 53 GW and an increase in slot reservation agreements from 56 to 63 GW."""


def test_korea_release_parses_memory_and_prices():
    r = korea.parse_release(KOREA_TEXT)
    assert r["period"] == "2026-08"
    assert r["chips_usd"] == pytest.approx(46.65e9)
    assert r["chips_yoy"] == pytest.approx(2.09)
    assert r["memory_usd"] == pytest.approx(40.94e9)
    assert r["memory_year_ago_usd"] == pytest.approx(10.49e9)
    assert r["memory_yoy"] == pytest.approx(2.902)
    assert r["system_chips_yoy"] == pytest.approx(0.244)
    assert r["ddr5_16gb_contract_usd"] == pytest.approx(46.5)
    assert r["nand_128gb_yoy"] == pytest.approx(7.925)


def test_korea_percent_marks_declines_with_a_triangle():
    assert korea._pct("△5") == pytest.approx(-0.05)
    assert korea._pct("+1,040") == pytest.approx(10.4)


def test_roc_period():
    assert taiwan.roc_period("11508") == "2026-08"
    assert taiwan.roc_period("07301") == "1984-01"


TOTAL_CSV = """統計項目,資料期(民國年),統計值(美元),計量單位(美元),統計值(新台幣),計量單位(新台幣)
外銷訂單金額,11406,50,百萬美元,15,新臺幣億元
外銷訂單金額,11407,50,百萬美元,15,新臺幣億元
外銷訂單金額,11408,60,百萬美元,19,新臺幣億元
外銷訂單金額,11506,80,百萬美元,25,新臺幣億元
外銷訂單金額,11507,90,百萬美元,28,新臺幣億元
外銷訂單金額,11508,120,百萬美元,38,新臺幣億元
""".encode("utf-8-sig")

PRODUCT_CSV = """統計項目,貨品別,資料期(民國年),統計值(金額),計量單位
外銷訂單金額_美元,電子產品,11408,25,百萬美元
外銷訂單金額_新臺幣,電子產品,11408,800,新臺幣億元
外銷訂單金額_美元,電子產品,11508,50,百萬美元
外銷訂單金額_新臺幣,電子產品,11508,1500,新臺幣億元
""".encode("utf-8")


def test_taiwan_total_csv_and_growth():
    series = taiwan.parse_csv(TOTAL_CSV)
    assert series[-1] == ("2026-08", 120.0)
    s = taiwan.summarize(series)
    assert s["yoy"] == pytest.approx(1.0)
    assert s["yoy_3m"] == pytest.approx(290 / 160 - 1)


def test_taiwan_product_csv_keeps_us_dollar_rows():
    assert taiwan.parse_csv(PRODUCT_CSV) == [("2025-08", 25.0), ("2026-08", 50.0)]


def test_ge_vernova_release():
    r = turbines.parse_ge_vernova(GEV_TEXT)
    assert r == {
        "quarter": "2026-Q2",
        "backlog_and_slots_gw": 116.0,
        "backlog_gw": 53.0,
        "slot_reservations_gw": 63.0,
        "shipped_gw_quarter": 3.0,
        "year_end_target_gw": 125.0,
    }
    assert turbines.years_of_backlog(r) == pytest.approx(9.7)


def test_years_of_backlog_needs_shipments():
    assert turbines.years_of_backlog({"backlog_gw": 35}) is None
    assert turbines.years_of_backlog({"backlog_gw": 69, "slot_reservations_gw": 26, "shipped_gw_quarter": 6}) == 4.0
