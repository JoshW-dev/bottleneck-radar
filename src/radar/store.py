"""Reading and writing the files the stages hand to each other."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_json(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str) + "\n")
    return path


def read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n")
    return path


def latest(directory: Path, pattern: str = "*.json") -> Path | None:
    files = sorted(directory.glob(pattern))
    return files[-1] if files else None
