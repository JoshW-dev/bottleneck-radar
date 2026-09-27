#!/usr/bin/env bash
# Local monthly run for the private stage. GitHub Actions commits the public refresh;
# this pulls it, reads your IBKR positions and writes private/<month>/exposure.md and a
# fresh order list. Nothing here gets committed or pushed.
set -euo pipefail
cd "$(dirname "$0")/.."

git pull --ff-only --quiet
uv run radar ibkr
uv run radar exposure
uv run radar clone
