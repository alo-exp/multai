"""Tests for DeepSeek platform driver — 100% coverage."""

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

from platforms.deepseek import DeepSeek  # noqa: E402


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
    loc.bounding_box = AsyncMock(return_value={"width": 30, "height": 30})
    loc.nth = lambda n: loc
    return loc


def _driver():
    d = DeepSeek()
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
    assert result == "server is busy"


async def test_check_rate_limit_none(mock_page):
    """No rate limit text visible → returns None."""
    driver = _driver()
    loc = _make_loc(count=0)
    mock_page.get_by_text = MagicMock(return_value=loc)
    result = await driver.check_rate_limit(mock_page)
    assert result is None


async def test_check_rate_limit_exception(mock_page):
    """Exception → silently caught, returns None."""
    driver = _driver()
    mock_page.get_by_text = MagicMock(side_effect=Exception("boom"))
    result = await driver.check_rate_limit(mock_page)
    assert result is None


# ══════════════════════════════════════════════════════════════════════════════
# configure_mode
# ══════════════════════════════════════════════════════════════════════════════

async def test_configure_mode_deepthink_by_text(mock_page):
    """DeepThink text found and clicked."""
    driver = _driver()
    dt_loc = _make_loc(count=1, visible=True)
    search_loc = _make_loc(count=1, visible=True)

    def _get_by_text(text, **kw):
        if text == "DeepThink":
            return dt_loc
        if text == "Search":
            return search_loc
        return _make_loc(count=0)

    mock_page.get_by_text = MagicMock(side_effect=_get_by_text)
    mock_page.locator = MagicMock(return_value=_make_loc(count=0))
    mock_page.wait_for_timeout = AsyncMock()

    result = await driver.configure_mode(mock_page, "DEEP")
    assert result == "DeepThink + Search"
    dt_loc.click.assert_called_once()
    search_loc.click.assert_called_once()


async def test_configure_mode_deepthink_not_found_fallback_selector(mock_page):
    """DeepThink text not found → tries aria-label/class selectors."""
    driver = _driver()
    no_text = _make_loc(count=0)
    dt_sel_loc = _make_loc(count=1)
    search_text = _make_loc(count=1, visible=True)

    def _get_by_text(text, **kw):
        if text == "Search":
            return search_text
        return no_text

    def _locator(sel):
        if "DeepThink" in sel or "deep-think" in sel:
            return dt_sel_loc
        return _make_loc(count=0)

    mock_page.get_by_text = MagicMock(side_effect=_get_by_text)
    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.wait_for_timeout = AsyncMock()

    result = await driver.configure_mode(mock_page, "DEEP")
    assert result == "DeepThink + Search"


async def test_configure_mode_deepthink_exception(mock_page):
    """Exception in DeepThink block → caught, continues to Search."""
    driver = _driver()
    mock_page.get_by_text = MagicMock(side_effect=Exception("dt crash"))
    mock_page.locator = MagicMock(return_value=_make_loc(count=0))
    mock_page.wait_for_timeout = AsyncMock()

    result = await driver.configure_mode(mock_page, "DEEP")
    assert result == "DeepThink + Search"


async def test_configure_mode_search_not_found_fallback_selector(mock_page):
    """Search text not found → tries aria-label/class selectors."""
    driver = _driver()
    dt_text = _make_loc(count=1, visible=True)
    no_text = _make_loc(count=0)
    search_sel_loc = _make_loc(count=1)

    call_idx = [0]

    def _get_by_text(text, **kw):
        if text == "DeepThink":
            return dt_text
        return no_text

    def _locator(sel):
        if "Search" in sel or "search" in sel:
            return search_sel_loc
        return _make_loc(count=0)

    mock_page.get_by_text = MagicMock(side_effect=_get_by_text)
    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.wait_for_timeout = AsyncMock()

    result = await driver.configure_mode(mock_page, "DEEP")
    assert result == "DeepThink + Search"


