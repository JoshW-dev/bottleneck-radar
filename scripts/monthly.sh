#!/usr/bin/env bash
# Monthly run for cron: every stage, then commit and push the public outputs in data/.
# private/ (positions, order list, exposure) never leaves this machine.
set -euo pipefail
cd "$(dirname "$0")/.."

git pull --ff-only --quiet
uv run radar run
git add data
if ! git diff --cached --quiet; then
  git commit --quiet -m "data: $(date +%Y-%m) run"
  git push --quiet
fi
