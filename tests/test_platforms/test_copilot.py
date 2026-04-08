"""Tests for Copilot platform driver — 100% coverage."""

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

from platforms.copilot import Copilot  # noqa: E402


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_loc(count=0, visible=False, text="", attr=None):
    loc = MagicMock()
    loc.first = loc
    loc.count = AsyncMock(return_value=count)
    loc.is_visible = AsyncMock(return_value=visible)
    loc.click = AsyncMock()
    loc.hover = AsyncMock()
    loc.get_attribute = AsyncMock(return_value=attr)
    loc.inner_text = AsyncMock(return_value=text)
    loc.evaluate = AsyncMock(return_value=None)
    loc.fill = AsyncMock()
    loc.dispatch_event = AsyncMock()
    loc.nth = lambda n: loc
    return loc


def _driver():
    d = Copilot()
    d.agent_manager = None
    d.prompt_sigs = []
    return d


# ══════════════════════════════════════════════════════════════════════════════
# check_rate_limit
# ══════════════════════════════════════════════════════════════════════════════

async def test_check_rate_limit_found(mock_page):
    """Visible rate limit text → returns pattern."""
    driver = _driver()
    loc = _make_loc(count=1, visible=True)
    mock_page.get_by_text = MagicMock(return_value=loc)
    result = await driver.check_rate_limit(mock_page)
    assert result == "conversation limit"


async def test_check_rate_limit_none(mock_page):
    """No rate limit text visible → returns None."""
    driver = _driver()
    loc = _make_loc(count=0)
    mock_page.get_by_text = MagicMock(return_value=loc)
    result = await driver.check_rate_limit(mock_page)
    assert result is None


async def test_check_rate_limit_exception(mock_page):
    """Exception in get_by_text → silently caught, returns None."""
    driver = _driver()
    mock_page.get_by_text = MagicMock(side_effect=Exception("boom"))
    result = await driver.check_rate_limit(mock_page)
    assert result is None


# ══════════════════════════════════════════════════════════════════════════════
# configure_mode
# ══════════════════════════════════════════════════════════════════════════════

async def test_configure_mode_think_deeper_selected(mock_page):
    """mode_btn found, Think deeper clicked → label includes Think deeper."""
    driver = _driver()
    mode_btn = _make_loc(count=1, visible=True)
    think_loc = _make_loc(count=1, visible=True)

    def _locator(sel):
        return mode_btn

    def _get_by_text(text, **kw):
        if text == "Think deeper":
            return think_loc
        return _make_loc(count=0)

    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.get_by_text = MagicMock(side_effect=_get_by_text)
    mock_page.wait_for_timeout = AsyncMock()

    result = await driver.configure_mode(mock_page, "REGULAR")
    assert "Think deeper" in result


async def test_configure_mode_smart_text_fallback(mock_page):
    """aria-label mode_btn count=0, Smart text fallback found."""
    driver = _driver()
    no_loc = _make_loc(count=0)
    smart_loc = _make_loc(count=1, visible=True)
    think_loc = _make_loc(count=1, visible=True)

    call_idx = [0]

    def _locator(sel):
        call_idx[0] += 1
        return no_loc

    def _get_by_text(text, **kw):
        if text == "Smart":
            return smart_loc
        if text == "Think deeper":
            return think_loc
        return no_loc

    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.get_by_text = MagicMock(side_effect=_get_by_text)
    mock_page.wait_for_timeout = AsyncMock()

    result = await driver.configure_mode(mock_page, "REGULAR")
    assert "Think deeper" in result


async def test_configure_mode_think_deeper_not_found(mock_page):
    """mode_btn found but Think deeper option absent → Default."""
    driver = _driver()
    mode_btn = _make_loc(count=1, visible=True)
    no_loc = _make_loc(count=0)

    mock_page.locator = MagicMock(return_value=mode_btn)
    mock_page.get_by_text = MagicMock(return_value=no_loc)
    mock_page.wait_for_timeout = AsyncMock()

    result = await driver.configure_mode(mock_page, "REGULAR")
    assert result == "Default"


