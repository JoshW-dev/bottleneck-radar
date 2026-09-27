from radar import bottleneck, llm

OWNERS = bottleneck.load_owners()


def test_every_owner_and_candidate_is_a_known_company():
    ids = set(OWNERS["companies"])
    for name in bottleneck.INPUTS:
        assert set(OWNERS["inputs"][name]["owners"]) <= ids
    assert set(OWNERS["consensus_candidates"]) <= ids


def test_schema_limits_the_model_to_known_ids():
    schema = bottleneck.schema(OWNERS)
    assert schema["properties"]["bottleneck"]["enum"] == bottleneck.INPUTS
    assert "micron" in schema["properties"]["owners"]["items"]["enum"]
    assert schema["additionalProperties"] is False


def test_validate_drops_owners_from_other_inputs():
    call = {
        "bottleneck": "memory",
        "owners": ["micron", "ge_vernova"],
        "consensus_trade": ["nvidia", "micron"],
        "ranking": [{"input": "memory", "tightness": 4}, {"input": "gas_turbines", "tightness": 5}],
        "data_gaps": [],
    }
    out = bottleneck.validate(call, OWNERS)
    assert out["owners"] == ["micron"]
    assert out["consensus_trade"] == ["nvidia"]
    assert "ge_vernova" in out["data_gaps"][0]
    assert [r["tightness"] for r in out["ranking"]] == [5, 4]


def test_previous_month_wraps_the_year():
    assert bottleneck.previous_month("2026-01") == "2025-12"
    assert bottleneck.previous_month("2026-09") == "2026-08"


def test_tidy_removes_dashes_but_keeps_number_ranges():
    assert llm.tidy("Memory is tight — prices rose.") == "Memory is tight, prices rose."
    assert llm.tidy("$130–145 billion") == "$130-145 billion"
