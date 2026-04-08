"""Shared helpers for platform driver tests."""

import sys
import types
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
ENGINE_DIR = str(PROJECT_ROOT / "skills" / "orchestrator" / "engine")
PLATFORMS_DIR = str(PROJECT_ROOT / "skills" / "orchestrator" / "engine" / "platforms")


def install_platform_stubs():
    """Stub all platform-level heavy deps before importing engine code."""
    # engine_setup stub
    mock_es = types.ModuleType("engine_setup")
    mock_es._load_dotenv = lambda: None
    mock_es._ensure_venv = lambda: None
    mock_es._ensure_dependencies = lambda: None
    sys.modules["engine_setup"] = mock_es

    # playwright stubs
    pw = types.ModuleType("playwright")
    pw_api = types.ModuleType("playwright.async_api")

    class _MockPage:
        pass

    pw_api.Page = _MockPage
    pw_api.async_playwright = None
    pw_api.BrowserContext = None
    sys.modules["playwright"] = pw
    sys.modules["playwright.async_api"] = pw_api

    # browser_use stub
    bu = types.ModuleType("browser_use")
    bu.Agent = None
    bu.BrowserSession = None
    sys.modules["browser_use"] = bu

    # agent_fallback stub
    af = types.ModuleType("agent_fallback")
    af.AgentFallbackManager = None
    af.FallbackStep = None
    sys.modules["agent_fallback"] = af

    # anthropic stub
    anth = types.ModuleType("anthropic")
    sys.modules["anthropic"] = anth

    # platforms stub
    mock_platforms = types.ModuleType("platforms")
    mock_platforms.ALL_PLATFORMS = {}
    sys.modules["platforms"] = mock_platforms

    # Add paths
    if ENGINE_DIR not in sys.path:
        sys.path.insert(0, ENGINE_DIR)
    if PLATFORMS_DIR not in sys.path:
        sys.path.insert(0, PLATFORMS_DIR)