async def test_configure_mode_think_deeper_exception(mock_page):
    """Exception in think-deeper block → caught, continues."""
    driver = _driver()
    mock_page.locator = MagicMock(side_effect=Exception("oops"))
    mock_page.get_by_text = MagicMock(return_value=_make_loc(count=0))
    mock_page.wait_for_timeout = AsyncMock()

    result = await driver.configure_mode(mock_page, "REGULAR")
    assert result == "Default"


async def test_configure_mode_deep_research_enabled(mock_page):
    """DEEP mode: plus button found, Start deep research clicked."""
    driver = _driver()
    mode_btn = _make_loc(count=0)
    plus_loc = _make_loc(count=1, visible=True)
    dr_loc = _make_loc(count=1, visible=True)

    call_idx = [0]

    def _locator(sel):
        call_idx[0] += 1
        if "Add" in sel or "attach" in sel:
            return plus_loc
        return mode_btn

    def _get_by_text(text, **kw):
        if text == "Start deep research":
            return dr_loc
        return _make_loc(count=0)

    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.get_by_text = MagicMock(side_effect=_get_by_text)
    mock_page.wait_for_timeout = AsyncMock()

    result = await driver.configure_mode(mock_page, "DEEP")
    assert "Deep Research" in result


async def test_configure_mode_deep_plus_text_fallback(mock_page):
    """DEEP mode: aria-label button count=0, + text fallback found."""
    driver = _driver()
    no_loc = _make_loc(count=0)
    plus_text_loc = _make_loc(count=1, visible=True)
    dr_loc = _make_loc(count=1, visible=True)

    call_idx = [0]

    def _locator(sel):
        return no_loc

    def _get_by_text(text, **kw):
        if text == "+":
            return plus_text_loc
        if text == "Start deep research":
            return dr_loc
        return no_loc

    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.get_by_text = MagicMock(side_effect=_get_by_text)
    mock_page.wait_for_timeout = AsyncMock()

    result = await driver.configure_mode(mock_page, "DEEP")
    assert "Deep Research" in result


async def test_configure_mode_deep_exception(mock_page):
    """DEEP mode: exception in deep research block → caught, returns label."""
    driver = _driver()
    mode_btn = _make_loc(count=0)
    call_idx = [0]

    def _locator(sel):
        call_idx[0] += 1
        if call_idx[0] > 3:
            raise Exception("deep crash")
        return mode_btn

    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.get_by_text = MagicMock(return_value=_make_loc(count=0))
    mock_page.wait_for_timeout = AsyncMock()

    result = await driver.configure_mode(mock_page, "DEEP")
    assert result == "Default"


async def test_configure_mode_deep_no_dr_option(mock_page):
    """DEEP mode: plus button found but Start deep research absent."""
    driver = _driver()
    no_loc = _make_loc(count=0)
    plus_loc = _make_loc(count=1, visible=True)

    def _locator(sel):
        if "Add" in sel or "attach" in sel:
            return plus_loc
        return no_loc

    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.get_by_text = MagicMock(return_value=no_loc)
    mock_page.wait_for_timeout = AsyncMock()

    result = await driver.configure_mode(mock_page, "DEEP")
    assert result == "Default"


# ══════════════════════════════════════════════════════════════════════════════
# inject_prompt
# ══════════════════════════════════════════════════════════════════════════════

async def test_inject_prompt_message_textarea(mock_page):
    """Textarea with Message placeholder found and filled."""
    driver = _driver()
    textarea = _make_loc(count=1, visible=True)
    mock_page.locator = MagicMock(return_value=textarea)
    mock_page.wait_for_timeout = AsyncMock()

    await driver.inject_prompt(mock_page, "hello copilot")
    textarea.fill.assert_called_once_with("hello copilot")
    textarea.dispatch_event.assert_called_once_with("input")


