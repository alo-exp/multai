#!/usr/bin/env bash
# MultAI — one-time bootstrap for the Playwright/Browser-Use engine
# Run from the repo root: bash setup.sh
# Optional: bash setup.sh --with-fallback   (also installs browser-use agent)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENGINE_DIR="$SCRIPT_DIR/skills/orchestrator/engine"
VENV_DIR="$ENGINE_DIR/.venv"
WITH_FALLBACK=false

for arg in "$@"; do
  [[ "$arg" == "--with-fallback" ]] && WITH_FALLBACK=true
done

# ── helpers ──────────────────────────────────────────────────────────────────
info()    { echo "  → $*"; }
success() { echo "  ✓ $*"; }
warn()    { echo "  ⚠ $*"; }
die()     { echo "  ✗ ERROR: $*" >&2; exit 1; }

echo ""
echo "MultAI Setup"
echo "────────────────────────────────────────────"

# ── Python version check ─────────────────────────────────────────────────────
info "Checking Python version..."
PYTHON=$(command -v python3 || die "python3 not found. Install Python 3.11+ first.")
PY_VER=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$("$PYTHON" -c "import sys; print(sys.version_info.major)")
PY_MINOR=$("$PYTHON" -c "import sys; print(sys.version_info.minor)")

if [[ "$PY_MAJOR" -lt 3 ]] || [[ "$PY_MAJOR" -eq 3 && "$PY_MINOR" -lt 11 ]]; then
  die "Python 3.11+ required (found $PY_VER). Please upgrade: https://www.python.org/downloads/"
fi
success "Python $PY_VER"

# ── Virtual environment ───────────────────────────────────────────────────────
if [[ -d "$VENV_DIR" ]]; then
  info "Virtual environment already exists at skills/orchestrator/engine/.venv — skipping creation."
else
  info "Creating virtual environment at skills/orchestrator/engine/.venv ..."
  "$PYTHON" -m venv "$VENV_DIR"
  success "Virtual environment created"
fi

PIP="$VENV_DIR/bin/pip"
PYTHON_VENV="$VENV_DIR/bin/python"

# ── Core dependencies ─────────────────────────────────────────────────────────
info "Installing core dependencies (playwright, openpyxl)..."
"$PIP" install --quiet --upgrade pip
"$PIP" install --quiet "playwright>=1.40.0" "openpyxl>=3.1.0"
success "Core dependencies installed"

# ── Playwright browsers ───────────────────────────────────────────────────────
info "Installing Playwright Chromium browser..."
"$PYTHON_VENV" -m playwright install chromium
success "Chromium installed"

# ── Optional: browser-use fallback ───────────────────────────────────────────
if [[ "$WITH_FALLBACK" == true ]]; then
  info "Installing browser-use agent fallback (--with-fallback)..."
  "$PIP" install --quiet "browser-use==0.12.2" "anthropic>=0.76.0" "fastmcp>=2.0.0"
  success "browser-use fallback installed"
else
  warn "Skipping browser-use fallback (add --with-fallback to enable it)"
fi

# ── Smoke test ────────────────────────────────────────────────────────────────
info "Running smoke test..."
"$PYTHON_VENV" "$ENGINE_DIR/orchestrator.py" --budget --tier free > /dev/null 2>&1 \
  && success "Engine smoke test passed" \
  || warn "Smoke test returned non-zero — check your Chrome / profile setup (see skills/orchestrator/platform-setup.md)"

echo ""
echo "────────────────────────────────────────────"
echo "  Setup complete. You're ready to use MultAI."
echo ""
echo "  Next: open Claude Code in this directory and invoke a skill, e.g.:"
echo "    /orchestrator  →  route a research task"
echo "    /landscape-researcher  →  market landscape analysis"
echo "    /solution-researcher   →  competitive intelligence on a product"
echo ""
echo "  See USER-GUIDE.md for full usage instructions."
echo ""