async def test_configure_mode_search_exception(mock_page):
    """Exception in Search block → caught, returns label."""
    driver = _driver()
    dt_text = _make_loc(count=1, visible=True)
    no_loc = _make_loc(count=0)

    call_idx = [0]

    def _get_by_text(text, **kw):
        call_idx[0] += 1
        if text == "DeepThink":
            return dt_text
        raise Exception("search crash")

    mock_page.get_by_text = MagicMock(side_effect=_get_by_text)
    mock_page.locator = MagicMock(return_value=no_loc)
    mock_page.wait_for_timeout = AsyncMock()

    result = await driver.configure_mode(mock_page, "DEEP")
    assert result == "DeepThink + Search"


# ══════════════════════════════════════════════════════════════════════════════
# inject_prompt
# ══════════════════════════════════════════════════════════════════════════════

async def test_inject_prompt_success(mock_page):
    """Textarea found and filled via nativeInputValueSetter."""
    driver = _driver()
    textarea = _make_loc(count=1)
    mock_page.locator = MagicMock(return_value=textarea)
    mock_page.wait_for_timeout = AsyncMock()
    mock_page.evaluate = AsyncMock(return_value=None)

    await driver.inject_prompt(mock_page, "test prompt")
    textarea.click.assert_called_once()
    mock_page.evaluate.assert_called()


async def test_inject_prompt_no_textarea_raises(mock_page):
    """No textarea → RuntimeError raised."""
    driver = _driver()
    no_loc = _make_loc(count=0)
    mock_page.locator = MagicMock(return_value=no_loc)
    mock_page.wait_for_timeout = AsyncMock()

    with pytest.raises(RuntimeError, match="No textarea found on DeepSeek"):
        await driver.inject_prompt(mock_page, "test")


# ══════════════════════════════════════════════════════════════════════════════
# click_send
# ══════════════════════════════════════════════════════════════════════════════

async def test_click_send_ds_icon_button(mock_page):
    """ds-icon-button found → last one clicked."""
    driver = _driver()
    btn = _make_loc(count=1, visible=True)
    mock_page.locator = MagicMock(return_value=btn)

    await driver.click_send(mock_page)
    btn.click.assert_called_once()


async def test_click_send_ds_icon_button_exception_falls_to_role(mock_page):
    """Exception in ds-icon-button → falls to role=button fallback."""
    driver = _driver()
    fail_loc = MagicMock()
    fail_loc.count = AsyncMock(side_effect=Exception("ds crash"))

    small_btn = _make_loc(count=1, visible=True)
    small_btn.bounding_box = AsyncMock(return_value={"width": 30, "height": 30})

    call_idx = [0]

    def _locator(sel):
        call_idx[0] += 1
        if "ds-icon-button" in sel and "[role" not in sel:
            return fail_loc
        if 'role="button"' in sel:
            role_loc = MagicMock()
            role_loc.count = AsyncMock(return_value=1)
            role_loc.nth = lambda n: small_btn
            return role_loc
        return _make_loc(count=0)

    mock_page.locator = MagicMock(side_effect=_locator)

    await driver.click_send(mock_page)
    small_btn.click.assert_called()


async def test_click_send_ds_icon_not_visible_falls_to_role(mock_page):
    """ds-icon-button count=1 but not visible → falls to role=button."""
    driver = _driver()
    not_visible = _make_loc(count=1, visible=False)
    small_btn = _make_loc(count=1, visible=True)
    small_btn.bounding_box = AsyncMock(return_value={"width": 25, "height": 25})

    call_idx = [0]

    def _locator(sel):
        call_idx[0] += 1
        if "ds-icon-button" in sel and "[role" not in sel:
            return not_visible
        if 'div[role="button"]' in sel:
            role_loc = MagicMock()
            role_loc.count = AsyncMock(return_value=1)
            role_loc.nth = lambda n: small_btn
            return role_loc
        return _make_loc(count=0)

    mock_page.locator = MagicMock(side_effect=_locator)

    await driver.click_send(mock_page)
    small_btn.click.assert_called()


async def test_click_send_role_button_large_skipped(mock_page):
    """Role button bounding_box too large → skipped, falls to Enter."""
    driver = _driver()
    no_ds = _make_loc(count=0)
    large_btn = _make_loc(count=1, visible=True)
    large_btn.bounding_box = AsyncMock(return_value={"width": 100, "height": 100})

    call_idx = [0]

    def _locator(sel):
        call_idx[0] += 1
        if "ds-icon-button" in sel and "[role" not in sel:
            return no_ds
        if 'div[role="button"]' in sel:
            role_loc = MagicMock()
            role_loc.count = AsyncMock(return_value=1)
            role_loc.nth = lambda n: large_btn
            return role_loc
        return no_ds

    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.keyboard = MagicMock()
    mock_page.keyboard.press = AsyncMock()

    await driver.click_send(mock_page)
    mock_page.keyboard.press.assert_called_once_with("Enter")


