import json
from datetime import date

import pytest

from radar import predictions as pr


def pred(pid="p1", confidence=0.8, due="2026-10-01", **check):
    return {"id": pid, "group": "memory", "statement": "s", "why": "w", "confidence": confidence, "due": due, "unit": "pct",
            "check": check or {"metric": "korea", "field": "memory_yoy", "period": "2026-09", "op": ">=", "value": 1.0}}


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setattr(pr, "DATA", tmp_path)
    return pr.Context(date(2026, 10, 2))


def test_fingerprint_changes_when_a_prediction_is_edited():
    a = [pred()]
    b = [pred(confidence=0.9)]
    assert pr.fingerprint(a) == pr.fingerprint(json.loads(json.dumps(a)))
    assert pr.fingerprint(a) != pr.fingerprint(b)


def test_validate_rejects_bad_predictions():
    pr.validate([pred()])
    with pytest.raises(SystemExit, match="unknown metric"):
        pr.validate([pred(metric="vibes", op=">=")])
    with pytest.raises(SystemExit, match="confidence"):
        pr.validate([pred(confidence=0.3)])
    with pytest.raises(SystemExit, match="already used"):
        pr.validate([pred(), pred()])


def test_freeze_stamps_the_set_and_refuses_to_overwrite_it(tmp_path, monkeypatch):
    monkeypatch.setattr(pr, "DATA", tmp_path)
    monkeypatch.setattr(pr, "SETS", tmp_path / "predictions")
    src = tmp_path / "in.json"
    src.write_text(json.dumps({"predictions": [pred()]}))
    frozen = pr.freeze(str(src), "tester", "2026-09")
    assert frozen["made_at"].endswith("Z") and frozen["made_by"] == "tester"
    assert pr.verify(frozen)
    with pytest.raises(SystemExit, match="frozen"):
        pr.freeze(str(src), "tester", "2026-09")


def test_korea_resolves_from_committed_data(ctx):
    ctx.supply = [{"memory": {"period": "2026-09", "memory_yoy": 1.4, "source": "motir"}}]
    r = pr.check_one(pred(), ctx, "2026-10-02T22:00:00Z")
    assert r["status"] == "right" and r["value"] == 1.4 and r["observed"] == "2026-10-01" and r["resolved_at"] == "2026-10-02T22:00:00Z"
    ctx.supply = [{"memory": {"period": "2026-09", "memory_yoy": 0.8}}]
    assert pr.check_one(pred(), ctx, "t")["status"] == "wrong"


def test_taiwan_growth_comes_from_the_history(ctx):
    ctx.supply = [{"export_orders": {"electronics": {"history": [["2025-09", 100.0], ["2026-09", 170.0]]}}}]
    r = pr.check_one(pred(metric="taiwan", series="electronics", period="2026-09", op=">=", value=0.6), ctx, "t")
    assert r["status"] == "right" and r["value"] == pytest.approx(0.7)


def test_no_data_stays_open_then_goes_void(ctx):
    p = pred(metric="call", month="2026-10", field="bottleneck", op="==", value="memory")
    assert pr.check_one(p, ctx, "t")["status"] == "open"
    ctx.today = date(2026, 11, 15)
    assert pr.check_one(p, ctx, "t")["status"] == "void"


def closes_ctx(ctx, series, monkeypatch):
    monkeypatch.setattr(pr.prices, "usd_history", lambda symbol, start, end=None: series[symbol])
    return ctx


def test_a_price_race_reports_how_it_stands_until_the_end_date(ctx, monkeypatch):
    days = ["2026-09-25", "2026-09-28", "2026-10-30"]
    series = {"SPY": dict(zip(days, [100, 100, 105])), "MU": dict(zip(days, [50, 50, 60])), "GEV": dict(zip(days, [10, 10, 10]))}
    closes_ctx(ctx, series, monkeypatch)
    p = pred(due="2026-12-31", metric="prices.beat", a=["MU"], b=["SPY"], start="2026-09-28", end="2026-12-31")
    r = pr.check_one(p, ctx, "t")
    assert r["status"] == "open" and r["so_far"] == pytest.approx(0.15) and r["leaning"] == "right"
    # A later check asking for another symbol still gets it.
    gev = pr.check_one(pred("p2", due="2026-12-31", metric="prices.beat", a=["GEV"], b=["SPY"], start="2026-09-28", end="2026-12-31"), ctx, "t")
    assert gev["so_far"] == pytest.approx(-0.05)
    series["SPY"]["2026-12-31"], series["MU"]["2026-12-31"] = 120, 55
    later = pr.Context(ctx.today)
    r = pr.check_one(p, later, "t")
    assert r["status"] == "wrong" and r["value"] == pytest.approx(-0.1) and r["observed"] == "2026-12-31"


