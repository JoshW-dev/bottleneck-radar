from pathlib import Path

import pytest

from radar import exposure, ibkr_flex
from radar.bottleneck import load_owners

STATEMENT_XML = (Path(__file__).parent / "fixtures" / "flex_statement.xml").read_bytes()
SEND_OK = b"<FlexStatementResponse><Status>Success</Status><ReferenceCode>42</ReferenceCode><Url>https://example.test/GetStatement</Url></FlexStatementResponse>"
IN_PROGRESS = b"<FlexStatementResponse><Status>Warn</Status><ErrorCode>1019</ErrorCode><ErrorMessage>Statement generation in progress. Please try again shortly.</ErrorMessage></FlexStatementResponse>"
BAD_TOKEN = b"<FlexStatementResponse><Status>Fail</Status><ErrorCode>1015</ErrorCode><ErrorMessage>Token is invalid.</ErrorMessage></FlexStatementResponse>"


def test_parse_statement_skips_lot_rows_and_converts_to_base():
    s = ibkr_flex.parse_statement(STATEMENT_XML)
    assert s["account"] == "U****567"
    assert s["nav"] == 100000
    assert [p["symbol"] for p in s["positions"]] == ["MU", "MU    261218C01100000", "NVDA", "ENR"]
    enr = s["positions"][-1]
    assert enr["value"] == 10000 and enr["value_base"] == pytest.approx(11000)
    assert s["positions"][1]["underlying"] == "MU"


def test_fetch_statement_polls_until_ready(monkeypatch):
    replies = iter([SEND_OK, IN_PROGRESS, STATEMENT_XML])
    calls = []

    def fake_get(url, params, ttl_hours):
        assert ttl_hours == 0  # nothing about the account touches the disk cache
        calls.append((url, params["q"]))
        return next(replies)

    monkeypatch.setattr(ibkr_flex, "get", fake_get)
    monkeypatch.setattr(ibkr_flex.time, "sleep", lambda s: None)
    assert ibkr_flex.fetch_statement("token", "123") == STATEMENT_XML
    assert calls[0] == (ibkr_flex.SEND_URL, "123")
    assert calls[1:] == [("https://example.test/GetStatement", "42")] * 2


def test_fetch_statement_reports_ibkr_errors(monkeypatch):
    monkeypatch.setattr(ibkr_flex, "get", lambda url, params, ttl_hours: BAD_TOKEN)
    with pytest.raises(ibkr_flex.FlexError, match="1015: Token is invalid"):
        ibkr_flex.fetch_statement("bad", "123")


def test_exposure_buckets_follow_the_call():
    statement = ibkr_flex.parse_statement(STATEMENT_XML)
    call = {"bottleneck": "memory", "owners": ["micron", "sk_hynix"], "consensus_trade": ["nvidia"]}
    result = exposure.compute(statement, call, load_owners())
    shares = result["shares"]
    assert shares["bottleneck"] == pytest.approx(0.266456)  # MU stock plus the MU call
    assert shares["consensus"] == pytest.approx(0.30)
    assert shares["other"] == pytest.approx(0.11)  # Siemens Energy isn't a memory owner
    assert shares["cash_and_rest"] == pytest.approx(1 - 0.676456)
    assert result["denominator_is_nav"]
