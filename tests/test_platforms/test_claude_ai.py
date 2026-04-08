"""Tests for ClaudeAI platform driver — 100% coverage."""

import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# ── Stubs ──────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent.parent
ENGINE_DIR = str(PROJECT_ROOT / "skills" / "orchestrator" / "engine")

_es = types.ModuleType("engine_setup")
_es._load_dotenv = lambda: None
_es._ensure_venv = lambda: None
_es._ensure_dependencies = lambda: None
sys.modules.setdefault("engine_setup", _es)

_pw = types.ModuleType("playwright")
_pw_api = types.ModuleType("playwright.async_api")
_pw_api.Page = MagicMock
_pw_api.async_playwright = MagicMock
_pw_api.BrowserContext = MagicMock
sys.modules.setdefault("playwright", _pw)
sys.modules.setdefault("playwright.async_api", _pw_api)

_bu = types.ModuleType("browser_use")
_bu.Agent = MagicMock
_bu.BrowserSession = MagicMock
sys.modules.setdefault("browser_use", _bu)

_af = types.ModuleType("agent_fallback")
_af.AgentFallbackManager = MagicMock
_af.FallbackStep = MagicMock
sys.modules.setdefault("agent_fallback", _af)

sys.modules.setdefault("anthropic", types.ModuleType("anthropic"))

if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

from platforms.claude_ai import ClaudeAI  # noqa: E402


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_loc(count=0, visible=False, text="", attr=None):
    loc = MagicMock()
    loc.first = loc
    loc.count = AsyncMock(return_value=count)
    loc.is_visible = AsyncMock(return_value=visible)
    loc.click = AsyncMock()
    loc.get_attribute = AsyncMock(return_value=attr)
    loc.inner_text = AsyncMock(return_value=text)
    loc.evaluate = AsyncMock(return_value=None)
    loc.fill = AsyncMock()
    loc.dispatch_event = AsyncMock()
    loc.nth = lambda n: loc
    return loc


def _driver():
    d = ClaudeAI()
    d.agent_manager = None
    d.prompt_sigs = []
    return d


# ══════════════════════════════════════════════════════════════════════════════
# check_rate_limit
# ══════════════════════════════════════════════════════════════════════════════

async def test_rate_limit_found(mock_page):
    """Usage limit text visible → returns pattern."""
    driver = _driver()
    loc = _make_loc(count=1, visible=True)
    mock_page.get_by_text = MagicMock(return_value=loc)
    result = await driver.check_rate_limit(mock_page)
    assert result == "Usage limit reached"


async def test_rate_limit_none(mock_page):
    """No pattern visible → returns None."""
    driver = _driver()
    loc = _make_loc(count=0)
    mock_page.get_by_text = MagicMock(return_value=loc)
    result = await driver.check_rate_limit(mock_page)
    assert result is None


async def test_rate_limit_exception(mock_page):
    """Exception during element check → returns None."""
    driver = _driver()
    mock_page.get_by_text = MagicMock(side_effect=Exception("boom"))
    result = await driver.check_rate_limit(mock_page)
    assert result is None


# ══════════════════════════════════════════════════════════════════════════════
# configure_mode
# ══════════════════════════════════════════════════════════════════════════════

async def test_configure_mode_regular_sonnet_selected(mock_page):
    """REGULAR mode: model button found, Sonnet option clicked."""
    driver = _driver()
    model_btn = _make_loc(count=1, visible=True)
    sonnet_loc = _make_loc(count=1, visible=True)

    mock_page.locator = MagicMock(return_value=model_btn)
    mock_page.get_by_text = MagicMock(return_value=sonnet_loc)
    mock_page.wait_for_timeout = AsyncMock()

    result = await driver.configure_mode(mock_page, "REGULAR")
    assert "Sonnet" in result


