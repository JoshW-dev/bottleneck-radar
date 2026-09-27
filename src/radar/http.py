"""HTTP helpers: a small disk cache, SEC pacing and the headers each source expects."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import httpx

from .config import CACHE, env, require_env

DEFAULT_UA = "bottleneck-radar/0.1 (+https://github.com/JoshW-dev/bottleneck-radar)"
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Safari/605.1.15"
)
SEC_MIN_INTERVAL = 0.15  # SEC's fair-access limit is 10 requests a second
RETRY_STATUSES = {429, 500, 502, 503, 504}

_last_sec_request = 0.0


def sec_user_agent() -> str:
    ua = require_env(
        "SEC_USER_AGENT",
        "SEC rejects scripts without a contact, so set it to 'Your Name you@example.com' in .env.",
    )
    if "@" not in ua:
        raise SystemExit("SEC_USER_AGENT needs a contact email, like 'Jane Doe jane@example.com'.")
    return ua


def _cache_file(url: str, params: dict | None) -> Path:
    key = url + "?" + json.dumps(params or {}, sort_keys=True)
    return CACHE / hashlib.sha256(key.encode()).hexdigest()[:32]


def _pace_sec() -> None:
    global _last_sec_request
    wait = SEC_MIN_INTERVAL - (time.monotonic() - _last_sec_request)
    if wait > 0:
        time.sleep(wait)
    _last_sec_request = time.monotonic()


def get(
    url: str,
    *,
    sec: bool = False,
    browser: bool = False,
    headers: dict | None = None,
    params: dict | None = None,
    ttl_hours: float = 12,
) -> bytes:
    """GET a URL, reusing a cached copy younger than ttl_hours.

    Pass ttl_hours=0 for anything private: nothing gets written to disk. Errors
    quote the URL without its query string, so tokens in params stay out of logs.
    """
    cache_file = _cache_file(url, params)
    use_cache = ttl_hours > 0 and not env("RADAR_NO_CACHE")
    if use_cache and cache_file.exists() and time.time() - cache_file.stat().st_mtime < ttl_hours * 3600:
        return cache_file.read_bytes()

    request_headers = {"User-Agent": BROWSER_UA if browser else DEFAULT_UA}
    if sec:
        request_headers["User-Agent"] = sec_user_agent()
    request_headers.update(headers or {})

    for attempt in range(4):
        if sec:
            _pace_sec()
        response = httpx.get(url, headers=request_headers, params=params, timeout=60, follow_redirects=True)
        if response.status_code not in RETRY_STATUSES:
            break
        time.sleep(2**attempt)
    if response.is_error:
        raise httpx.HTTPStatusError(
            f"HTTP {response.status_code} from {url}", request=response.request, response=response
        )
    if use_cache:
        CACHE.mkdir(parents=True, exist_ok=True)
        cache_file.write_bytes(response.content)
    return response.content


def get_json(url: str, **kwargs: Any) -> Any:
    return json.loads(get(url, **kwargs))


def post_json(url: str, payload: Any, *, headers: dict | None = None) -> Any:
    request_headers = {"User-Agent": DEFAULT_UA, "Content-Type": "application/json"} | (headers or {})
    for attempt in range(4):
        response = httpx.post(url, json=payload, headers=request_headers, timeout=60)
        if response.status_code not in RETRY_STATUSES:
            break
        time.sleep(2 ** (attempt + 2))
    response.raise_for_status()
    return response.json()
