"""Paths and environment settings shared by every stage."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(os.getenv("RADAR_HOME") or Path(__file__).resolve().parents[2])
load_dotenv(ROOT / ".env")

DATA = ROOT / "data"  # public outputs, committed to git
PRIVATE = ROOT / "private"  # anything tied to your account, gitignored
CACHE = ROOT / ".cache"  # raw HTTP responses, gitignored
CONFIG = ROOT / "config"  # hand-maintained inputs: assumptions, owners, manual figures


def month_key(day: date | None = None) -> str:
    return f"{day or date.today():%Y-%m}"


def env(name: str, default: str | None = None) -> str | None:
    return os.getenv(name) or default


def require_env(name: str, hint: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"{name} is not set. {hint}")
    return value