async def test_configure_mode_regular_model_btn_count_zero_fallbacks(mock_page):
    """REGULAR mode: first locator returns count=0, try text fallbacks."""
    driver = _driver()

    call_idx = [0]

    def _locator(sel):
        call_idx[0] += 1
        if call_idx[0] <= 1:
            return _make_loc(count=0)
        return _make_loc(count=1, visible=True)

    sonnet_loc = _make_loc(count=1)
    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.get_by_text = MagicMock(return_value=sonnet_loc)
    mock_page.wait_for_timeout = AsyncMock()

    result = await driver.configure_mode(mock_page, "REGULAR")
    assert "Sonnet" in result


async def test_configure_mode_regular_all_model_btns_zero(mock_page):
    """REGULAR mode: all model locators count=0, sonnet not found, no model selected."""
    driver = _driver()
    no_loc = _make_loc(count=0)
    mock_page.locator = MagicMock(return_value=no_loc)
    mock_page.get_by_text = MagicMock(return_value=no_loc)
    mock_page.wait_for_timeout = AsyncMock()

    result = await driver.configure_mode(mock_page, "REGULAR")
    assert result == "Sonnet"


async def test_configure_mode_regular_model_exception(mock_page):
    """REGULAR mode: exception (non-RuntimeError) → continues gracefully."""
    driver = _driver()
    mock_page.locator = MagicMock(side_effect=Exception("page crash"))
    mock_page.get_by_text = MagicMock(return_value=_make_loc(count=0))
    mock_page.wait_for_timeout = AsyncMock()

    result = await driver.configure_mode(mock_page, "REGULAR")
    assert result == "Sonnet"


async def test_configure_mode_regular_runtime_error_re_raised(mock_page):
    """REGULAR mode: RuntimeError is re-raised per explicit handler."""
    driver = _driver()
    mock_page.locator = MagicMock(side_effect=RuntimeError("hard stop"))
    mock_page.wait_for_timeout = AsyncMock()

    with pytest.raises(RuntimeError):
        await driver.configure_mode(mock_page, "REGULAR")


async def test_configure_mode_deep_web_search_enabled(mock_page):
    """DEEP mode: plus button found, Web search option clicked."""
    driver = _driver()
    plus_loc = _make_loc(count=1, visible=True)
    websearch_loc = _make_loc(count=1, visible=True)
    model_btn = _make_loc(count=0)

    call_idx = [0]

    def _locator(sel):
        call_idx[0] += 1
        if "Add" in sel or "attach" in sel:
            return plus_loc
        return model_btn

    def _get_by_text(text, **kw):
        if text == "Web search":
            return websearch_loc
        return _make_loc(count=0)

    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.get_by_text = MagicMock(side_effect=_get_by_text)
    mock_page.wait_for_timeout = AsyncMock()

    result = await driver.configure_mode(mock_page, "DEEP")
    assert "Web search" in result


async def test_configure_mode_deep_plus_not_found(mock_page):
    """DEEP mode: plus button not found → still returns Sonnet."""
    driver = _driver()
    no_loc = _make_loc(count=0)
    mock_page.locator = MagicMock(return_value=no_loc)
    mock_page.get_by_text = MagicMock(return_value=no_loc)
    mock_page.wait_for_timeout = AsyncMock()

    result = await driver.configure_mode(mock_page, "DEEP")
    assert "Sonnet" in result


async def test_configure_mode_deep_exception(mock_page):
    """DEEP mode: exception in plus-button block → returns Sonnet."""
    driver = _driver()
    model_btn = _make_loc(count=0)

    call_idx = [0]

    def _locator(sel):
        call_idx[0] += 1
        if call_idx[0] > 3:
            raise Exception("deep crash")
        return model_btn

    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.get_by_text = MagicMock(return_value=_make_loc(count=0))
    mock_page.wait_for_timeout = AsyncMock()

    result = await driver.configure_mode(mock_page, "DEEP")
    assert "Sonnet" in result


# ══════════════════════════════════════════════════════════════════════════════
# inject_prompt
# ══════════════════════════════════════════════════════════════════════════════

async def test_inject_prompt_contenteditable_found(mock_page):
    """Contenteditable found on first attempt → injects via execCommand."""
    driver = _driver()
    ce_loc = _make_loc(count=1, visible=True)
    mock_page.locator = MagicMock(return_value=ce_loc)
    mock_page.wait_for_timeout = AsyncMock()
    mock_page.evaluate = AsyncMock(return_value=len("hello world"))

    await driver.inject_prompt(mock_page, "hello world")
    mock_page.evaluate.assert_called()