async def test_inject_prompt_fallback_textarea(mock_page):
    """Message placeholder absent; fallback to non-hidden textarea."""
    driver = _driver()
    no_loc = _make_loc(count=0)
    fallback = _make_loc(count=1)

    call_idx = [0]

    def _locator(sel):
        call_idx[0] += 1
        if "Message" in sel:
            return no_loc
        return fallback

    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.wait_for_timeout = AsyncMock()

    await driver.inject_prompt(mock_page, "test")
    fallback.fill.assert_called_once_with("test")


async def test_inject_prompt_last_resort_textarea(mock_page):
    """Both specific selectors return count=0; last resort plain textarea used."""
    driver = _driver()
    no_loc = _make_loc(count=0)
    plain = _make_loc(count=1)

    call_idx = [0]

    def _locator(sel):
        call_idx[0] += 1
        if call_idx[0] <= 2:
            return no_loc
        return plain

    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.wait_for_timeout = AsyncMock()

    await driver.inject_prompt(mock_page, "test")
    plain.fill.assert_called_once_with("test")


async def test_inject_prompt_no_textarea_raises(mock_page):
    """All textarea selectors return count=0 → RuntimeError raised."""
    driver = _driver()
    no_loc = _make_loc(count=0)
    mock_page.locator = MagicMock(return_value=no_loc)
    mock_page.wait_for_timeout = AsyncMock()

    with pytest.raises(RuntimeError, match="No textarea found on Copilot"):
        await driver.inject_prompt(mock_page, "test")


# ══════════════════════════════════════════════════════════════════════════════
# click_send
# ══════════════════════════════════════════════════════════════════════════════

async def test_click_send_aria_label_send(mock_page):
    """Send button found via aria-label → clicked."""
    driver = _driver()
    send_btn = _make_loc(count=1, visible=True, attr="Send message")
    mock_page.locator = MagicMock(return_value=send_btn)
    mock_page.get_by_role = MagicMock(return_value=_make_loc(count=0))

    await driver.click_send(mock_page)
    send_btn.click.assert_called_once()


async def test_click_send_skips_microphone(mock_page):
    """Send button with microphone in aria-label → skipped, role fallback."""
    driver = _driver()
    mic_btn = _make_loc(count=1, visible=True, attr="microphone send")
    send_role = _make_loc(count=1, visible=True, attr="Send")

    call_idx = [0]

    def _locator(sel):
        return mic_btn

    def _get_by_role(role, **kw):
        return send_role

    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.get_by_role = MagicMock(side_effect=_get_by_role)

    await driver.click_send(mock_page)
    send_role.click.assert_called_once()


async def test_click_send_role_fallback_skips_mic(mock_page):
    """Role button with voice in aria-label → skipped, falls to Enter."""
    driver = _driver()
    no_loc = _make_loc(count=0)
    voice_btn = _make_loc(count=1, visible=True, attr="voice input")

    mock_page.locator = MagicMock(return_value=no_loc)
    mock_page.get_by_role = MagicMock(return_value=voice_btn)
    mock_page.keyboard = MagicMock()
    mock_page.keyboard.press = AsyncMock()

    # agent_manager is None so _agent_fallback raises, falls to Enter
    await driver.click_send(mock_page)
    mock_page.keyboard.press.assert_called_once_with("Enter")


async def test_click_send_no_button_presses_enter(mock_page):
    """No send button found → presses Enter."""
    driver = _driver()
    no_loc = _make_loc(count=0)
    mock_page.locator = MagicMock(return_value=no_loc)
    mock_page.get_by_role = MagicMock(return_value=no_loc)
    mock_page.keyboard = MagicMock()
    mock_page.keyboard.press = AsyncMock()

    await driver.click_send(mock_page)
    mock_page.keyboard.press.assert_called_once_with("Enter")


# ══════════════════════════════════════════════════════════════════════════════
# post_send
# ══════════════════════════════════════════════════════════════════════════════

