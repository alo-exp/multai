"""DeepSeek platform automation."""

from __future__ import annotations

import logging

from playwright.async_api import Page

from .base import BasePlatform
from prompt_echo import is_prompt_echo

log = logging.getLogger(__name__)


class DeepSeek(BasePlatform):
    name = "deepseek"

    def __init__(self):
        super().__init__()
        self._no_stop_polls: int = 0  # Consecutive polls with no stop button visible

    async def check_rate_limit(self, page: Page) -> str | None:
        """Check for DeepSeek-specific rate limit indicators.

        DeepSeek under heavy load returns several different throttle messages
        depending on the specific failure mode (server overload vs. rate limit).
        """
        patterns = [
            "server is busy",
            "too many requests",
            "rate limit",
            "try again later",
            "service is temporarily unavailable",
            # Additional patterns observed under load
            "overloaded",
            "service unavailable",
            "We're experiencing high demand",
            "high traffic",
            "currently unavailable",
        ]
        for pattern in patterns:
            try:
                el = page.get_by_text(pattern, exact=False).first
                if await el.count() > 0 and await el.is_visible():
                    return pattern
            except Exception:
                pass
        return None

    async def configure_mode(self, page: Page, mode: str) -> str:
        """Enable DeepThink + Search toggles."""
        # DeepThink toggle
        try:
            dt_btn = page.get_by_text("DeepThink", exact=False).first
            if await dt_btn.count() > 0 and await dt_btn.is_visible():
                await dt_btn.click()
                await page.wait_for_timeout(300)
                log.info("[DeepSeek] Enabled DeepThink")
            else:
                for sel in ['button[aria-label*="DeepThink"]', '[class*="deep-think"]']:
                    btn = page.locator(sel).first
                    if await btn.count() > 0:
                        await btn.click()
                        await page.wait_for_timeout(300)
                        break
        except Exception as exc:
            log.warning(f"[DeepSeek] DeepThink toggle failed: {exc}")

        # Search toggle
        try:
            search_btn = page.get_by_text("Search", exact=True).first
            if await search_btn.count() > 0 and await search_btn.is_visible():
                await search_btn.click()
                await page.wait_for_timeout(300)
                log.info("[DeepSeek] Enabled Search")
            else:
                for sel in ['button[aria-label*="Search"]', '[class*="search"]']:
                    btn = page.locator(sel).first
                    if await btn.count() > 0:
                        await btn.click()
                        await page.wait_for_timeout(300)
                        break
        except Exception as exc:
            log.warning(f"[DeepSeek] Search toggle failed: {exc}")

        return "DeepThink + Search"

    async def inject_prompt(self, page: Page, prompt: str) -> None:
        """Inject via React-compatible approach: fill + React event trigger.

        DeepSeek uses a React textarea. We use fill() + native event
        dispatching to ensure React picks up the state change.
        """
        textarea = page.locator("textarea").first
        if await textarea.count() == 0:
            raise RuntimeError("No textarea found on DeepSeek")

        await textarea.click()
        await page.wait_for_timeout(300)

        # Use nativeInputValueSetter to bypass React's synthetic event system
        # and trigger a proper React-visible state change
        await page.evaluate("""(prompt) => {
            const textarea = document.querySelector('textarea');
            if (!textarea) throw new Error('No textarea');
            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                window.HTMLTextAreaElement.prototype, 'value'
            ).set;
            nativeInputValueSetter.call(textarea, prompt);
            textarea.dispatchEvent(new Event('input', { bubbles: true }));
            textarea.dispatchEvent(new Event('change', { bubbles: true }));
        }""", prompt)
        log.info(f"[DeepSeek] Injected {len(prompt)} chars via nativeInputValueSetter")

    async def click_send(self, page: Page) -> None:
        """Click the send icon button (DeepSeek uses div[role='button'] not <button>)."""
        # DeepSeek's send button is the rightmost ds-icon-button near the textarea
        try:
            send_btns = page.locator('[role="button"].ds-icon-button')
            count = await send_btns.count()
            if count > 0:
                # Click the last icon button (rightmost = send)
                last_btn = send_btns.nth(count - 1)
                if await last_btn.is_visible():
                    await last_btn.click()
                    log.info("[DeepSeek] Clicked send button (ds-icon-button)")
                    return
        except Exception as exc:
            log.debug(f"[DeepSeek] ds-icon-button click failed: {exc}")

        # Fallback: try role="button" near the textarea
        try:
            send_btns = page.locator('div[role="button"]')
            count = await send_btns.count()
            for i in range(count - 1, max(count - 5, -1), -1):
                btn = send_btns.nth(i)
                if await btn.is_visible():
                    box = await btn.bounding_box()
                    if box and box["width"] < 50 and box["height"] < 50:
                        await btn.click()
                        log.info(f"[DeepSeek] Clicked send button (role=button #{i})")
                        return
        except Exception as exc:
            log.debug(f"[DeepSeek] role=button fallback failed: {exc}")

        # Last resort: press Enter
        log.warning("[DeepSeek] No send button found, pressing Enter")
        await page.keyboard.press("Enter")

    async def completion_check(self, page: Page) -> bool:
        """Check for completion — multi-signal with stable-state fallback.

        DeepSeek uses div[role='button'] for its stop button, not <button>.
        We must check both.
        """
        # 1. Check for stop button (still generating) — both <button> and div[role="button"]
        has_stop = False
        for sel in [
            'button:has-text("Stop")',
            'button[aria-label*="Stop"]',
            '[role="button"]:has-text("Stop")',
        ]:
            try:
                stop = page.locator(sel).first
                if await stop.count() > 0 and await stop.is_visible():
                    has_stop = True
                    break
            except Exception:
                pass

        # Also check for animated "thinking" indicators
        if not has_stop:
            try:
                # DeepSeek shows a pulsing/animated indicator while thinking
                thinking = page.locator('[class*="thinking"], [class*="loading"], [class*="typing"]').first
                if await thinking.count() > 0 and await thinking.is_visible():
                    has_stop = True
            except Exception:
                pass

        if has_stop:
            self._no_stop_polls = 0
            return False

        self._no_stop_polls += 1

        # 2. Check if we're still on the homepage (no conversation started)
        current_url = page.url
        if current_url.rstrip("/") == "https://chat.deepseek.com":
            # Still on homepage — prompt likely wasn't sent
            if self._no_stop_polls < 6:
                return False  # Wait longer
            log.warning("[DeepSeek] Still on homepage after 60s — prompt may not have been sent")
            return True  # Give up

        # 3. Check for copy/regenerate buttons (strongest completion signal)
        try:
            for sel in ['button:has-text("Copy")', 'button:has-text("Regenerate")',
                        '[role="button"]:has-text("Copy")', '[role="button"]:has-text("Regenerate")']:
                btn = page.locator(sel).first
                if await btn.count() > 0 and await btn.is_visible():
                    return True
        except Exception:
            pass

        # 4. Check for substantial response content (NOT thinking output)
        # DeepThink mode renders thinking text in markdown-body while still
        # generating. Only declare complete if content is very large (> 3000),
        # indicating the actual response (not just CoT) has appeared.
        try:
            md = page.locator('.markdown-body, [class*="ds-markdown"]')
            count = await md.count()
            if count > 0:
                last = md.nth(count - 1)
                length = await last.evaluate("el => el.innerText.length")
                if length > 3000:
                    return True
        except Exception:
            pass

        # 5. Stable-state: no stop button for 6 consecutive polls (~60s)
        if self._no_stop_polls >= 6:
            log.info("[DeepSeek] No stop button for 6 polls — declaring complete")
            return True

        return False

    async def extract_response(self, page: Page) -> str:
        """Extract AI response from the last assistant message container."""
        # Primary: use JS to collect ONLY response markdown blocks.
        # Two problems in DeepThink mode:
        # 1. Thinking-chain blocks must be excluded (parent has "think" class).
        # 2. The selector '.markdown-body, [class*="ds-markdown"]' can match both
        #    a parent and its child — causing duplicated text. Fix: take only
        #    LEAF blocks (those that contain no other matching descendant).
        try:
            combined = await page.evaluate("""() => {
                const sel = '.markdown-body, [class*="ds-markdown"]';
                const blocks = [...document.querySelectorAll(sel)];

                // Keep only leaf blocks (no matching descendants)
                const leafBlocks = blocks.filter(el => !el.querySelector(sel));

                // Exclude blocks inside thinking/reasoning containers
                const responseBlocks = leafBlocks.filter(el => {
                    let parent = el.parentElement;
                    while (parent && parent !== document.body) {
                        const cls = (parent.className || '').toLowerCase();
                        if (cls.includes('think') || cls.includes('reasoning') ||
                            cls.includes('chain-of-thought')) {
                            return false;
                        }
                        parent = parent.parentElement;
                    }
                    return true;
                });

                return responseBlocks
                    .map(el => el.innerText.trim())
                    .filter(t => t.length > 50)
                    .join('\\n\\n');
            }""")
            if combined and len(combined) > 200:
                log.info(f"[DeepSeek] Extracted {len(combined)} chars via JS leaf response blocks")
                return combined
        except Exception as exc:
            log.debug(f"[DeepSeek] JS response-only extraction failed: {exc}")

        # Fallback: collect all markdown blocks, skip very long thinking chains,
        # and concatenate the rest.
        try:
            md_blocks = page.locator('.markdown-body, [class*="ds-markdown"]')
            count = await md_blocks.count()
            if count > 0:
                chunks: list[str] = []
                for i in range(count):
                    try:
                        text = await md_blocks.nth(i).inner_text()
                        text = text.strip()
                        if len(text) < 50 or len(text) > 15000:
                            continue
                        chunks.append(text)
                    except Exception:
                        continue

                if chunks:
                    combined = "\n\n".join(chunks)
                    log.info(f"[DeepSeek] Extracted {len(combined)} chars via {len(chunks)} fallback markdown block(s)")
                    return combined
        except Exception as exc:
            log.debug(f"[DeepSeek] markdown extraction failed: {exc}")

        # Secondary: try the last message-content div
        try:
            msgs = page.locator('[class*="message-content"]')
            count = await msgs.count()
            if count > 0:
                last_msg = msgs.nth(count - 1)
                text = await last_msg.inner_text()
                if len(text) > 200:
                    log.info(f"[DeepSeek] Extracted {len(text)} chars via message-content")
                    return text
        except Exception as exc:
            log.debug(f"[DeepSeek] message-content extraction failed: {exc}")

        # Tertiary: find generic Markdown heading markers in body text (skip sidebar).
        # Scan ALL occurrences and pick the LAST one that is not a prompt echo.
        # (rfind alone is insufficient — if the prompt's last heading happens to be
        #  the final marker on the page, we'd return the echoed prompt.)
        try:
            text = await page.evaluate("document.body.innerText")
            if text and len(text) > 500:
                for marker in ["# ", "## "]:
                    positions = []
                    start = 0
                    while True:
                        idx = text.find(marker, start)
                        if idx < 0:
                            break
                        positions.append(idx)
                        start = idx + 1
                    for idx in reversed(positions):
                        # Find the preceding newline to capture the full heading line
                        line_start = text.rfind("\n", max(0, idx - 200), idx)
                        if line_start < 0:
                            line_start = idx
                        candidate = text[line_start:].strip()
                        if is_prompt_echo(candidate, self.prompt_sigs):
                            log.debug(f"[DeepSeek] Skipping prompt echo at marker '{marker}' pos {idx}")
                            continue
                        if len(candidate) > 500:
                            log.info(f"[DeepSeek] Extracted {len(candidate)} chars from marker '{marker}' at pos {idx}")
                            return candidate
        except Exception as exc:
            log.debug(f"[DeepSeek] marker extraction failed: {exc}")

        # Last resort: full body text (with prompt-echo guard)
        text = await page.evaluate("document.body.innerText")
        if is_prompt_echo(text, self.prompt_sigs):
            log.warning("[DeepSeek] body.innerText appears to be a prompt echo — returning as-is (no better option)")
        log.info(f"[DeepSeek] Extracted {len(text)} chars via body.innerText")
        return text