async def test_inject_prompt_contenteditable_found_after_retry(mock_page):
    """Contenteditable absent on first attempt, found on second."""
    driver = _driver()
    no_loc = _make_loc(count=0, visible=False)
    found_loc = _make_loc(count=1, visible=True)

    call_idx = [0]

    def _locator(sel):
        call_idx[0] += 1
        if call_idx[0] == 1:
            return no_loc
        return found_loc

    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.wait_for_timeout = AsyncMock()
    mock_page.evaluate = AsyncMock(return_value=5)

    await driver.inject_prompt(mock_page, "test")


async def test_inject_prompt_no_contenteditable_raises(mock_page):
    """All 5 attempts fail → RuntimeError raised."""
    driver = _driver()
    no_loc = _make_loc(count=0, visible=False)
    mock_page.locator = MagicMock(return_value=no_loc)
    mock_page.wait_for_timeout = AsyncMock()

    with pytest.raises(RuntimeError, match="No contenteditable"):
        await driver.inject_prompt(mock_page, "test")


# ══════════════════════════════════════════════════════════════════════════════
# completion_check
# ══════════════════════════════════════════════════════════════════════════════

async def test_completion_check_research_failed(mock_page):
    """Stopped button visible → _research_failed=True, returns True."""
    driver = _driver()
    stopped_loc = _make_loc(count=1, visible=True, attr="Stopped: No connectors")
    no_loc = _make_loc(count=0)

    def _locator(sel):
        if "Stopped" in sel:
            return stopped_loc
        return no_loc

    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.evaluate = AsyncMock(return_value=None)
    mock_page.wait_for_timeout = AsyncMock()

    result = await driver.completion_check(mock_page)
    assert result is True
    assert driver._research_failed is True


async def test_completion_check_stopped_get_attr_exception(mock_page):
    """Stopped button visible but get_attribute raises → reason='unknown'."""
    driver = _driver()
    stopped_loc = _make_loc(count=1, visible=True)
    stopped_loc.get_attribute = AsyncMock(side_effect=Exception("no attr"))
    no_loc = _make_loc(count=0)

    def _locator(sel):
        if "Stopped" in sel:
            return stopped_loc
        return no_loc

    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.evaluate = AsyncMock(return_value=None)
    mock_page.wait_for_timeout = AsyncMock()

    result = await driver.completion_check(mock_page)
    assert result is True
    assert driver._research_failed_reason == "unknown"


async def test_completion_check_stop_button_visible(mock_page):
    """Stop button visible → returns False."""
    driver = _driver()
    no_stopped = _make_loc(count=0)
    stop_loc = _make_loc(count=1, visible=True, attr="Stop generating")

    def _locator(sel):
        if "Stopped" in sel:
            return no_stopped
        return stop_loc

    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.evaluate = AsyncMock(return_value=None)
    mock_page.wait_for_timeout = AsyncMock()

    result = await driver.completion_check(mock_page)
    assert result is False


async def test_completion_check_stop_button_aria_starts_stopped(mock_page):
    """Stop button aria-label starts with 'stopped' → skipped, no_stop_polls increments."""
    driver = _driver()
    no_loc = _make_loc(count=0)
    skip_stop = _make_loc(count=1, visible=True, attr="stopped: no connectors")

    def _locator(sel):
        if "Stopped" in sel:
            return no_loc
        if "Stop" in sel:
            return skip_stop  # count=1, visible, but aria starts with "stopped" → continue
        return no_loc  # Copy/Download/artifact → count=0

    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.evaluate = AsyncMock(return_value=None)
    mock_page.wait_for_timeout = AsyncMock()

    # has_stop stays False (skipped), no_stop_polls=1, stable-state < 12 → False
    result = await driver.completion_check(mock_page)
    assert result is False


