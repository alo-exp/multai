"""Shared helpers for platform driver tests."""
import sys
import types
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
ENGINE_DIR = str(PROJECT_ROOT / "skills" / "orchestrator" / "engine")
PLATFORMS_DIR = str(PROJECT_ROOT / "skills" / "orchestrator" / "engine" / "platforms")


def install_platform_stubs():
    for mod in ("playwright", "playwright.async_api", "browser_use", "anthropic"):
        if mod not in sys.modules:
            sys.modules[mod] = types.ModuleType(mod)
    mock_es = types.ModuleType("engine_setup")
    mock_es._load_dotenv = lambda: None
    mock_es._ensure_venv = lambda: None
    mock_es._ensure_dependencies = lambda: None
    sys.modules["engine_setup"] = mock_es
    if ENGINE_DIR not in sys.path:
        sys.path.insert(0, ENGINE_DIR)
    if PLATFORMS_DIR not in sys.path:
        sys.path.insert(0, PLATFORMS_DIR)
