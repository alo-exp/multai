"""Tests for ChatGPT platform driver — 100% coverage."""

import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Stubs ──────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent.parent
ENGINE_DIR = str(PROJECT_ROOT / "skills" / "orchestrator" / "engine")

_es = types.ModuleType("engine_setup")
_es._load_dotenv = lambda: None
_es._ensure_venv = lambda: None
_es._ensure_dependencies = lambda: None
sys.modules["engine_setup"] = _es

_pw = types.ModuleType("playwright")
_pw_api = types.ModuleType("playwright.async_api")
_pw_api.Page = MagicMock
_pw_api.async_playwright = MagicMock
_pw_api.BrowserContext = MagicMock
sys.modules["playwright"] = _pw
sys.modules["playwright.async_api"] = _pw_api

_bu = types.ModuleType("browser_use")
_bu.Agent = MagicMock
_bu.BrowserSession = MagicMock
sys.modules["browser_use"] = _bu

_af = types.ModuleType("agent_fallback")
_af.AgentFallbackManager = MagicMock
_af.FallbackStep = MagicMock
sys.modules["agent_fallback"] = _af

_anth = types.ModuleType("anthropic")
sys.modules["anthropic"] = _anth

if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

# ── Import under test ──────────────────────────────────────────────────────────
from platforms.chatgpt import ChatGPT  # noqa: E402


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_loc(count=0, visible=False, text=""):
    loc = MagicMock()
    loc.first = loc
    loc.count = AsyncMock(return_value=count)
    loc.is_visible = AsyncMock(return_value=visible)
    loc.click = AsyncMock()
    loc.get_attribute = AsyncMock(return_value=None)
    loc.inner_text = AsyncMock(return_value=text)
    loc.evaluate = AsyncMock(return_value=0)
    loc.nth = lambda n: loc
    return loc


def _driver():
    d = ChatGPT()
    d.agent_manager = None
    d.prompt_sigs = []
    return d


# ══════════════════════════════════════════════════════════════════════════════
# check_rate_limit
# ══════════════════════════════════════════════════════════════════════════════

async def test_check_rate_limit_found(mock_page):
    """Pattern element visible → returns pattern string."""
    driver = _driver()
    loc = _make_loc(count=1, visible=True)
    mock_page.get_by_text = MagicMock(return_value=loc)
    mock_page.evaluate = AsyncMock(return_value="")
    result = await driver.check_rate_limit(mock_page)
    assert result is not None
    assert isinstance(result, str)


async def test_check_rate_limit_not_found_via_body_text(mock_page):
    """Element not visible; body text contains pattern → returns pattern."""
    driver = _driver()
    loc = _make_loc(count=0)
    mock_page.get_by_text = MagicMock(return_value=loc)
    mock_page.evaluate = AsyncMock(return_value="you've reached your limit on this service")
    result = await driver.check_rate_limit(mock_page)
    assert result is not None  # "You've reached your limit" or "reached your limit"


async def test_check_rate_limit_none(mock_page):
    """No matching element or body text → returns None."""
    driver = _driver()
    loc = _make_loc(count=0)
    mock_page.get_by_text = MagicMock(return_value=loc)
    mock_page.evaluate = AsyncMock(return_value="all good here nothing special")
    result = await driver.check_rate_limit(mock_page)
    assert result is None


async def test_check_rate_limit_get_by_text_exception(mock_page):
    """Exception in get_by_text → falls through to body scan."""
    driver = _driver()
    mock_page.get_by_text = MagicMock(side_effect=Exception("boom"))
    mock_page.evaluate = AsyncMock(return_value="daily limit exceeded")
    result = await driver.check_rate_limit(mock_page)
    assert result == "daily limit"


async def test_check_rate_limit_body_evaluate_exception(mock_page):
    """Exception in body evaluate → returns None."""
    driver = _driver()
    loc = _make_loc(count=0)
    mock_page.get_by_text = MagicMock(return_value=loc)
    mock_page.evaluate = AsyncMock(side_effect=Exception("no evaluate"))
    result = await driver.check_rate_limit(mock_page)
    assert result is None


# ══════════════════════════════════════════════════════════════════════════════
# configure_mode
# ══════════════════════════════════════════════════════════════════════════════

async def test_configure_mode_deep_attach_button_found(mock_page):
    """DEEP mode: Attach button found, deep research option clicked."""
    driver = _driver()
    attach_loc = _make_loc(count=1, visible=True)
    dr_loc = _make_loc(count=1, visible=True)

    def _locator(sel):
        return attach_loc

    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.get_by_text = MagicMock(return_value=dr_loc)
    mock_page.wait_for_timeout = AsyncMock()

    result = await driver.configure_mode(mock_page, "DEEP")
    assert result == "Deep Research"


