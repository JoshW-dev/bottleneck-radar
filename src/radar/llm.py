"""Structured JSON answers from Claude, with token and cost accounting."""

from __future__ import annotations

import json
import re
from typing import Any

from .config import env

WRITER_MODEL = env("RADAR_WRITER_MODEL", "claude-sonnet-5")
READER_MODEL = env("RADAR_READER_MODEL", "claude-haiku-4-5")
# US$ per million tokens (input, output), for the cost line in each output file.
PRICES = {"claude-sonnet-5": (2.0, 10.0), "claude-haiku-4-5": (1.0, 5.0)}


def available() -> bool:
    return bool(env("ANTHROPIC_API_KEY") or env("ANTHROPIC_AUTH_TOKEN"))


def structured(
    system: str,
    user: str,
    schema: dict[str, Any],
    *,
    model: str = WRITER_MODEL,
    effort: str | None = "high",
    max_tokens: int = 16000,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """One request whose answer must match `schema`. Returns (answer, usage)."""
    import anthropic

    output_config: dict[str, Any] = {"format": {"type": "json_schema", "schema": schema}}
    if effort and "haiku" not in model:  # Haiku 4.5 doesn't take an effort setting
        output_config["effort"] = effort
    response = anthropic.Anthropic().messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config=output_config,
    )
    if response.stop_reason == "refusal":
        raise RuntimeError(f"{model} declined the request")
    if response.stop_reason == "max_tokens":
        raise RuntimeError(f"{model} hit max_tokens={max_tokens} before finishing")
    text = next(block.text for block in response.content if block.type == "text")
    price_in, price_out = PRICES.get(model, (0.0, 0.0))
    usage = {
        "model": model,
        "request_id": response._request_id,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "cost_usd": round(
            (response.usage.input_tokens * price_in + response.usage.output_tokens * price_out) / 1e6, 4
        ),
    }
    return json.loads(text), usage


def tidy(text: str) -> str:
    """House style for generated prose: no em or en dashes, except en dashes inside number ranges."""
    text = re.sub(r"(?<=\d)\s*–\s*(?=\d)", "-", text)
    return re.sub(r"\s*[—–]\s*", ", ", text)