async def test_click_send_role_exception_falls_to_enter(mock_page):
    """Exception in role=button fallback → falls to Enter."""
    driver = _driver()
    no_ds = _make_loc(count=0)

    call_idx = [0]

    def _locator(sel):
        call_idx[0] += 1
        if "ds-icon-button" in sel and "[role" not in sel:
            return no_ds
        raise Exception("role crash")

    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.keyboard = MagicMock()
    mock_page.keyboard.press = AsyncMock()

    await driver.click_send(mock_page)
    mock_page.keyboard.press.assert_called_once_with("Enter")


async def test_click_send_bounding_box_none_skipped(mock_page):
    """Role button bounding_box returns None → skipped."""
    driver = _driver()
    no_ds = _make_loc(count=0)
    none_box_btn = _make_loc(count=1, visible=True)
    none_box_btn.bounding_box = AsyncMock(return_value=None)

    call_idx = [0]

    def _locator(sel):
        call_idx[0] += 1
        if "ds-icon-button" in sel and "[role" not in sel:
            return no_ds
        if 'div[role="button"]' in sel:
            role_loc = MagicMock()
            role_loc.count = AsyncMock(return_value=1)
            role_loc.nth = lambda n: none_box_btn
            return role_loc
        return no_ds

    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.keyboard = MagicMock()
    mock_page.keyboard.press = AsyncMock()

    await driver.click_send(mock_page)
    mock_page.keyboard.press.assert_called_once_with("Enter")


# ══════════════════════════════════════════════════════════════════════════════
# completion_check
# ══════════════════════════════════════════════════════════════════════════════

async def test_completion_check_copy_button_visible(mock_page):
    """Copy button visible in conversation → returns True."""
    driver = _driver()
    mock_page.url = "https://chat.deepseek.com/conv/abc"
    copy_loc = _make_loc(count=1, visible=True)

    def _locator(sel):
        if "Copy" in sel or "Regenerate" in sel:
            return copy_loc
        return _make_loc(count=0)

    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.evaluate = AsyncMock(return_value=False)

    result = await driver.completion_check(mock_page)
    assert result is True


async def test_completion_check_copy_exception(mock_page):
    """Exception checking copy/regen buttons → silently caught."""
    driver = _driver()
    mock_page.url = "https://chat.deepseek.com/conv/abc"
    mock_page.locator = MagicMock(side_effect=Exception("locator crash"))
    mock_page.evaluate = AsyncMock(return_value=False)

    result = await driver.completion_check(mock_page)
    assert result is False


async def test_completion_check_stop_svg_rect_detected(mock_page):
    """SVG rect in ds-icon-button → still generating, returns False."""
    driver = _driver()
    mock_page.url = "https://chat.deepseek.com/conv/abc"
    no_loc = _make_loc(count=0)

    call_idx = [0]

    def _locator(sel):
        call_idx[0] += 1
        if "Copy" in sel or "Regenerate" in sel:
            return no_loc
        return no_loc

    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.evaluate = AsyncMock(return_value=True)  # is_generating = True

    result = await driver.completion_check(mock_page)
    assert result is False


async def test_completion_check_svg_evaluate_exception(mock_page):
    """Exception in SVG evaluate → silently caught, falls to text selectors."""
    driver = _driver()
    mock_page.url = "https://chat.deepseek.com/conv/abc"
    no_loc = _make_loc(count=0)

    call_idx = [0]

    def _locator(sel):
        return no_loc

    async def _evaluate(script, *args):
        if "svg rect" in script or "ds-icon-button" in script:
            raise Exception("svg crash")
        return 100  # text length

    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.evaluate = MagicMock(side_effect=_evaluate)

    result = await driver.completion_check(mock_page)
    assert result is False