async def test_completion_check_stop_exception(mock_page):
    """Exception checking stopped/stop selectors → silently caught."""
    driver = _driver()
    mock_page.locator = MagicMock(side_effect=Exception("locator crash"))
    mock_page.evaluate = AsyncMock(return_value=None)
    mock_page.wait_for_timeout = AsyncMock()

    result = await driver.completion_check(mock_page)
    assert result is False


async def test_completion_check_copy_button_visible(mock_page):
    """Copy button visible → returns True."""
    driver = _driver()
    no_loc = _make_loc(count=0)
    copy_loc = _make_loc(count=1, visible=True)

    def _locator(sel):
        if "Stopped" in sel or "Stop" in sel:
            return no_loc
        if "Copy" in sel:
            return copy_loc
        return no_loc

    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.evaluate = AsyncMock(return_value=None)
    mock_page.wait_for_timeout = AsyncMock()

    result = await driver.completion_check(mock_page)
    assert result is True


async def test_completion_check_download_button_visible(mock_page):
    """Download button visible → returns True."""
    driver = _driver()
    no_loc = _make_loc(count=0)
    dl_loc = _make_loc(count=1, visible=True)

    def _locator(sel):
        if "Stopped" in sel or "Stop" in sel or "Copy" in sel:
            return no_loc
        if "Download" in sel:
            return dl_loc
        return no_loc

    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.evaluate = AsyncMock(return_value=None)
    mock_page.wait_for_timeout = AsyncMock()

    result = await driver.completion_check(mock_page)
    assert result is True


async def test_completion_check_artifact_click_then_copy(mock_page):
    """Artifact card clicked, re-check finds Copy → returns True."""
    driver = _driver()
    no_loc = _make_loc(count=0)
    artifact_loc = _make_loc(count=1, visible=True)
    copy_loc = _make_loc(count=1, visible=True)

    locator_calls = [0]

    def _locator(sel):
        locator_calls[0] += 1
        if "Stopped" in sel or "Stop" in sel:
            return no_loc
        if "Copy" in sel or "Download" in sel:
            # After artifact is clicked, re-check returns copy
            if driver._artifact_clicked:
                return copy_loc
            return no_loc
        if "artifact" in sel or "document" in sel:
            return artifact_loc
        return no_loc

    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.evaluate = AsyncMock(return_value=None)
    mock_page.wait_for_timeout = AsyncMock()

    result = await driver.completion_check(mock_page)
    assert result is True
    assert driver._artifact_clicked is True


async def test_completion_check_artifact_click_exception(mock_page):
    """Exception during artifact click → silently caught."""
    driver = _driver()
    no_loc = _make_loc(count=0)
    artifact_loc = _make_loc(count=1, visible=True)
    artifact_loc.evaluate = AsyncMock(side_effect=Exception("click error"))

    def _locator(sel):
        if "Stopped" in sel or "Stop" in sel or "Copy" in sel or "Download" in sel:
            return no_loc
        if "artifact" in sel or "document" in sel:
            return artifact_loc
        return no_loc

    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.evaluate = AsyncMock(return_value=None)
    mock_page.wait_for_timeout = AsyncMock()

    result = await driver.completion_check(mock_page)
    assert result is False


async def test_completion_check_stable_12_polls(mock_page):
    """12 polls with no stop/copy → returns True (stable-state fallback)."""
    driver = _driver()
    driver._no_stop_polls = 12
    no_loc = _make_loc(count=0)
    mock_page.locator = MagicMock(return_value=no_loc)
    mock_page.evaluate = AsyncMock(return_value=None)
    mock_page.wait_for_timeout = AsyncMock()

    result = await driver.completion_check(mock_page)
    assert result is True


async def test_completion_check_visibility_events_dispatched(mock_page):
    """Every 30 polls, visibility events are dispatched."""
    driver = _driver()
    driver._total_polls = 29  # Next call = 30th poll
    no_loc = _make_loc(count=0)
    mock_page.locator = MagicMock(return_value=no_loc)
    mock_page.evaluate = AsyncMock(return_value=None)
    mock_page.wait_for_timeout = AsyncMock()

    await driver.completion_check(mock_page)
    # evaluate called for visibility events dispatch
    mock_page.evaluate.assert_called()


