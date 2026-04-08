"""Shared pytest fixtures and helpers for all MultAI unit tests.

Provides:
  - mock_page fixture: canonical async MockPage for all platform driver tests
  - _stub_engine_setup(): plain callable helper (NOT a fixture) to stub engine_setup in sys.modules
  - install_stubs(): stubs sys.modules for all heavy runtime dependencies
  - ENGINE_DIR constant and sys.path setup
"""

import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

ENGINE_DIR = str(Path(__file__).parent.parent / "skills" / "orchestrator" / "engine")

if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)


@pytest.fixture
def mock_page():
    """Canonical async MockPage for all platform driver tests."""
    page = MagicMock()
    page.url = "https://example.com"

    # Async methods
    page.title = AsyncMock(return_value="Page Title")
    page.goto = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.evaluate = AsyncMock(return_value="")
    page.bring_to_front = AsyncMock()

    # keyboard
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock()
    page.keyboard.type = AsyncMock()

    # Locator factory — every call to locator/get_by_text/get_by_role returns
    # a MagicMock with async count/is_visible/click/get_attribute methods.
    def _make_locator(count=0, visible=False, text=""):
        loc = MagicMock()
        loc.first = loc
        loc.count = AsyncMock(return_value=count)
        loc.is_visible = AsyncMock(return_value=visible)
        loc.click = AsyncMock()
        loc.get_attribute = AsyncMock(return_value=None)
        loc.inner_text = AsyncMock(return_value=text)
        loc.evaluate = AsyncMock(return_value=None)
        loc.fill = AsyncMock()
        loc.dispatch_event = AsyncMock()
        loc.type = AsyncMock()
        loc.nth = lambda n: loc
        return loc

    page.locator = MagicMock(side_effect=lambda sel: _make_locator())
    page.get_by_text = MagicMock(side_effect=lambda text, **kw: _make_locator())
    page.get_by_role = MagicMock(side_effect=lambda role, **kw: _make_locator())

    # on() event binding
    page.on = MagicMock()

    # frames (for ChatGPT DEEP mode)
    frame = MagicMock()
    frame.url = "about:blank"
    frame.evaluate = AsyncMock(return_value=0)
    page.frames = [frame]
    page.main_frame = frame

    # expect_download context manager
    dl = MagicMock()
    dl.__aenter__ = AsyncMock(return_value=dl)
    dl.__aexit__ = AsyncMock(return_value=False)
    dl.value = AsyncMock(return_value=MagicMock(path=AsyncMock(return_value=None)))
    page.expect_download = MagicMock(return_value=dl)

    return page


def _stub_engine_setup():
    """Install a fake engine_setup module into sys.modules.

    Returns the stub module. Callers that need the REAL engine_setup
    (e.g. Plan 03 test_engine_setup.py) MUST:
      1. sys.modules.pop("engine_setup", None)
      2. import the real module
      3. In teardown: call _stub_engine_setup() to restore the stub
    """
    es = types.ModuleType("engine_setup")
    es._load_dotenv = lambda: None
    es._ensure_venv = lambda: None
    es._ensure_dependencies = lambda: None
    sys.modules["engine_setup"] = es
    return es


def install_stubs(platform_name, url):
    """Stub sys.modules for all heavy runtime dependencies.

    Called by platform driver test modules before importing any engine code.
    Returns the config stub module so callers can add extra attributes.
    """
    import os
    _stub_engine_setup()

    # playwright stubs
    pw = types.ModuleType("playwright")
    pw_api = types.ModuleType("playwright.async_api")
    pw_api.Page = MagicMock
    pw_api.async_playwright = MagicMock
    pw_api.BrowserContext = MagicMock
    sys.modules["playwright"] = pw
    sys.modules["playwright.async_api"] = pw_api

    # config stub — returned so callers can set extra attributes
    config = types.ModuleType("config")
    config.PLATFORM_URLS = {platform_name: url}
    config.PLATFORM_DISPLAY_NAMES = {platform_name: platform_name.capitalize()}
    config.INJECTION_METHODS = {platform_name: "execCommand"}
    config.POLL_INTERVAL = 0
    config.TIMEOUTS = {}
    config.STATUS_COMPLETE = "complete"
    config.STATUS_FAILED = "failed"
    config.STATUS_NEEDS_LOGIN = "needs_login"
    config.STATUS_PARTIAL = "partial"
    config.STATUS_RATE_LIMITED = "rate_limited"
    config.STATUS_TIMEOUT = "timeout"
    config.TimeoutConfig = type("TimeoutConfig", (), {"regular": 60, "deep": 300})
    config.DEFAULT_TIER = "free"
    config.STAGGER_DELAY = 0
    config.RATE_LIMIT_STATE_DIR = "/tmp"
    config.RATE_LIMITS = {}
    config.PLATFORM_DISPLAY_NAMES.update({
        "claude_ai": "Claude.ai", "chatgpt": "ChatGPT", "copilot": "Copilot",
        "perplexity": "Perplexity", "grok": "Grok", "deepseek": "DeepSeek",
        "gemini": "Gemini",
    })
    sys.modules["config"] = config

    # prompt_echo stub
    pe = types.ModuleType("prompt_echo")
    pe.is_prompt_echo = lambda text, sigs: False
    pe.auto_extract_prompt_sigs = lambda text: []
    sys.modules["prompt_echo"] = pe

    # agent_fallback stub
    af = types.ModuleType("agent_fallback")
    af.AgentFallbackManager = MagicMock
    af.FallbackStep = MagicMock
    sys.modules["agent_fallback"] = af

    # browser_use stub
    bu = types.ModuleType("browser_use")
    bu.Agent = MagicMock
    bu.BrowserSession = MagicMock
    sys.modules["browser_use"] = bu

    # platforms package — point __path__ at real directory so submodules load
    platforms_path = os.path.join(ENGINE_DIR, "platforms")
    mock_platforms = types.ModuleType("platforms")
    mock_platforms.__path__ = [platforms_path]
    mock_platforms.__package__ = "platforms"
    mock_platforms.ALL_PLATFORMS = {
        "claude_ai": MagicMock(),
        "chatgpt": MagicMock(),
        "copilot": MagicMock(),
        "perplexity": MagicMock(),
        "grok": MagicMock(),
        "deepseek": MagicMock(),
        "gemini": MagicMock(),
    }
    sys.modules["platforms"] = mock_platforms

    return config