def test_a_drawdown_resolves_as_soon_as_it_happens(ctx, monkeypatch):
    days = ["2026-09-28", "2026-10-05", "2026-10-12"]
    closes_ctx(ctx, {"SPY": dict(zip(days, [1, 1, 1])), "MU": dict(zip(days, [100, 120, 84]))}, monkeypatch)
    p = pred(due="2026-12-31", metric="prices.drawdown", basket=["MU"], start="2026-09-28", end="2026-12-31", value=-0.25)
    r = pr.check_one(p, ctx, "t")
    assert r["status"] == "right" and r["value"] == pytest.approx(-0.3) and r["observed"] == "2026-10-12"


def test_settled_results_never_change(tmp_path, monkeypatch):
    monkeypatch.setattr(pr, "DATA", tmp_path)
    monkeypatch.setattr(pr, "SETS", tmp_path / "predictions")
    monkeypatch.setattr(pr, "RESULTS", tmp_path / "prediction-results.json")
    p = pred()
    s = {"set": "2026-09", "made_at": "x", "made_by": "t", "sha256": pr.fingerprint([p]), "predictions": [p]}
    (tmp_path / "predictions").mkdir()
    (tmp_path / "predictions" / "2026-09.json").write_text(json.dumps(s))
    (tmp_path / "2026-10").mkdir()
    (tmp_path / "2026-10" / "supply.json").write_text(json.dumps({"memory": {"period": "2026-09", "memory_yoy": 1.4}}))
    first = pr.run(date(2026, 10, 2))["results"]["p1"]
    (tmp_path / "2026-10" / "supply.json").write_text(json.dumps({"memory": {"period": "2026-09", "memory_yoy": 0.5}}))
    out = pr.run(date(2026, 10, 3))
    assert out["results"]["p1"] == first and out["sets"][0]["intact"]


def test_summary_scores_only_resolved_predictions():
    ps = [pred("a", 0.9), pred("b", 0.6), pred("c", 0.7), pred("d", 0.8)]
    results = {"a": {"status": "right"}, "b": {"status": "wrong"}, "c": {"status": "open"}, "d": {"status": "void"}}
    s = pr.summarize(ps, results)
    assert (s["right"], s["wrong"], s["open"], s["void"], s["resolved"]) == (1, 1, 1, 1, 2)
    assert s["hit_rate"] == 0.5 and s["expected_right"] == 1.5
    assert s["brier"] == pytest.approx(((0.9 - 1) ** 2 + 0.6**2) / 2)


def test_the_dashboard_shows_results_and_the_fingerprint():
    from radar import site

    ps = [pred("a", 0.9), pred("b", 0.6, due="2026-12-31"), pred("c", 0.7, due="2026-12-31")]
    s = {"set": "2026-09", "made_at": "2026-09-27T22:05:37Z", "made_by": "tester", "note": "", "sha256": pr.fingerprint(ps), "predictions": ps}
    results = {"a": {"status": "right", "value": 1.4, "observed": "2026-10-01"}, "b": {"status": "open", "so_far": 0.2}, "c": {"status": "open"}}
    checked = {"checked_at": "2026-10-01T22:00:00Z", "sets": [{"set": "2026-09", "intact": True}], "results": results,
               "summary": pr.summarize(ps, results)}
    html = site.predictions_section({"sets": [s], "results": checked})
    assert "22:05 UTC on Sep 27, 2026" in html and pr.fingerprint(ps)[:16] in html
    assert "1 of 3" in html and "Came true" in html and "+20% so far" in html
    assert html.count('class="pt-dot') == 3
    assert site.predictions_section(None) == ""