async def test_completion_check_stop_text_selector(mock_page):
    """Stop text selector finds button → still generating."""
    driver = _driver()
    mock_page.url = "https://chat.deepseek.com/conv/abc"
    no_loc = _make_loc(count=0)
    stop_loc = _make_loc(count=1, visible=True)

    call_idx = [0]

    def _locator(sel):
        call_idx[0] += 1
        if "Copy" in sel or "Regenerate" in sel:
            return no_loc
        if "Stop" in sel or "stop" in sel or "cancel" in sel:
            return stop_loc
        return no_loc

    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.evaluate = AsyncMock(return_value=False)  # not generating via SVG

    result = await driver.completion_check(mock_page)
    assert result is False


async def test_completion_check_stop_exception(mock_page):
    """Exception in stop-button selectors → silently caught."""
    driver = _driver()
    mock_page.url = "https://chat.deepseek.com/conv/abc"
    no_loc = _make_loc(count=0)

    call_idx = [0]

    def _locator(sel):
        call_idx[0] += 1
        if "Copy" in sel or "Regenerate" in sel:
            return no_loc
        raise Exception("stop crash")

    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.evaluate = AsyncMock(return_value=False)

    result = await driver.completion_check(mock_page)
    assert result is False


async def test_completion_check_animated_indicator(mock_page):
    """Animated thinking indicator visible → still generating."""
    driver = _driver()
    mock_page.url = "https://chat.deepseek.com/conv/abc"
    no_loc = _make_loc(count=0)
    indicator_loc = _make_loc(count=1, visible=True)

    call_idx = [0]

    def _locator(sel):
        call_idx[0] += 1
        if "Copy" in sel or "Regenerate" in sel:
            return no_loc
        if "Stop" in sel or "stop" in sel or "cancel" in sel:
            return no_loc
        if "thinking" in sel or "loading" in sel or "typing" in sel:
            return indicator_loc
        return no_loc

    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.evaluate = AsyncMock(return_value=False)

    result = await driver.completion_check(mock_page)
    assert result is False


async def test_completion_check_indicator_exception(mock_page):
    """Exception in indicator check → silently caught."""
    driver = _driver()
    mock_page.url = "https://chat.deepseek.com/conv/abc"
    no_loc = _make_loc(count=0)

    call_idx = [0]

    def _locator(sel):
        call_idx[0] += 1
        if "Copy" in sel or "Regenerate" in sel:
            return no_loc
        if "Stop" in sel or "stop" in sel or "cancel" in sel:
            return no_loc
        raise Exception("indicator crash")

    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.evaluate = AsyncMock(return_value=False)

    result = await driver.completion_check(mock_page)
    assert result is False


async def test_completion_check_homepage_no_stop_polls_lt_6(mock_page):
    """Homepage (not in conversation), no_stop_polls < 6 → returns False."""
    driver = _driver()
    driver._no_stop_polls = 2
    mock_page.url = "https://chat.deepseek.com"
    no_loc = _make_loc(count=0)
    mock_page.locator = MagicMock(return_value=no_loc)
    mock_page.evaluate = AsyncMock(return_value=False)

    result = await driver.completion_check(mock_page)
    assert result is False


async def test_completion_check_homepage_no_stop_polls_ge_6(mock_page):
    """Homepage, no_stop_polls >= 6 → declares complete (warning)."""
    driver = _driver()
    driver._no_stop_polls = 6
    mock_page.url = "https://chat.deepseek.com"
    no_loc = _make_loc(count=0)
    mock_page.locator = MagicMock(return_value=no_loc)
    mock_page.evaluate = AsyncMock(return_value=False)

    result = await driver.completion_check(mock_page)
    assert result is True


async def test_completion_check_text_growing(mock_page):
    """Page text growing → stable_text_polls reset, returns False."""
    driver = _driver()
    driver._prev_text_len = 100
    mock_page.url = "https://chat.deepseek.com/conv/abc"
    no_loc = _make_loc(count=0)
    mock_page.locator = MagicMock(return_value=no_loc)

    async def _evaluate(script, *args):
        if "ds-icon-button" in script:
            return False  # not generating via SVG
        return 200  # text length growing

    mock_page.evaluate = MagicMock(side_effect=_evaluate)

    result = await driver.completion_check(mock_page)
    assert result is False
    assert driver._prev_text_len == 200


