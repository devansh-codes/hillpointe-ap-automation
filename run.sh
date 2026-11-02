#!/usr/bin/env bash
# Process a folder of invoices:   ./run.sh path/to/folder        (add --what-if to preview without recording)
set -euo pipefail
cd "$(dirname "$0")"
if ! command -v uv >/dev/null 2>&1; then
  echo "First-time setup: installing uv (Python package manager)..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
[ -f .env ] && set -a && . ./.env && set +a
uv sync --quiet
if [ $# -eq 0 ]; then echo "Usage: ./run.sh <folder-of-invoices> [--what-if]"; exit 1; fi
uv run ap run "$@" --open