async def test_configure_mode_deep_attach_zero_add_button_found(mock_page):
    """DEEP mode: Attach button count=0, falls through to Add button."""
    driver = _driver()
    no_loc = _make_loc(count=0)
    add_loc = _make_loc(count=1, visible=True)
    dr_loc = _make_loc(count=1, visible=True)

    call_idx = [0]

    def _locator(sel):
        call_idx[0] += 1
        # First call: Attach → count=0; second call: Add → count=1
        if call_idx[0] == 1:
            return no_loc
        return add_loc

    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.get_by_text = MagicMock(return_value=dr_loc)
    mock_page.wait_for_timeout = AsyncMock()

    result = await driver.configure_mode(mock_page, "DEEP")
    assert result == "Deep Research"


async def test_configure_mode_deep_no_button(mock_page):
    """DEEP mode: No attach/add button → returns failure string."""
    driver = _driver()
    no_loc = _make_loc(count=0)
    mock_page.locator = MagicMock(return_value=no_loc)
    mock_page.get_by_text = MagicMock(return_value=no_loc)
    mock_page.wait_for_timeout = AsyncMock()

    result = await driver.configure_mode(mock_page, "DEEP")
    assert "Default" in result


async def test_configure_mode_deep_exception(mock_page):
    """DEEP mode: Exception during button interaction → returns failure string."""
    driver = _driver()
    mock_page.locator = MagicMock(side_effect=Exception("boom"))
    mock_page.wait_for_timeout = AsyncMock()

    result = await driver.configure_mode(mock_page, "DEEP")
    assert "Default" in result


async def test_configure_mode_deep_no_dr_option(mock_page):
    """DEEP mode: Plus button found but Deep Research option absent → returns fallback."""
    driver = _driver()
    plus_loc = _make_loc(count=1, visible=True)
    no_dr_loc = _make_loc(count=0)

    mock_page.locator = MagicMock(return_value=plus_loc)
    mock_page.get_by_text = MagicMock(return_value=no_dr_loc)
    mock_page.wait_for_timeout = AsyncMock()

    result = await driver.configure_mode(mock_page, "DEEP")
    assert "Default" in result


async def test_configure_mode_regular_model_found_o3(mock_page):
    """REGULAR mode: model selector found, o3 selected."""
    driver = _driver()
    model_loc = _make_loc(count=1, visible=True)
    o3_loc = _make_loc(count=1, visible=True)

    mock_page.locator = MagicMock(return_value=model_loc)
    mock_page.get_by_text = MagicMock(return_value=o3_loc)
    mock_page.wait_for_timeout = AsyncMock()

    result = await driver.configure_mode(mock_page, "REGULAR")
    assert result == "o3"


async def test_configure_mode_regular_model_found_o4mini(mock_page):
    """REGULAR mode: o3 not found, o4-mini found → returns o4-mini."""
    driver = _driver()
    model_loc = _make_loc(count=1, visible=True)

    call_idx = [0]

    def _get_by_text(text, **kw):
        call_idx[0] += 1
        if text == "o3":
            return _make_loc(count=0)
        return _make_loc(count=1, visible=True)

    mock_page.locator = MagicMock(return_value=model_loc)
    mock_page.get_by_text = MagicMock(side_effect=_get_by_text)
    mock_page.wait_for_timeout = AsyncMock()

    result = await driver.configure_mode(mock_page, "REGULAR")
    assert result == "o4-mini"


async def test_configure_mode_regular_no_model_button(mock_page):
    """REGULAR mode: no model button visible → returns 'Default'."""
    driver = _driver()
    no_loc = _make_loc(count=0)
    mock_page.locator = MagicMock(return_value=no_loc)
    mock_page.get_by_text = MagicMock(return_value=no_loc)
    mock_page.wait_for_timeout = AsyncMock()

    result = await driver.configure_mode(mock_page, "REGULAR")
    assert result == "Default"


async def test_configure_mode_regular_exception(mock_page):
    """REGULAR mode: Exception → returns 'Default'."""
    driver = _driver()
    mock_page.locator = MagicMock(side_effect=Exception("crash"))
    mock_page.wait_for_timeout = AsyncMock()

    result = await driver.configure_mode(mock_page, "REGULAR")
    assert result == "Default"


# ══════════════════════════════════════════════════════════════════════════════
# post_send
# ══════════════════════════════════════════════════════════════════════════════