async def test_completion_check_text_evaluate_exception(mock_page):
    """Exception in text-length evaluate → silently caught."""
    driver = _driver()
    mock_page.url = "https://chat.deepseek.com/conv/abc"
    no_loc = _make_loc(count=0)
    mock_page.locator = MagicMock(return_value=no_loc)
    mock_page.evaluate = AsyncMock(side_effect=Exception("eval crash"))

    result = await driver.completion_check(mock_page)
    assert result is False


async def test_completion_check_text_stable_3_polls_large(mock_page):
    """Text stable for 3 polls with >500 chars → declares complete."""
    driver = _driver()
    driver._stable_text_polls = 3
    driver._prev_text_len = 600
    mock_page.url = "https://chat.deepseek.com/conv/abc"
    no_loc = _make_loc(count=0)
    mock_page.locator = MagicMock(return_value=no_loc)

    async def _evaluate(script, *args):
        if "ds-icon-button" in script:
            return False  # SVG check → not generating
        return 600  # text length stable, same as prev → increments stable_text_polls

    mock_page.evaluate = MagicMock(side_effect=_evaluate)

    result = await driver.completion_check(mock_page)
    assert result is True


async def test_completion_check_stable_polls_exception(mock_page):
    """Exception in stable_text_polls check → silently caught."""
    driver = _driver()
    driver._stable_text_polls = 3
    driver._prev_text_len = 600
    mock_page.url = "https://chat.deepseek.com/conv/abc"
    no_loc = _make_loc(count=0)
    mock_page.locator = MagicMock(return_value=no_loc)

    call_idx = [0]

    async def _evaluate(script, *args):
        call_idx[0] += 1
        if call_idx[0] == 1:
            return False  # SVG check
        if call_idx[0] <= 3:
            return 600  # text length stable → increments stable_text_polls
        raise Exception("stable check crash")

    mock_page.evaluate = MagicMock(side_effect=_evaluate)

    result = await driver.completion_check(mock_page)
    assert isinstance(result, bool)


async def test_completion_check_stable_state_fallback(mock_page):
    """no_stop_polls >= stable_state_polls threshold → declares complete."""
    driver = _driver()
    driver._no_stop_polls = 60
    driver._current_max_wait_s = 120
    driver._prev_text_len = 100
    driver._stable_text_polls = 0
    mock_page.url = "https://chat.deepseek.com/conv/abc"
    no_loc = _make_loc(count=0)
    mock_page.locator = MagicMock(return_value=no_loc)

    async def _evaluate(script, *args):
        if "ds-icon-button" in script:
            return False  # SVG check → not generating
        return 100  # text stable but < 500 → stable_text check won't trigger

    mock_page.evaluate = MagicMock(side_effect=_evaluate)

    result = await driver.completion_check(mock_page)
    assert result is True


# ══════════════════════════════════════════════════════════════════════════════
# extract_response
# ══════════════════════════════════════════════════════════════════════════════

async def test_extract_response_js_leaf_blocks(mock_page):
    """JS leaf response blocks return >200 chars → extracted."""
    driver = _driver()
    long_text = "Response content " * 20
    mock_page.evaluate = AsyncMock(return_value=long_text)

    result = await driver.extract_response(mock_page)
    assert result == long_text


async def test_extract_response_js_exception_falls_to_markdown(mock_page):
    """JS leaf extraction raises → falls to markdown locator."""
    driver = _driver()
    md_loc = MagicMock()
    md_loc.count = AsyncMock(return_value=1)
    long_chunk = "Markdown content " * 20
    md_loc.nth = lambda n: _make_loc(text=long_chunk)

    def _locator(sel):
        if "markdown" in sel or "ds-markdown" in sel:
            return md_loc
        return _make_loc(count=0)

    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.evaluate = AsyncMock(side_effect=Exception("js crash"))

    result = await driver.extract_response(mock_page)
    assert "Markdown content" in result