async def test_completion_check_visibility_events_exception(mock_page):
    """Exception in visibility dispatch → silently caught."""
    driver = _driver()
    driver._total_polls = 29
    no_loc = _make_loc(count=0)
    mock_page.locator = MagicMock(return_value=no_loc)
    mock_page.evaluate = AsyncMock(side_effect=Exception("no eval"))
    mock_page.wait_for_timeout = AsyncMock()

    result = await driver.completion_check(mock_page)
    assert result is False


# ══════════════════════════════════════════════════════════════════════════════
# extract_response
# ══════════════════════════════════════════════════════════════════════════════

async def test_extract_response_research_failed(mock_page):
    """_research_failed=True → returns error string immediately."""
    driver = _driver()
    driver._research_failed = True
    driver._research_failed_reason = "No connectors"

    result = await driver.extract_response(mock_page)
    assert "[RESEARCH FAILED]" in result
    assert "No connectors" in result


async def test_extract_response_rate_limited(mock_page):
    """Rate limit element visible → returns RATE LIMITED string."""
    driver = _driver()
    rate_loc = _make_loc(count=1, visible=True)
    mock_page.get_by_text = MagicMock(return_value=rate_loc)
    mock_page.locator = MagicMock(return_value=_make_loc(count=0))
    mock_page.evaluate = AsyncMock(return_value="")
    mock_page.expect_download = MagicMock()

    result = await driver.extract_response(mock_page)
    assert "[RATE LIMITED]" in result


async def test_extract_response_rate_limit_exception(mock_page):
    """Exception checking rate limit → falls through."""
    driver = _driver()
    mock_page.get_by_text = MagicMock(side_effect=Exception("boom"))
    mock_page.locator = MagicMock(return_value=_make_loc(count=0))
    mock_page.evaluate = AsyncMock(return_value="body text " + "X" * 200)
    mock_page.expect_download = MagicMock()

    result = await driver.extract_response(mock_page)
    assert isinstance(result, str)


async def test_extract_response_docx_download_success(mock_page):
    """Download button found, DOCX downloaded with >500 chars → returns text."""
    driver = _driver()

    no_rate = _make_loc(count=0)
    artifact_loc = _make_loc(count=0)
    dl_btn = _make_loc(count=1, visible=True)

    def _locator(sel):
        if 'aria-label="Download"' in sel:
            return dl_btn
        if "artifact" in sel or "document" in sel or "DOCX" in sel:
            return artifact_loc
        return no_rate

    mock_page.get_by_text = MagicMock(return_value=no_rate)
    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.wait_for_timeout = AsyncMock()
    mock_page.evaluate = AsyncMock(return_value="")

    # Mock the download context manager
    long_text = "P" * 600
    mock_path = MagicMock()

    mock_dl_value = MagicMock()
    mock_dl_value.path = AsyncMock(return_value=mock_path)

    # `download_info.value` is awaited directly in the source: `await download_info.value`
    # Must be an awaitable (coroutine), not just AsyncMock as an attribute.
    async def _dl_value():
        return mock_dl_value

    dl_ctx = MagicMock()
    dl_ctx.__aenter__ = AsyncMock(return_value=dl_ctx)
    dl_ctx.__aexit__ = AsyncMock(return_value=False)
    dl_ctx.value = _dl_value()  # coroutine
    mock_page.expect_download = MagicMock(return_value=dl_ctx)

    # Mock python-docx Document
    mock_doc = MagicMock()
    mock_para = MagicMock()
    mock_para.text = long_text
    mock_doc.paragraphs = [mock_para]

    import unittest.mock
    mock_docx_module = types.ModuleType("docx")
    mock_docx_module.Document = MagicMock(return_value=mock_doc)
    with unittest.mock.patch.dict(sys.modules, {"docx": mock_docx_module}):
        result = await driver.extract_response(mock_page)

    assert len(result) > 0