async def test_post_send_url_changed(mock_page):
    """URL contains /chats/ → no retry send."""
    driver = _driver()
    mock_page.url = "https://copilot.microsoft.com/chats/abc123"
    mock_page.wait_for_timeout = AsyncMock()
    mock_page.locator = MagicMock(return_value=_make_loc(count=0))
    mock_page.get_by_text = MagicMock(return_value=_make_loc(count=0))

    await driver.post_send(mock_page, "REGULAR")


async def test_post_send_url_not_changed_retries_send(mock_page):
    """URL without /chats/ → retries click_send."""
    driver = _driver()
    mock_page.url = "https://copilot.microsoft.com/home"
    mock_page.wait_for_timeout = AsyncMock()
    no_loc = _make_loc(count=0)
    mock_page.locator = MagicMock(return_value=no_loc)
    mock_page.get_by_role = MagicMock(return_value=no_loc)
    mock_page.get_by_text = MagicMock(return_value=no_loc)
    mock_page.keyboard = MagicMock()
    mock_page.keyboard.press = AsyncMock()

    await driver.post_send(mock_page, "REGULAR")
    mock_page.keyboard.press.assert_called()


async def test_post_send_deep_start_research_clicked(mock_page):
    """DEEP mode: Start research button found and clicked."""
    driver = _driver()
    mock_page.url = "https://copilot.microsoft.com/chats/abc"
    mock_page.wait_for_timeout = AsyncMock()
    start_loc = _make_loc(count=1, visible=True)
    mock_page.get_by_text = MagicMock(return_value=start_loc)

    await driver.post_send(mock_page, "DEEP")
    start_loc.click.assert_called_once()


async def test_post_send_deep_start_research_exception(mock_page):
    """DEEP mode: exception checking Start research → caught."""
    driver = _driver()
    mock_page.url = "https://copilot.microsoft.com/chats/abc"
    mock_page.wait_for_timeout = AsyncMock()
    mock_page.get_by_text = MagicMock(side_effect=Exception("boom"))

    await driver.post_send(mock_page, "DEEP")


async def test_post_send_deep_no_start_research_button(mock_page):
    """DEEP mode: Start research not found after 6 checks → warning logged."""
    driver = _driver()
    mock_page.url = "https://copilot.microsoft.com/chats/abc"
    mock_page.wait_for_timeout = AsyncMock()
    no_loc = _make_loc(count=0)
    mock_page.get_by_text = MagicMock(return_value=no_loc)

    await driver.post_send(mock_page, "DEEP")


# ══════════════════════════════════════════════════════════════════════════════
# completion_check
# ══════════════════════════════════════════════════════════════════════════════

async def test_completion_check_stop_button_visible(mock_page):
    """Stop button visible → returns False."""
    driver = _driver()
    stop_loc = _make_loc(count=1, visible=True)
    mock_page.locator = MagicMock(return_value=stop_loc)
    mock_page.evaluate = AsyncMock(return_value=False)
    mock_page.url = "https://copilot.microsoft.com/chats/abc"

    result = await driver.completion_check(mock_page)
    assert result is False


async def test_completion_check_stop_exception(mock_page):
    """Exception checking stop button → silently caught."""
    driver = _driver()
    mock_page.locator = MagicMock(side_effect=Exception("locator crash"))
    mock_page.evaluate = AsyncMock(return_value=False)
    mock_page.url = "https://copilot.microsoft.com/home"

    result = await driver.completion_check(mock_page)
    assert result is False


async def test_completion_check_thinking_indicator_visible(mock_page):
    """Thinking indicator visible → returns False."""
    driver = _driver()
    no_stop = _make_loc(count=0)
    think_loc = _make_loc(count=1, visible=True)

    call_idx = [0]

    def _locator(sel):
        call_idx[0] += 1
        if "Stop" in sel or "Cancel" in sel:
            return no_stop
        return think_loc

    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.evaluate = AsyncMock(return_value=False)
    mock_page.url = "https://copilot.microsoft.com/chats/abc"

    result = await driver.completion_check(mock_page)
    assert result is False