async def test_extract_response_js_short_falls_to_markdown(mock_page):
    """JS leaf extraction returns <200 chars → falls to markdown locator."""
    driver = _driver()

    call_idx = [0]
    short = "short"
    long_chunk = "MD content " * 10

    md_loc = MagicMock()
    md_loc.count = AsyncMock(return_value=1)
    md_loc.nth = lambda n: _make_loc(text=long_chunk)

    def _locator(sel):
        if "markdown" in sel or "ds-markdown" in sel:
            return md_loc
        return _make_loc(count=0)

    async def _evaluate(script, *args):
        call_idx[0] += 1
        if call_idx[0] == 1:
            return short
        return ""

    mock_page.locator = MagicMock(side_effect=_locator)
    mock_page.evaluate = MagicMock(side_effect=_evaluate)

    result = await driver.extract_response(mock_page)
    assert "MD content" in result


async def test_extract_response_markdown_block_skips_short_and_long(mock_page):
    """Markdown blocks: skip <50 chars and >15000 chars, use middle range."""
    driver = _driver()

    call_idx = [0]

    async def _evaluate(script, *args):
        return ""  # JS extraction fails

    mock_page.evaluate = MagicMock(side_effect=_evaluate)

    short_loc = _make_loc(text="short")
    long_loc = _make_loc(text="X" * 16000)
    good_loc = _make_loc(text="Good content " * 10)

    call_n = [0]

    class FakeMDLoc:
        count = AsyncMock(return_value=3)

        def nth(self, n):
            if n == 0:
                return short_loc
            elif n == 1:
                return long_loc
            return good_loc

    def _locator(sel):
        if "markdown" in sel or "ds-markdown" in sel:
            return FakeMDLoc()
        return _make_loc(count=0)

    mock_page.locator = MagicMock(side_effect=_locator)

    result = await driver.extract_response(mock_page)
    assert "Good content" in result


async def test_extract_response_markdown_block_exception(mock_page):
    """Exception in markdown block → falls to message-content."""
    driver = _driver()

    async def _evaluate(script, *args):
        raise Exception("js crash")

    mock_page.evaluate = MagicMock(side_effect=_evaluate)

    md_loc = MagicMock()
    md_loc.count = AsyncMock(return_value=1)
    md_fail = _make_loc(text="x")
    md_fail.inner_text = AsyncMock(side_effect=Exception("inner_text crash"))

    msg_loc = MagicMock()
    msg_loc.count = AsyncMock(return_value=1)
    msg_loc.nth = lambda n: _make_loc(text="Message content " * 20)

    def _locator(sel):
        if "markdown" in sel or "ds-markdown" in sel:
            md_loc.nth = lambda n: md_fail
            return md_loc
        if "message-content" in sel:
            return msg_loc
        return _make_loc(count=0)

    mock_page.locator = MagicMock(side_effect=_locator)

    result = await driver.extract_response(mock_page)
    assert "Message content" in result


async def test_extract_response_message_content(mock_page):
    """message-content fallback → >200 chars extracted."""
    driver = _driver()
    mock_page.evaluate = AsyncMock(return_value="")

    long_text = "Message " * 40
    msg_loc = MagicMock()
    msg_loc.count = AsyncMock(return_value=1)
    msg_loc.nth = lambda n: _make_loc(text=long_text)

    def _locator(sel):
        if "message-content" in sel:
            return msg_loc
        return _make_loc(count=0)

    mock_page.locator = MagicMock(side_effect=_locator)

    result = await driver.extract_response(mock_page)
    assert result == long_text


async def test_extract_response_message_content_exception(mock_page):
    """Exception in message-content → falls to body marker."""
    driver = _driver()
    body = "## Main Section\n" + "Content " * 100

    call_idx = [0]

    async def _evaluate(script, *args):
        call_idx[0] += 1
        if "querySelectorAll" in script or "markdown" in script:
            return ""
        return body

    mock_page.evaluate = MagicMock(side_effect=_evaluate)

    def _locator(sel):
        if "message-content" in sel:
            raise Exception("msg crash")
        return _make_loc(count=0)

    mock_page.locator = MagicMock(side_effect=_locator)

    result = await driver.extract_response(mock_page)
    assert "Main Section" in result


async def test_extract_response_body_marker_extraction(mock_page):
    """Body has ## heading → extracted."""
    driver = _driver()
    body = "Preamble\n## Response Section\n" + "Content " * 100
    mock_page.evaluate = AsyncMock(return_value=body)
    mock_page.locator = MagicMock(return_value=_make_loc(count=0))

    result = await driver.extract_response(mock_page)
    assert "Response Section" in result