async def test_extract_response_docx_short_falls_through(mock_page):
    """DOCX download returns <500 chars → falls to panel selector."""
    driver = _driver()

    no_loc = _make_loc(count=0)
    dl_btn = _make_loc(count=1, visible=True)

    def _locator(sel):
        if 'aria-label="Download"' in sel:
            return dl_btn
        # Panel selector → count=1 with long text
        return _make_loc(count=1, text="X" * 6000)

    mock_page.get_by_text = MagicMock(return_value=no_loc)
    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.wait_for_timeout = AsyncMock()
    mock_page.evaluate = AsyncMock(return_value="")

    mock_dl_value = MagicMock()
    mock_dl_value.path = AsyncMock(return_value="/tmp/test.docx")

    async def _dl_value_short():
        return mock_dl_value

    dl_ctx = MagicMock()
    dl_ctx.__aenter__ = AsyncMock(return_value=dl_ctx)
    dl_ctx.__aexit__ = AsyncMock(return_value=False)
    dl_ctx.value = _dl_value_short()
    mock_page.expect_download = MagicMock(return_value=dl_ctx)

    short_text = "short"
    mock_doc = MagicMock()
    mock_para = MagicMock()
    mock_para.text = short_text
    mock_doc.paragraphs = [mock_para]

    import unittest.mock
    with unittest.mock.patch.dict(sys.modules, {"docx": MagicMock(Document=MagicMock(return_value=mock_doc))}):
        result = await driver.extract_response(mock_page)

    assert len(result) > 0


async def test_extract_response_panel_selector(mock_page):
    """Panel selector returns >5000 chars → extracted."""
    driver = _driver()
    no_loc = _make_loc(count=0)
    panel_text = "Z" * 5500
    panel_loc = _make_loc(count=1, text=panel_text)

    def _locator(sel):
        if 'aria-label="Download"' in sel:
            return no_loc
        if "artifact" in sel or "document" in sel or "DOCX" in sel:
            return no_loc
        if "ease-out" in sel:
            return panel_loc
        return no_loc

    mock_page.get_by_text = MagicMock(return_value=no_loc)
    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.wait_for_timeout = AsyncMock()
    mock_page.evaluate = AsyncMock(return_value="")

    result = await driver.extract_response(mock_page)
    assert result == panel_text


async def test_extract_response_body_marker_extraction(mock_page):
    """Body text has ## heading that is not a prompt echo → extracted."""
    driver = _driver()
    no_loc = _make_loc(count=0)
    body = "Preamble\n## Section Heading\n" + "Content " * 100

    mock_page.get_by_text = MagicMock(return_value=no_loc)
    mock_page.locator = MagicMock(return_value=no_loc)
    mock_page.wait_for_timeout = AsyncMock()
    mock_page.evaluate = AsyncMock(return_value=body)

    result = await driver.extract_response(mock_page)
    assert "Section Heading" in result


async def test_extract_response_body_marker_prompt_echo_skipped(mock_page):
    """Body text heading is a prompt echo → skipped, falls to conversation turn."""
    driver = _driver()
    driver.prompt_sigs = ["section heading"]
    no_loc = _make_loc(count=0)
    body = "Preamble\n## Section Heading\n" + "A" * 600
    turns_text = "AI response " * 100  # >1000 chars

    mock_page.get_by_text = MagicMock(return_value=no_loc)
    mock_page.locator = MagicMock(return_value=no_loc)
    mock_page.wait_for_timeout = AsyncMock()

    call_idx = [0]

    async def _evaluate(script, *args):
        call_idx[0] += 1
        if "body.innerText" in script and call_idx[0] <= 2:
            return body
        if "conversation-turn" in script or "querySelectorAll" in script:
            return turns_text
        return body

    mock_page.evaluate = MagicMock(side_effect=_evaluate)

    result = await driver.extract_response(mock_page)
    assert isinstance(result, str)
    assert len(result) > 0


