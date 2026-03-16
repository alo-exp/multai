#!/usr/bin/env bash
# multi-ai-skills — one-shot setup script
# Installs core Python dependencies, Playwright browsers, and creates a .env template.
# Run after cloning / after /plugin install.
#
# Usage:
#   bash install.sh              # core install only
#   bash install.sh --with-fallback   # also set up browser-use agent-fallback venv

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${GREEN}[install]${NC} $*"; }
warn() { echo -e "${YELLOW}[install]${NC} $*"; }
fail() { echo -e "${RED}[install]${NC} $*" >&2; exit 1; }

# ── 1. Python version check ────────────────────────────────────────────────
PYTHON=$(command -v python3 || true)
[[ -z "$PYTHON" ]] && fail "python3 not found. Install Python ≥ 3.10 and re-run."
PY_VER=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
log "Python $PY_VER detected"

# ── 2. Core pip install ────────────────────────────────────────────────────
log "Installing core Python dependencies..."
"$PYTHON" -m pip install --quiet --upgrade pip
"$PYTHON" -m pip install --quiet -r "$SCRIPT_DIR/requirements.txt"
log "Core dependencies installed."

# ── 3. Playwright browser install ─────────────────────────────────────────
log "Installing Playwright Chromium browser..."
"$PYTHON" -m playwright install chromium
log "Playwright Chromium installed."

# ── 4. .env template ──────────────────────────────────────────────────────
ENV_FILE="$SCRIPT_DIR/.env"
if [[ ! -f "$ENV_FILE" ]]; then
    log "Creating .env template..."
    cat > "$ENV_FILE" <<'EOF'
# multi-ai-skills environment configuration
# Copy this file, fill in any optional keys, and keep it out of version control.

# ── Agent Fallback (optional) ──────────────────────────────────────────────
# Provide one key to enable browser-use agent fallback for tricky platforms.
# ANTHROPIC_API_KEY=your_anthropic_key_here
# GOOGLE_API_KEY=your_google_api_key_here
EOF
    log ".env template created at $ENV_FILE"
else
    warn ".env already exists — skipping template creation."
fi

# ── 5. Optional: browser-use fallback venv ────────────────────────────────
if [[ "${1:-}" == "--with-fallback" ]]; then
    log "Setting up browser-use agent-fallback virtual environment..."

    FALLBACK_VENV="$SCRIPT_DIR/.venv-fallback"
    if [[ ! -d "$FALLBACK_VENV" ]]; then
        "$PYTHON" -m venv "$FALLBACK_VENV"
        log "Fallback venv created at $FALLBACK_VENV"
    else
        warn "Fallback venv already exists — skipping creation."
    fi

    FALLBACK_PIP="$FALLBACK_VENV/bin/pip"
    log "Installing fallback extras (browser-use, anthropic, fastmcp)..."
    "$FALLBACK_PIP" install --quiet --upgrade pip
    "$FALLBACK_PIP" install --quiet ".[fallback]" 2>/dev/null \
        || "$FALLBACK_PIP" install --quiet \
               "browser-use==0.12.2" \
               "anthropic>=0.76.0" \
               "fastmcp>=2.0.0"

    "$FALLBACK_VENV/bin/python" -m playwright install chromium
    log "Fallback venv ready. Activate with: source $FALLBACK_VENV/bin/activate"
fi

# ── Done ───────────────────────────────────────────────────────────────────
echo ""
log "Setup complete!"
echo ""
echo "  Next steps:"
echo "    1. Edit .env and add any optional API keys (ANTHROPIC_API_KEY / GOOGLE_API_KEY)"
echo "    2. Open Claude Code and use a skill, e.g.:"
echo "         /orchestrate  — run a prompt on all 7 AI platforms"
echo "         /solution-researcher  — research a product URL"
echo "         /landscape-researcher — produce a market landscape report"
echo ""
