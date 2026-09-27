from pathlib import Path

from radar import clone

XML = (Path(__file__).parent / "fixtures" / "info_table.xml").read_bytes()


def test_parse_info_table_reads_every_row():
    rows = clone.parse_info_table(XML)
    assert len(rows) == 4
    assert rows[0] == {
        "name": "MICRON TECHNOLOGY INC",
        "title": "COM",
        "cusip": "595112103",
        "value": 3000,
        "shares": 3,
        "share_type": "SH",
        "put_call": None,
    }
    assert rows[2]["put_call"] == "Call"


def test_aggregate_merges_split_holdings_but_keeps_options_apart():
    rows = clone.aggregate(clone.parse_info_table(XML))
    by_key = {(r["cusip"], r["put_call"]): r for r in rows}
    assert by_key[("595112103", None)]["value"] == 4000
    assert by_key[("595112103", None)]["shares"] == 4
    assert by_key[("093712107", None)]["value"] == 1000
    assert by_key[("093712107", "Call")]["value"] == 500
    assert [r["value"] for r in rows] == sorted((r["value"] for r in rows), reverse=True)


def test_weights_cover_long_stock_only():
    weights = clone.weights(clone.aggregate(clone.parse_info_table(XML)))
    assert {w["cusip"]: w["weight"] for w in weights} == {"595112103": 0.8, "093712107": 0.2}


def test_order_list_uses_whole_shares(monkeypatch):
    monkeypatch.setattr(clone.prices, "last_price", lambda ticker: {"MU": 1000.0, "BE": 300.0}[ticker])
    book = {
        "period": "2026-06-30",
        "weights": [
            {"ticker": "MU", "name": "MICRON", "value": 4000, "shares": 4, "weight": 0.8},
            {"ticker": "BE", "name": "BLOOM", "value": 1000, "shares": 10, "weight": 0.2},
        ],
    }
    orders = clone.order_list(book, 10_000)
    assert [(o["ticker"], o["shares"]) for o in orders["orders"]] == [("MU", 8), ("BE", 6)]
    assert orders["invested"] == 9800
    assert orders["cash_left"] == 200


def test_order_list_falls_back_to_the_13f_price(monkeypatch):
    monkeypatch.setattr(clone.prices, "last_price", lambda ticker: None)
    book = {"period": "2026-06-30", "weights": [{"ticker": "MU", "name": "MICRON", "value": 4000, "shares": 4, "weight": 1.0}]}
    order = clone.order_list(book, 5000)["orders"][0]
    assert order["price"] == 1000 and order["price_is_13f"] and order["shares"] == 5