async def test_post_send_deep_installs_blob_interceptor(mock_page):
    """DEEP mode: blob interceptor JS evaluated."""
    driver = _driver()
    mock_page.evaluate = AsyncMock(return_value=None)
    mock_page.wait_for_timeout = AsyncMock()
    mock_page.url = "https://chatgpt.com/c/abc123"
    await driver.post_send(mock_page, "DEEP")
    mock_page.evaluate.assert_called()


async def test_post_send_deep_captures_conversation_id(mock_page):
    """DEEP mode: URL with /c/ → conversation_id extracted."""
    driver = _driver()
    mock_page.evaluate = AsyncMock(return_value=None)
    mock_page.wait_for_timeout = AsyncMock()
    mock_page.url = "https://chatgpt.com/c/test-conv-id"
    await driver.post_send(mock_page, "DEEP")
    assert driver._conversation_id == "test-conv-id"


async def test_post_send_deep_evaluate_exception(mock_page):
    """DEEP mode: evaluate raises → no crash."""
    driver = _driver()
    mock_page.evaluate = AsyncMock(side_effect=Exception("no eval"))
    mock_page.wait_for_timeout = AsyncMock()
    mock_page.url = "https://chatgpt.com"
    await driver.post_send(mock_page, "DEEP")  # should not raise


async def test_post_send_regular_mode(mock_page):
    """REGULAR mode: no blob interceptor, still waits for URL."""
    driver = _driver()
    mock_page.evaluate = AsyncMock(return_value=None)
    mock_page.wait_for_timeout = AsyncMock()
    mock_page.url = "https://chatgpt.com"
    await driver.post_send(mock_page, "REGULAR")


# ══════════════════════════════════════════════════════════════════════════════
# completion_check
# ══════════════════════════════════════════════════════════════════════════════

async def test_completion_check_stop_button_visible(mock_page):
    """Stop button visible → returns False."""
    driver = _driver()
    stop_loc = _make_loc(count=1, visible=True)
    mock_page.locator = MagicMock(return_value=stop_loc)
    mock_page.get_by_text = MagicMock(return_value=_make_loc())
    mock_page.frames = []
    mock_page.main_frame = MagicMock()

    result = await driver.completion_check(mock_page)
    assert result is False


async def test_completion_check_deep_progress_text_visible(mock_page):
    """DEEP mode: progress text visible → returns False."""
    driver = _driver()
    driver._mode = "DEEP"
    no_stop = _make_loc(count=0)
    prog_loc = _make_loc(count=1, visible=True)

    mock_page.locator = MagicMock(return_value=no_stop)
    mock_page.get_by_text = MagicMock(return_value=prog_loc)
    mock_page.frames = []
    mock_page.main_frame = MagicMock()

    result = await driver.completion_check(mock_page)
    assert result is False


async def test_completion_check_regular_two_articles_long(mock_page):
    """REGULAR mode: 2 articles, last one >2000 chars → returns True."""
    driver = _driver()
    driver._mode = "REGULAR"
    driver._no_stop_polls = 0

    no_stop = _make_loc(count=0)
    articles_loc = MagicMock()
    articles_loc.first = articles_loc
    articles_loc.count = AsyncMock(return_value=2)
    articles_loc.evaluate = AsyncMock(return_value=2500)
    articles_loc.nth = lambda n: articles_loc

    def _locator(sel):
        if sel == "article":
            return articles_loc
        return no_stop

    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.get_by_text = MagicMock(return_value=no_stop)
    mock_page.evaluate = AsyncMock(return_value=5000)
    mock_page.frames = []
    mock_page.main_frame = MagicMock()

    result = await driver.completion_check(mock_page)
    assert result is True


async def test_completion_check_regular_large_body(mock_page):
    """REGULAR mode: body.innerText.length > 15000 → returns True."""
    driver = _driver()
    driver._mode = "REGULAR"
    driver._no_stop_polls = 0

    no_stop = _make_loc(count=0)
    articles_loc = MagicMock()
    articles_loc.first = articles_loc
    articles_loc.count = AsyncMock(return_value=0)

    def _locator(sel):
        if sel == "article":
            return articles_loc
        return no_stop

    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.get_by_text = MagicMock(return_value=no_stop)
    mock_page.evaluate = AsyncMock(return_value=16000)
    mock_page.frames = []
    mock_page.main_frame = MagicMock()

    result = await driver.completion_check(mock_page)
    assert result is True


