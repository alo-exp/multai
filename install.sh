#!/usr/bin/env bash
# MultAI — plugin install hook entry point (called by hooks/hooks.json on SessionStart)
# Delegates to setup.sh which is the canonical bootstrap.
# Direct users: run `bash setup.sh` from the repo root instead.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$SCRIPT_DIR/setup.sh" "$@"