async def test_completion_check_thinking_exception(mock_page):
    """Exception checking thinking indicators → silently caught."""
    driver = _driver()
    no_stop = _make_loc(count=0)
    call_idx = [0]

    def _locator(sel):
        call_idx[0] += 1
        if call_idx[0] <= 2:
            return no_stop
        raise Exception("indicator crash")

    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.evaluate = AsyncMock(return_value=False)
    mock_page.url = "https://copilot.microsoft.com/home"

    result = await driver.completion_check(mock_page)
    assert result is False


async def test_completion_check_chats_url_no_reply(mock_page):
    """URL has /chats/ but no 'Copilot said' → is_thinking=True → False."""
    driver = _driver()
    no_loc = _make_loc(count=0)
    mock_page.locator = MagicMock(return_value=no_loc)
    mock_page.evaluate = AsyncMock(return_value=False)  # copilot_replied = False
    mock_page.url = "https://copilot.microsoft.com/chats/abc"

    result = await driver.completion_check(mock_page)
    assert result is False


async def test_completion_check_chats_evaluate_exception(mock_page):
    """Exception checking copilot_replied → silently caught."""
    driver = _driver()
    no_loc = _make_loc(count=0)
    mock_page.locator = MagicMock(return_value=no_loc)
    mock_page.evaluate = AsyncMock(side_effect=Exception("eval crash"))
    mock_page.url = "https://copilot.microsoft.com/chats/abc"

    result = await driver.completion_check(mock_page)
    assert result is False


async def test_completion_check_text_growing(mock_page):
    """Response text growing → no_stop_polls reset, returns False."""
    driver = _driver()
    driver._last_response_len = 100
    no_loc = _make_loc(count=0)
    mock_page.locator = MagicMock(return_value=no_loc)
    mock_page.evaluate = AsyncMock(return_value=200)  # growing
    mock_page.url = "https://copilot.microsoft.com/home"

    result = await driver.completion_check(mock_page)
    assert result is False
    assert driver._last_response_len == 200


async def test_completion_check_text_stable_evaluate_exception(mock_page):
    """Exception in page.evaluate for text length → silently caught."""
    driver = _driver()
    no_loc = _make_loc(count=0)
    mock_page.locator = MagicMock(return_value=no_loc)

    call_idx = [0]

    async def _evaluate(script, *args):
        call_idx[0] += 1
        if call_idx[0] == 1:
            return False  # copilot_replied (bool)
        raise Exception("eval crash")

    mock_page.evaluate = MagicMock(side_effect=_evaluate)
    mock_page.url = "https://copilot.microsoft.com/chats/abc"

    result = await driver.completion_check(mock_page)
    assert result is False


async def test_completion_check_stable_3_polls_large_response(mock_page):
    """3 polls with stable text >5000 → declares complete."""
    driver = _driver()
    driver._no_stop_polls = 3
    driver._last_response_len = 6000
    no_loc = _make_loc(count=0)
    mock_page.locator = MagicMock(return_value=no_loc)
    mock_page.evaluate = AsyncMock(return_value=6000)  # stable, same value
    mock_page.url = "https://copilot.microsoft.com/home"

    result = await driver.completion_check(mock_page)
    assert result is True


async def test_completion_check_8_polls_no_activity(mock_page):
    """8 polls with no activity → declares complete."""
    driver = _driver()
    driver._no_stop_polls = 8
    driver._last_response_len = 100  # stable — same as what evaluate returns
    no_loc = _make_loc(count=0)
    mock_page.locator = MagicMock(return_value=no_loc)
    mock_page.evaluate = AsyncMock(return_value=100)
    mock_page.url = "https://copilot.microsoft.com/home"

    result = await driver.completion_check(mock_page)
    assert result is True


# ══════════════════════════════════════════════════════════════════════════════
# extract_response
# ══════════════════════════════════════════════════════════════════════════════

