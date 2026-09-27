"""CUSIP-to-ticker lookups through OpenFIGI, cached in data/reference/openfigi.json."""

from __future__ import annotations

import time

import yaml

from .config import CONFIG, DATA, env
from .http import post_json
from .store import read_json, write_json

URL = "https://api.openfigi.com/v3/mapping"
CACHE_FILE = DATA / "reference" / "openfigi.json"
OVERRIDES_FILE = CONFIG / "cusip_overrides.yaml"


def overrides() -> dict[str, str]:
    """Hand-checked fixes for 13F rows filed under the wrong CUSIP (see the file for how each was checked)."""
    if not OVERRIDES_FILE.exists():
        return {}
    return yaml.safe_load(OVERRIDES_FILE.read_text()) or {}


def tickers(cusips: list[str]) -> dict[str, str | None]:
    """US tickers for 13F security codes. Only successful lookups are cached, so misses retry next run."""
    fixed = overrides()
    cache = read_json(CACHE_FILE) if CACHE_FILE.exists() else {}
    missing = [code for code in dict.fromkeys(cusips) if code not in cache and code not in fixed]
    if missing:
        found = _lookup(missing, "ID_CUSIP")
        # Non-US issuers carry CINS codes (they start with a letter), which OpenFIGI files under ID_CINS.
        retry = [code for code in missing if not found.get(code)]
        if retry:
            found.update({code: t for code, t in _lookup(retry, "ID_CINS").items() if t})
        cache.update({code: t for code, t in found.items() if t})
        write_json(CACHE_FILE, dict(sorted(cache.items())))
    return {code: fixed.get(code) or cache.get(code) for code in cusips}


def _lookup(codes: list[str], id_type: str) -> dict[str, str | None]:
    key = env("OPENFIGI_API_KEY")
    headers = {"X-OPENFIGI-APIKEY": key} if key else {}
    batch_size = 100 if key else 10
    out: dict[str, str | None] = {}
    for start in range(0, len(codes), batch_size):
        if start:
            time.sleep(0.3 if key else 2.5)  # keyless callers get 25 requests a minute
        batch = codes[start : start + batch_size]
        jobs = [{"idType": id_type, "idValue": code, "exchCode": "US"} for code in batch]
        for code, result in zip(batch, post_json(URL, jobs, headers=headers)):
            matches = result.get("data") or []
            out[code] = matches[0]["ticker"] if matches else None
    return out