async def test_completion_check_regular_stable_3_polls(mock_page):
    """REGULAR mode: no_stop_polls >= 3 → returns True."""
    driver = _driver()
    driver._mode = "REGULAR"
    driver._no_stop_polls = 3

    no_stop = _make_loc(count=0)
    articles_loc = MagicMock()
    articles_loc.first = articles_loc
    articles_loc.count = AsyncMock(return_value=0)

    def _locator(sel):
        if sel == "article":
            return articles_loc
        return no_stop

    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.get_by_text = MagicMock(return_value=no_stop)
    mock_page.evaluate = AsyncMock(return_value=100)
    mock_page.frames = []
    mock_page.main_frame = MagicMock()

    result = await driver.completion_check(mock_page)
    assert result is True


async def test_completion_check_deep_dr_frame_large(mock_page):
    """DEEP mode: DR iframe has >20000 chars → returns True."""
    driver = _driver()
    driver._mode = "DEEP"
    driver._no_stop_polls = 0

    no_stop = _make_loc(count=0)
    mock_page.locator = MagicMock(return_value=no_stop)
    mock_page.get_by_text = MagicMock(return_value=no_stop)

    dr_frame = MagicMock()
    dr_frame.url = "https://oaiusercontent.com/dr"
    dr_frame.evaluate = AsyncMock(return_value=25000)
    main_frame = MagicMock()
    main_frame.url = "https://chatgpt.com"
    mock_page.main_frame = main_frame
    mock_page.frames = [main_frame, dr_frame]

    result = await driver.completion_check(mock_page)
    assert result is True


async def test_completion_check_deep_60_polls_timeout(mock_page):
    """DEEP mode: 60 polls without DR iframe → returns True."""
    driver = _driver()
    driver._mode = "DEEP"
    driver._no_stop_polls = 60

    no_stop = _make_loc(count=0)
    mock_page.locator = MagicMock(return_value=no_stop)
    mock_page.get_by_text = MagicMock(return_value=no_stop)

    main_frame = MagicMock()
    main_frame.url = "about:blank"
    mock_page.main_frame = main_frame
    mock_page.frames = [main_frame]

    result = await driver.completion_check(mock_page)
    assert result is True


async def test_completion_check_exceptions_in_selectors(mock_page):
    """Exceptions in selector checks are silently caught; stable_3_polls triggers."""
    driver = _driver()
    driver._mode = "REGULAR"
    driver._no_stop_polls = 3

    mock_page.locator = MagicMock(side_effect=Exception("oops"))
    mock_page.get_by_text = MagicMock(side_effect=Exception("oops"))
    mock_page.evaluate = AsyncMock(side_effect=Exception("nope"))
    mock_page.frames = []
    mock_page.main_frame = MagicMock()

    result = await driver.completion_check(mock_page)
    assert result is True


async def test_completion_check_deep_exception_in_progress(mock_page):
    """DEEP mode: exception checking progress text → still returns False (has_stop=False, polls reset)."""
    driver = _driver()
    driver._mode = "DEEP"
    driver._no_stop_polls = 0

    no_stop = _make_loc(count=0)
    mock_page.locator = MagicMock(return_value=no_stop)
    mock_page.get_by_text = MagicMock(side_effect=Exception("boom"))

    dr_frame = MagicMock()
    dr_frame.url = "https://oaiusercontent.com/dr"
    dr_frame.evaluate = AsyncMock(return_value=0)
    main_frame = MagicMock()
    main_frame.url = "https://chatgpt.com"
    mock_page.main_frame = main_frame
    mock_page.frames = [main_frame, dr_frame]

    result = await driver.completion_check(mock_page)
    assert result is False


# ══════════════════════════════════════════════════════════════════════════════
# extract_response  (ChatGPTExtractorMixin)
# ══════════════════════════════════════════════════════════════════════════════

async def test_extract_response_regular_article_selector(mock_page):
    """REGULAR mode: article selector returns long text."""
    driver = _driver()
    driver._mode = "REGULAR"

    long_text = "A" * 600
    mock_page.evaluate = AsyncMock(return_value=long_text)
    mock_page.frames = []
    mock_page.main_frame = MagicMock()

    result = await driver.extract_response(mock_page)
    assert len(result) > 0


async def test_extract_response_deep_quota_detected(mock_page):
    """DEEP mode: quota phrase in body → returns RATE LIMITED."""
    driver = _driver()
    driver._mode = "DEEP"

    mock_page.evaluate = AsyncMock(return_value="You've reached the current usage cap for today.")
    mock_page.frames = []
    mock_page.main_frame = MagicMock()

    result = await driver.extract_response(mock_page)
    assert "[RATE LIMITED]" in result