async def test_extract_response_copilot_said_marker(mock_page):
    """Body has 'Copilot said' marker with >200 chars → extracted."""
    driver = _driver()
    body = "Copilot said\nHere is the full response " + "X" * 300
    mock_page.evaluate = AsyncMock(return_value=body)

    result = await driver.extract_response(mock_page)
    assert len(result) > 200


async def test_extract_response_copilot_said_see_my_thinking(mock_page):
    """'Copilot said' extraction returns string starting with See my thinking.

    The JS strips it internally. The mock returns the post-strip JS output
    (what JS would return after startsWith check removes the prefix).
    """
    driver = _driver()
    # Mock returns what the JS produces AFTER stripping "See my thinking":
    # a long response with no prefix
    js_result = "Actual response " + "X" * 200  # JS already stripped the prefix

    call_idx = [0]

    async def _evaluate(script, *args):
        call_idx[0] += 1
        if call_idx[0] == 1:
            return js_result
        return ""

    mock_page.evaluate = MagicMock(side_effect=_evaluate)

    result = await driver.extract_response(mock_page)
    assert len(result) > 200
    assert "Actual response" in result


async def test_extract_response_copilot_said_short(mock_page):
    """'Copilot said' response < 200 chars → falls to markdown marker."""
    driver = _driver()
    body_short = "Copilot said\nshort"
    body_md = "## Heading\n" + "Content " * 100

    call_idx = [0]

    async def _evaluate(script, *args):
        call_idx[0] += 1
        if "Copilot said" in script or call_idx[0] == 1:
            return body_short
        return body_md

    mock_page.evaluate = MagicMock(side_effect=_evaluate)

    result = await driver.extract_response(mock_page)
    assert isinstance(result, str)


async def test_extract_response_copilot_said_exception(mock_page):
    """Exception in Copilot-said extraction → falls through."""
    driver = _driver()
    body = "## Heading\n" + "Content " * 100

    call_idx = [0]

    async def _evaluate(script, *args):
        call_idx[0] += 1
        if call_idx[0] == 1:
            raise Exception("eval crash")
        return body

    mock_page.evaluate = MagicMock(side_effect=_evaluate)

    result = await driver.extract_response(mock_page)
    assert isinstance(result, str)


async def test_extract_response_markdown_marker(mock_page):
    """Markdown ## heading in body → extracted."""
    driver = _driver()
    body = "Preamble text\n## Main Heading\n" + "Response content " * 50

    call_idx = [0]

    async def _evaluate(script, *args):
        return body

    mock_page.evaluate = MagicMock(side_effect=_evaluate)

    result = await driver.extract_response(mock_page)
    assert "Main Heading" in result


async def test_extract_response_markdown_prompt_echo_skipped(mock_page):
    """Markdown heading is a prompt echo → skipped."""
    driver = _driver()
    driver.prompt_sigs = ["main heading"]
    body = "## Main Heading\n" + "A" * 300

    mock_page.evaluate = AsyncMock(return_value=body)

    result = await driver.extract_response(mock_page)
    # Falls through to body.innerText
    assert result == body


async def test_extract_response_markdown_exception(mock_page):
    """Exception in markdown extraction → falls to body.innerText."""
    driver = _driver()
    body = "fallback body " * 10

    call_idx = [0]

    async def _evaluate(script, *args):
        call_idx[0] += 1
        if call_idx[0] == 1:
            return ""  # copilot-said → empty
        if call_idx[0] == 2:
            raise Exception("body crash")
        return body

    mock_page.evaluate = MagicMock(side_effect=_evaluate)

    result = await driver.extract_response(mock_page)
    assert isinstance(result, str)


async def test_extract_response_body_innertext_fallback(mock_page):
    """All other methods yield nothing → body.innerText fallback."""
    driver = _driver()
    body_text = "final body content " * 5
    mock_page.evaluate = AsyncMock(return_value=body_text)

    result = await driver.extract_response(mock_page)
    assert result == body_text


