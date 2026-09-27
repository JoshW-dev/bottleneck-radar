import json

import pytest

from radar import bottleneck, performance, picks, prices

OWNERS = bottleneck.load_owners()
CALL = {
    "month": "2026-09", "generated": "2026-09-27", "bottleneck": "memory", "headline": "Memory is tight.",
    "owners": ["micron", "sk_hynix"], "consensus_trade": ["nvidia"],
}


def closes(**series):
    return performance.Closes({symbol: dict(points) for symbol, points in series.items()})


def test_snapshot_weights_the_owners_equally_with_their_listings():
    snap = picks.snapshot(CALL, OWNERS)
    assert [(p["quote"], p["weight"]) for p in snap["picks"]] == [("MU", 0.5), ("000660.KS", 0.5)]
    assert snap["consensus"][0]["quote"] == "NVDA"
    assert snap["published"] == "2026-09-27" and snap["picks"][0]["role"]


def test_picks_are_frozen_once_written(tmp_path, monkeypatch):
    monkeypatch.setattr(picks, "DATA", tmp_path)
    monkeypatch.setattr(picks, "PICKS", tmp_path / "picks")
    (tmp_path / "2026-09").mkdir()
    (tmp_path / "2026-09" / "bottleneck.json").write_text(json.dumps(CALL))
    first = picks.run()
    (tmp_path / "2026-09" / "bottleneck.json").write_text(json.dumps({**CALL, "owners": ["sandisk"], "generated": "2026-09-30"}))
    assert picks.run() == first
    assert picks.run(force=True)["picks"][0]["quote"] == "SNDK"


def test_every_owner_has_a_listing_to_price():
    for name in bottleneck.INPUTS:
        for cid in OWNERS["inputs"][name]["owners"]:
            assert OWNERS["companies"][cid]["quote"] and OWNERS["companies"][cid]["role"]


def test_to_usd_uses_the_rate_on_or_before_each_day():
    krw = {"2026-01-02": 1000.0, "2026-01-05": 1100.0}
    fx = {"2026-01-01": 0.001, "2026-01-05": 0.002}  # dollars per won
    assert prices.to_usd(krw, fx) == {"2026-01-02": 1.0, "2026-01-05": 2.2}


def test_simulate_rebalances_at_the_first_close_on_or_after_the_trade_day():
    c = closes(A={"2026-01-01": 10, "2026-01-02": 20, "2026-01-05": 20}, B={"2026-01-01": 10, "2026-01-02": 10, "2026-01-05": 30})
    days = ["2026-01-01", "2026-01-02", "2026-01-05"]
    books = [{"trade": "2025-12-01", "weights": {"A": 1.0}}, {"trade": "2026-01-03", "weights": {"B": 1.0}}]
    values, fills = performance.simulate(books, c, days)
    # All in A until the Jan 5 close (Jan 3 is a Saturday), then all in B at that close.
    assert values == [100.0, 200.0, 200.0]
    assert [f["day"] for f in fills] == ["2026-01-01", "2026-01-05"]


def test_simulate_drops_unpriced_names_and_reports_them():
    c = closes(A={"2026-01-01": 10, "2026-01-02": 11})
    values, fills = performance.simulate([{"trade": "2026-01-01", "weights": {"A": 0.5, "Gone (no ticker)": 0.5}}], c, ["2026-01-01", "2026-01-02"])
    assert values == [100.0, 110.0]
    assert fills[0]["bought"] == 0.5 and fills[0]["missing"] == ["Gone (no ticker)"]


def test_simulate_keeps_only_the_book_in_force_on_the_first_day():
    c = closes(A={"2026-01-01": 10}, B={"2026-01-01": 10})
    _, fills = performance.simulate(
        [{"trade": "2025-08-01", "weights": {"A": 1.0}, "tag": "old"}, {"trade": "2025-11-15", "weights": {"B": 1.0}, "tag": "q3"}],
        c, ["2026-01-01"],
    )
    assert [f["tag"] for f in fills] == ["q3"]


def test_max_drawdown_finds_the_worst_fall_from_a_peak():
    assert performance.max_drawdown([100, 150, 90, 120, 60, 200]) == (-0.6, 1, 4)
    assert performance.max_drawdown([100, 110]) == (0.0, None, None)


def test_compute_splits_hindsight_from_the_live_record(monkeypatch, tmp_path):
    days = ["2025-12-31", "2026-01-02", "2026-09-25", "2026-09-28", "2026-09-29"]
    fake = {
        "SPY": [100, 101, 110, 111, 112],
        "MU": [10, 12, 40, 44, 48],
        "000660.KS": [10, 10, 20, 20, 30],
        "NVDA": [10, 11, 12, 12, 12],
    }
    monkeypatch.setattr(performance.prices, "usd_history", lambda symbol, start, end=None: dict(zip(days, map(float, fake[symbol]))))
    monkeypatch.setattr(performance.picks_stage, "snapshots", lambda: [picks.snapshot(CALL, OWNERS)])
    monkeypatch.setattr(performance, "DATA", tmp_path)
    out = performance.compute(today=__import__("datetime").date(2026, 9, 29))
    assert out["base"] == "2025-12-31" and out["as_of"] == "2026-09-29"
    p = out["picks"]
    assert p["entry"] == "2026-09-28" and p["live_from"] == "2026-09-28"
    assert p["basket_ytd"] == pytest.approx((48 / 10 + 30 / 10) / 2 - 1)
    mu = next(r for r in p["rows"] if r["quote"] == "MU")
    assert mu["ytd"] == pytest.approx(3.8) and mu["since_pick"] == pytest.approx(48 / 44 - 1, abs=1e-4)
    live = out["series"]["picks"]
    # From the Sep 28 close the basket is rebalanced to equal weight: +9.1% on MU, +50% on SK Hynix, then halved.
    assert live["since_call"] == pytest.approx(((48 / 44) + (30 / 20)) / 2 - 1, abs=1e-4)
    assert out["series"]["sp500"]["ytd"] == pytest.approx(0.12)
    assert out["clone"]["books"] == []


def test_check_rejects_calls_the_schema_would_refuse():
    good = {"bottleneck": "memory", "headline": "", "why": "", "owners": ["micron"], "consensus_trade": ["nvidia"],
            "ranking": [{"input": i, "tightness": 3, "demand_signal": "", "supply_signal": ""} for i in bottleneck.INPUTS],
            "falsifiers": [], "change_vs_last_month": "", "data_gaps": []}
    bottleneck.check(good, OWNERS)
    with pytest.raises(SystemExit, match="unknown company ids: acme"):
        bottleneck.check({**good, "owners": ["acme"]}, OWNERS)
    with pytest.raises(SystemExit, match="each input once"):
        bottleneck.check({**good, "ranking": good["ranking"][:2]}, OWNERS)
    with pytest.raises(SystemExit, match="missing why"):
        bottleneck.check({k: v for k, v in good.items() if k != "why"}, OWNERS)