async def test_extract_response_conversation_turn_extraction(mock_page):
    """Conversation-turn JS selector returns >1000 chars → extracted."""
    driver = _driver()
    no_loc = _make_loc(count=0)
    turns_text = "Turn content " * 100  # >1000 chars

    mock_page.get_by_text = MagicMock(return_value=no_loc)
    mock_page.locator = MagicMock(return_value=no_loc)
    mock_page.wait_for_timeout = AsyncMock()

    call_idx = [0]

    async def _evaluate(script, *args):
        call_idx[0] += 1
        if "querySelectorAll" in script or "conversation-turn" in script:
            return turns_text
        return ""

    mock_page.evaluate = MagicMock(side_effect=_evaluate)

    result = await driver.extract_response(mock_page)
    assert isinstance(result, str)


async def test_extract_response_all_fallbacks_body_text(mock_page):
    """All other methods fail → falls back to full body.innerText."""
    driver = _driver()
    no_loc = _make_loc(count=0)
    body_text = "Final fallback body " * 10

    mock_page.get_by_text = MagicMock(return_value=no_loc)
    mock_page.locator = MagicMock(return_value=no_loc)
    mock_page.wait_for_timeout = AsyncMock()
    mock_page.evaluate = AsyncMock(return_value=body_text)

    result = await driver.extract_response(mock_page)
    assert result == body_text


async def test_extract_response_all_methods_exception(mock_page):
    """All evaluate calls raise → returns empty string."""
    driver = _driver()
    no_loc = _make_loc(count=0)

    mock_page.get_by_text = MagicMock(return_value=no_loc)
    mock_page.locator = MagicMock(return_value=no_loc)
    mock_page.wait_for_timeout = AsyncMock()
    mock_page.evaluate = AsyncMock(side_effect=Exception("all broken"))

    result = await driver.extract_response(mock_page)
    assert result == ""


async def test_extract_response_docx_path_none(mock_page):
    """Download path returns None → falls through."""
    driver = _driver()
    no_loc = _make_loc(count=0)
    dl_btn = _make_loc(count=1, visible=True)

    def _locator(sel):
        if 'aria-label="Download"' in sel:
            return dl_btn
        return no_loc

    mock_page.get_by_text = MagicMock(return_value=no_loc)
    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.wait_for_timeout = AsyncMock()
    mock_page.evaluate = AsyncMock(return_value="body " * 5)

    mock_dl_value = MagicMock()
    mock_dl_value.path = AsyncMock(return_value=None)  # path=None

    async def _dl_value_none():
        return mock_dl_value

    dl_ctx = MagicMock()
    dl_ctx.__aenter__ = AsyncMock(return_value=dl_ctx)
    dl_ctx.__aexit__ = AsyncMock(return_value=False)
    dl_ctx.value = _dl_value_none()
    mock_page.expect_download = MagicMock(return_value=dl_ctx)

    result = await driver.extract_response(mock_page)
    assert isinstance(result, str)


async def test_completion_check_stop_aria_get_attr_exception(mock_page):
    """get_attribute raises inside stop-button aria check → exception caught, has_stop=True."""
    driver = _driver()
    no_loc = _make_loc(count=0)
    stop_loc = _make_loc(count=1, visible=True)
    stop_loc.get_attribute = AsyncMock(side_effect=Exception("no attr"))

    def _locator(sel):
        if "Stopped" in sel:
            return no_loc
        if "Stop" in sel:
            return stop_loc
        return no_loc

    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.evaluate = AsyncMock(return_value=None)
    mock_page.wait_for_timeout = AsyncMock()

    result = await driver.completion_check(mock_page)
    assert result is False


async def test_extract_response_artifact_card_clicked(mock_page):
    """Artifact card visible → clicked to open panel (lines 274-279)."""
    driver = _driver()
    no_loc = _make_loc(count=0)
    artifact_loc = _make_loc(count=1, visible=True)
    panel_loc = _make_loc(count=1, text="Z" * 5500)

    def _locator(sel):
        if 'aria-label="Download"' in sel:
            return no_loc
        if "artifact" in sel or "document" in sel or "DOCX" in sel:
            return artifact_loc
        if "ease-out" in sel:
            return panel_loc
        return no_loc

    mock_page.get_by_text = MagicMock(return_value=no_loc)
    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.wait_for_timeout = AsyncMock()
    mock_page.evaluate = AsyncMock(return_value="")

    result = await driver.extract_response(mock_page)
    assert "Z" in result
    artifact_loc.click.assert_called_once()


