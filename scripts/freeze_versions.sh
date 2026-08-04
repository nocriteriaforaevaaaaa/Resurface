#!/usr/bin/env bash
# Captures exact installed versions after a successful `pip install -r requirements.txt`,
# for reproducibility of this fast-moving ML stack.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../.venv/bin/activate"
pip freeze > "$SCRIPT_DIR/../requirements-lock.txt"
echo "Wrote requirements-lock.txt"
