"""DeepSeek platform automation."""

from __future__ import annotations

import logging

from playwright.async_api import Page

from .base import BasePlatform

log = logging.getLogger(__name__)


class DeepSeek(BasePlatform):
    name = "deepseek"

    def __init__(self):
        super().__init__()
        self._no_stop_polls: int = 0  # Consecutive polls with no stop button visible

    async def check_rate_limit(self, page: Page) -> str | None:
        """Check for DeepSeek-specific rate limit indicators."""
        patterns = [
            "server is busy",
            "too many requests",
            "rate limit",
            "try again later",
            "service is temporarily unavailable",
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
        # Primary: try to find the last assistant message container
        try:
            # DeepSeek uses markdown-body or ds-markdown for AI responses
            md_blocks = page.locator('.markdown-body, [class*="ds-markdown"]')
            count = await md_blocks.count()
            if count > 0:
                last_block = md_blocks.nth(count - 1)
                text = await last_block.inner_text()
                if len(text) > 200:
                    log.info(f"[DeepSeek] Extracted {len(text)} chars via markdown container")
                    return text
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

        # Tertiary: find generic Markdown heading markers in body text (skip sidebar)
        # Use rfind (LAST occurrence) because the sidebar at the top of the page
        # contains chat history titles. The actual AI response is near the bottom.
        try:
            text = await page.evaluate("document.body.innerText")
            if text:
                for marker in ["# ", "## "]:
                    idx = text.rfind(marker)  # Last occurrence (skip sidebar)
                    if idx > 0:
                        start = text.rfind("\n", max(0, idx - 200), idx)
                        if start < 0:
                            start = idx
                        report = text[start:].strip()
                        if len(report) > 500:
                            log.info(f"[DeepSeek] Extracted {len(report)} chars from marker '{marker}' at pos {idx}")
                            return report
        except Exception as exc:
            log.debug(f"[DeepSeek] marker extraction failed: {exc}")

        # Last resort: full body text
        text = await page.evaluate("document.body.innerText")
        log.info(f"[DeepSeek] Extracted {len(text)} chars via body.innerText")
        return text