async def test_extract_response_deep_quota_exception(mock_page):
    """DEEP mode: evaluate raises on quota scan → falls through to DR panel."""
    driver = _driver()
    driver._mode = "DEEP"

    call_count = [0]

    async def _evaluate(script, *args):
        call_count[0] += 1
        if call_count[0] == 1:
            raise Exception("eval error")
        # DR panel calls
        return ""

    mock_page.evaluate = MagicMock(side_effect=_evaluate)
    mock_page.frames = []
    mock_page.main_frame = MagicMock()
    mock_page.frame_locator = MagicMock(return_value=MagicMock())

    result = await driver.extract_response(mock_page)
    # Should not raise, returns empty or fallback
    assert isinstance(result, str)


async def test_extract_response_deep_blob_fallback(mock_page):
    """DEEP mode: DR panel empty, blob interceptor has text."""
    driver = _driver()
    driver._mode = "DEEP"

    blob_text = "B" * 1100

    call_count = [0]

    async def _evaluate(script, *args):
        call_count[0] += 1
        if call_count[0] == 1:
            return ""   # quota scan → empty
        if "__capturedBlobs" in script:
            return blob_text
        return ""

    mock_page.evaluate = MagicMock(side_effect=_evaluate)
    mock_page.frames = []
    mock_page.main_frame = MagicMock()
    mock_page.frame_locator = MagicMock(return_value=MagicMock())

    result = await driver.extract_response(mock_page)
    assert result == blob_text


async def test_extract_response_body_innertext_fallback(mock_page):
    """Falls through to body.innerText last resort."""
    driver = _driver()
    driver._mode = "REGULAR"

    body_text = "ChatGPT said:\nHere is the answer with sufficient content " + "X" * 300

    mock_page.evaluate = AsyncMock(return_value=body_text)
    mock_page.frames = []
    mock_page.main_frame = MagicMock()

    result = await driver.extract_response(mock_page)
    assert len(result) > 0


async def test_extract_response_deep_dr_frame_text(mock_page):
    """DEEP mode: DR frame has long text → extracted via frame.evaluate."""
    driver = _driver()
    driver._mode = "DEEP"
    driver.prompt_sigs = []

    long_frame_text = "DR content " * 200  # >1000 chars

    async def _evaluate(script, *args):
        if "innerText" in script and "body" in script:
            return ""   # quota scan empty
        return ""

    mock_page.evaluate = MagicMock(side_effect=_evaluate)

    dr_frame = MagicMock()
    dr_frame.url = "https://oaiusercontent.com/report"
    dr_frame.evaluate = AsyncMock(return_value=long_frame_text)
    main_frame = MagicMock()
    main_frame.url = "https://chatgpt.com"
    main_frame.parent_frame = None
    mock_page.main_frame = main_frame
    mock_page.frames = [main_frame, dr_frame]

    result = await driver.extract_response(mock_page)
    assert result == long_frame_text


async def test_completion_check_deep_frame_skip_blank_url(mock_page):
    """DEEP mode: frame with blank url is skipped (line 184 continue)."""
    driver = _driver()
    driver._mode = "DEEP"
    driver._no_stop_polls = 0

    no_stop = _make_loc(count=0)
    mock_page.locator = MagicMock(return_value=no_stop)
    mock_page.get_by_text = MagicMock(return_value=no_stop)

    # Frame with blank URL should be skipped via `continue`
    blank_frame = MagicMock()
    blank_frame.url = ""
    main_frame = MagicMock()
    main_frame.url = "https://chatgpt.com"
    mock_page.main_frame = main_frame
    mock_page.frames = [main_frame, blank_frame]

    result = await driver.completion_check(mock_page)
    # dr_frame_len stays 0, no_stop_polls < 60 → returns False
    assert result is False


async def test_completion_check_deep_dr_frame_evaluate_exception(mock_page):
    """DEEP mode: DR frame evaluate raises → exception caught, dr_frame_len=0."""
    driver = _driver()
    driver._mode = "DEEP"
    driver._no_stop_polls = 0

    no_stop = _make_loc(count=0)
    mock_page.locator = MagicMock(return_value=no_stop)
    mock_page.get_by_text = MagicMock(return_value=no_stop)

    dr_frame = MagicMock()
    dr_frame.url = "https://oaiusercontent.com/dr"
    dr_frame.evaluate = AsyncMock(side_effect=Exception("frame eval error"))
    main_frame = MagicMock()
    main_frame.url = "https://chatgpt.com"
    mock_page.main_frame = main_frame
    mock_page.frames = [main_frame, dr_frame]

    result = await driver.completion_check(mock_page)
    # Exception caught → dr_frame_len=0 → returns False
    assert result is False