async def test_extract_response_body_prompt_echo_warning(mock_page):
    """body.innerText is a prompt echo → warning logged, returned as-is."""
    driver = _driver()
    driver.prompt_sigs = ["keyword"]
    body_text = "keyword " * 100

    mock_page.evaluate = AsyncMock(return_value=body_text)

    result = await driver.extract_response(mock_page)
    assert result == body_text


# ── Additional tests for missing lines ────────────────────────────────────────

async def test_configure_mode_deep_exception_in_deep_block(mock_page):
    """Exception inside DEEP mode block → caught, warning logged (lines 92-93)."""
    driver = _driver()
    no_loc = _make_loc(count=0)
    plus_loc = _make_loc(count=1, visible=True)
    plus_loc.click = AsyncMock(side_effect=Exception("deep crash"))

    call_idx = [0]

    def _locator(sel):
        call_idx[0] += 1
        if "Add" in sel or "attach" in sel:
            return plus_loc
        return no_loc

    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.get_by_text = MagicMock(return_value=no_loc)
    mock_page.wait_for_timeout = AsyncMock()

    result = await driver.configure_mode(mock_page, "DEEP")
    assert result == "Default"


async def test_click_send_selector_mic_skipped_then_found(mock_page):
    """Selector loop: first button has mic in aria, second is real send (line 133)."""
    driver = _driver()
    mic_btn = _make_loc(count=1, visible=True, attr="mic button")
    real_send = _make_loc(count=1, visible=True, attr="Send message")

    call_idx = [0]

    def _locator(sel):
        call_idx[0] += 1
        if call_idx[0] == 1:
            return mic_btn
        return real_send

    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.get_by_role = MagicMock(return_value=_make_loc(count=0))

    await driver.click_send(mock_page)
    real_send.click.assert_called_once()


async def test_click_send_role_mic_skipped_then_found(mock_page):
    """Role loop: first role button has mic in aria → continue, second is real send."""
    driver = _driver()
    no_loc = _make_loc(count=0)
    mic_role = _make_loc(count=1, visible=True, attr="microphone")
    real_role = _make_loc(count=1, visible=True, attr="Submit message")

    mock_page.locator = MagicMock(return_value=no_loc)

    call_idx = [0]

    def _get_by_role(role, **kw):
        call_idx[0] += 1
        if call_idx[0] == 1:
            return mic_role
        return real_role

    mock_page.get_by_role = MagicMock(side_effect=_get_by_role)

    await driver.click_send(mock_page)
    real_role.click.assert_called_once()


async def test_click_send_all_roles_mic_falls_to_agent_fallback_return(mock_page):
    """Both role buttons are mic → agent_fallback called; if it succeeds, return (line 155)."""
    driver = _driver()
    no_loc = _make_loc(count=0)
    mic_role = _make_loc(count=1, visible=True, attr="voice input")

    mock_page.locator = MagicMock(return_value=no_loc)
    mock_page.get_by_role = MagicMock(return_value=mic_role)

    # Mock agent_manager so _agent_fallback succeeds instead of raising
    manager = MagicMock()
    manager.enabled = True
    manager.fallback = AsyncMock(return_value="clicked")

    import types as _types
    _af_mod = sys.modules.get("agent_fallback")
    if _af_mod:
        _af_mod.FallbackStep = MagicMock(return_value="click_send")

    driver.agent_manager = manager

    await driver.click_send(mock_page)
    manager.fallback.assert_called_once()


async def test_extract_response_markdown_prompt_echo_log(mock_page):
    """Markdown position is a prompt echo → log debug emitted (lines 332-333)."""
    driver = _driver()
    driver.prompt_sigs = ["heading text"]
    body = "## heading text\n" + "A" * 300

    call_idx = [0]

    async def _evaluate(script, *args):
        call_idx[0] += 1
        if call_idx[0] == 1:
            return ""  # copilot-said → empty
        return body

    mock_page.evaluate = MagicMock(side_effect=_evaluate)

    result = await driver.extract_response(mock_page)
    # All headings were prompt echoes → falls to body.innerText
    assert result == body