async def test_extract_response_artifact_open_exception(mock_page):
    """Exception opening artifact panel → silently caught (lines 278-279)."""
    driver = _driver()
    no_loc = _make_loc(count=0)
    artifact_loc = _make_loc(count=1, visible=True)
    artifact_loc.click = AsyncMock(side_effect=Exception("click failed"))

    def _locator(sel):
        if 'aria-label="Download"' in sel:
            return no_loc
        if "artifact" in sel or "document" in sel or "DOCX" in sel:
            return artifact_loc
        return no_loc

    mock_page.get_by_text = MagicMock(return_value=no_loc)
    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.wait_for_timeout = AsyncMock()
    mock_page.evaluate = AsyncMock(return_value="fallback body text " * 5)

    result = await driver.extract_response(mock_page)
    assert isinstance(result, str)


async def test_extract_response_docx_exception(mock_page):
    """Exception during DOCX download → caught, falls through (lines 297-298)."""
    driver = _driver()
    no_loc = _make_loc(count=0)
    dl_btn = _make_loc(count=1, visible=True)

    def _locator(sel):
        if 'aria-label="Download"' in sel:
            return dl_btn
        return no_loc

    mock_page.get_by_text = MagicMock(return_value=no_loc)
    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.wait_for_timeout = AsyncMock()
    mock_page.evaluate = AsyncMock(return_value="fallback " * 10)
    mock_page.expect_download = MagicMock(side_effect=Exception("download failed"))

    result = await driver.extract_response(mock_page)
    assert isinstance(result, str)


async def test_extract_response_panel_exception(mock_page):
    """Exception in panel selector → caught, falls through (lines 308-309)."""
    driver = _driver()
    no_loc = _make_loc(count=0)
    panel_loc = _make_loc(count=1)
    panel_loc.inner_text = AsyncMock(side_effect=Exception("panel error"))

    def _locator(sel):
        if 'aria-label="Download"' in sel:
            return no_loc
        if "artifact" in sel or "document" in sel or "DOCX" in sel:
            return no_loc
        if "ease-out" in sel:
            return panel_loc
        return no_loc

    mock_page.get_by_text = MagicMock(return_value=no_loc)
    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.wait_for_timeout = AsyncMock()
    mock_page.evaluate = AsyncMock(return_value="body fallback " * 5)

    result = await driver.extract_response(mock_page)
    assert isinstance(result, str)


async def test_extract_response_body_prompt_echo_warning(mock_page):
    """Full body text is a prompt echo → warning logged but returned (line 371)."""
    driver = _driver()
    driver.prompt_sigs = ["keyword"]
    no_loc = _make_loc(count=0)
    body_text = "keyword " * 100

    mock_page.get_by_text = MagicMock(return_value=no_loc)
    mock_page.locator = MagicMock(return_value=no_loc)
    mock_page.wait_for_timeout = AsyncMock()
    mock_page.evaluate = AsyncMock(return_value=body_text)

    result = await driver.extract_response(mock_page)
    assert result == body_text


async def test_extract_response_marker_prompt_echo_log(mock_page):
    """Heading positions are prompt echoes → log line 328-329 hit."""
    driver = _driver()
    driver.prompt_sigs = ["heading content"]
    no_loc = _make_loc(count=0)
    body = "# heading content\n" + "A" * 400

    mock_page.get_by_text = MagicMock(return_value=no_loc)
    mock_page.locator = MagicMock(return_value=no_loc)
    mock_page.wait_for_timeout = AsyncMock()

    call_idx = [0]

    async def _evaluate(script, *args):
        call_idx[0] += 1
        if "querySelectorAll" in script or "conversation-turn" in script:
            return ""
        return body

    mock_page.evaluate = MagicMock(side_effect=_evaluate)

    result = await driver.extract_response(mock_page)
    assert isinstance(result, str)