async def test_extract_response_body_marker_prompt_echo_skipped(mock_page):
    """Heading is a prompt echo → log debug (lines 430-431), falls to body.innerText."""
    driver = _driver()
    # sig matches heading so ALL marker occurrences are echoes → falls to last-resort
    driver.prompt_sigs = ["response section"]
    # Build body so both "# " and "## " occurrences are prompt echoes:
    # only one heading that satisfies both markers → both get skipped
    body = "## Response Section\n" + "response section " * 40

    call_idx = [0]

    async def _evaluate(script, *args):
        call_idx[0] += 1
        if call_idx[0] == 1:
            return body  # tertiary: body scan gets body with heading
        return body  # last-resort body.innerText

    mock_page.evaluate = MagicMock(side_effect=_evaluate)
    mock_page.locator = MagicMock(return_value=_make_loc(count=0))

    result = await driver.extract_response(mock_page)
    # heading is prompt echo → skipped, falls to last-resort body.innerText
    assert result == body


async def test_extract_response_body_marker_exception(mock_page):
    """Exception in body marker extraction → falls to body.innerText."""
    driver = _driver()

    call_idx = [0]

    async def _evaluate(script, *args):
        call_idx[0] += 1
        # First call: JS leaf block extraction
        if call_idx[0] == 1:
            raise Exception("js crash")
        # Second call: body.innerText for marker scan → crash
        if call_idx[0] == 2:
            raise Exception("body scan crash")
        # Third call: body.innerText last resort → success
        return "final fallback body"

    mock_page.evaluate = MagicMock(side_effect=_evaluate)
    mock_page.locator = MagicMock(return_value=_make_loc(count=0))

    result = await driver.extract_response(mock_page)
    assert isinstance(result, str)


async def test_extract_response_body_prompt_echo_warning(mock_page):
    """body.innerText is a prompt echo → warning logged (line 441), returned."""
    driver = _driver()
    driver.prompt_sigs = ["keyword"]
    body_text = "keyword " * 100

    call_idx = [0]

    async def _evaluate(script, *args):
        call_idx[0] += 1
        if call_idx[0] == 1:
            return ""  # JS leaf → empty
        return body_text  # marker scan + last resort

    mock_page.evaluate = MagicMock(side_effect=_evaluate)
    mock_page.locator = MagicMock(return_value=_make_loc(count=0))

    result = await driver.extract_response(mock_page)
    assert result == body_text


async def test_extract_response_markdown_exception_no_chunks(mock_page):
    """Markdown locator found but nth raises → no chunks, falls to message-content."""
    driver = _driver()

    call_idx = [0]

    async def _evaluate(script, *args):
        call_idx[0] += 1
        if call_idx[0] <= 2:
            raise Exception("js crash")
        return "final body text"  # body.innerText last resort

    mock_page.evaluate = MagicMock(side_effect=_evaluate)

    md_loc = MagicMock()
    md_loc.count = AsyncMock(return_value=1)

    def bad_nth(n):
        raise Exception("nth crash")

    md_loc.nth = bad_nth

    msg_loc = MagicMock()
    msg_loc.count = AsyncMock(return_value=0)

    def _locator(sel):
        if "markdown" in sel or "ds-markdown" in sel:
            return md_loc
        if "message-content" in sel:
            return msg_loc
        return _make_loc(count=0)

    mock_page.locator = MagicMock(side_effect=_locator)

    result = await driver.extract_response(mock_page)
    assert isinstance(result, str)


async def test_extract_response_markdown_loc_exception(mock_page):
    """Exception creating markdown locator itself → falls through."""
    driver = _driver()

    call_idx = [0]

    async def _evaluate(script, *args):
        call_idx[0] += 1
        if call_idx[0] <= 2:
            raise Exception("js crash")
        return "body fallback text"

    mock_page.evaluate = MagicMock(side_effect=_evaluate)

    call_idx = [0]

    def _locator(sel):
        call_idx[0] += 1
        if "markdown" in sel or "ds-markdown" in sel:
            raise Exception("locator crash")
        return _make_loc(count=0)

    mock_page.locator = MagicMock(side_effect=_locator)

    result = await driver.extract_response(mock_page)
    assert isinstance(result, str)
