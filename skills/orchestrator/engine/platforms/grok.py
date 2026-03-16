"""Grok platform automation."""

from __future__ import annotations

import logging

from playwright.async_api import Page

from .base import BasePlatform

log = logging.getLogger(__name__)


class Grok(BasePlatform):
    name = "grok"

    def __init__(self):
        super().__init__()
        self._no_stop_polls: int = 0  # Consecutive polls with no stop button visible

    async def check_rate_limit(self, page: Page) -> str | None:
        """Check for Grok-specific rate limit indicators."""
        patterns = [
            "Message limit reached",
            "try again later",
            "rate limit",
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
                log.info("[Grok] Enabled DeepThink")
            else:
                # Try toolbar buttons
                for sel in ['button[aria-label*="DeepThink"]', 'button[aria-label*="Think"]']:
                    btn = page.locator(sel).first
                    if await btn.count() > 0:
                        await btn.click()
                        await page.wait_for_timeout(300)
                        log.info("[Grok] Enabled DeepThink via aria-label")
                        break
        except Exception as exc:
            log.warning(f"[Grok] DeepThink toggle failed: {exc}")

        # Search toggle
        try:
            search_btn = page.get_by_text("Search", exact=True).first
            if await search_btn.count() > 0 and await search_btn.is_visible():
                await search_btn.click()
                await page.wait_for_timeout(300)
                log.info("[Grok] Enabled Search")
            else:
                for sel in ['button[aria-label*="Search"]', 'button[aria-label*="search"]']:
                    btn = page.locator(sel).first
                    if await btn.count() > 0:
                        await btn.click()
                        await page.wait_for_timeout(300)
                        log.info("[Grok] Enabled Search via aria-label")
                        break
        except Exception as exc:
            log.warning(f"[Grok] Search toggle failed: {exc}")

        return "DeepThink + Search"

    async def inject_prompt(self, page: Page, prompt: str) -> None:
        """
        Grok uses a ProseMirror/tiptap contenteditable div (NOT textarea).
        Use execCommand for reliable injection. Falls back to physical typing.
        """
        # Primary: contenteditable div (ProseMirror editor)
        ce = page.locator('div[contenteditable="true"]').first
        if await ce.count() > 0 and await ce.is_visible():
            length = await self._inject_exec_command(page, prompt)
            log.info(f"[Grok] Injected {length} chars via execCommand (contenteditable)")
            return

        # Fallback: try visible textarea (not the hidden one)
        textarea = page.locator('textarea:not([aria-hidden="true"])').first
        if await textarea.count() > 0 and await textarea.is_visible():
            await textarea.click()
            await page.wait_for_timeout(500)
            await textarea.type(prompt, delay=5)
            log.info(f"[Grok] Typed {len(prompt)} chars physically (textarea)")
            return

        raise RuntimeError("No visible input element found on Grok")

    async def completion_check(self, page: Page) -> bool:
        """Check for completion — multi-signal with stable-state fallback.
        Rate limit check now handled by base class _poll_completion().
        """
        # 1. Check for stop button (still generating)
        has_stop = False
        for sel in ['button:has-text("Stop")', 'button[aria-label*="Stop"]']:
            try:
                stop = page.locator(sel).first
                if await stop.count() > 0 and await stop.is_visible():
                    has_stop = True
                    break
            except Exception:
                pass

        if has_stop:
            self._no_stop_polls = 0
            return False

        self._no_stop_polls += 1

        # 2. Check for response message containers (at least 2 = user + AI)
        try:
            messages = page.locator('[data-testid*="message"], [class*="message"]')
            count = await messages.count()
            if count >= 2:
                return True
        except Exception:
            pass

        # 3. Stable-state: no stop button for 3 consecutive polls (~30s)
        if self._no_stop_polls >= 3:
            log.info("[Grok] No stop button for 3 polls — declaring complete")
            return True

        return False

    async def extract_response(self, page: Page) -> str:
        """Extract AI response — try specific containers before body fallback."""
        # Check for rate limit message
        try:
            rate_msg = page.get_by_text("Message limit reached", exact=False).first
            if await rate_msg.count() > 0 and await rate_msg.is_visible():
                return "[RATE LIMITED] Message limit reached on Grok."
        except Exception:
            pass

        # Primary: try to find AI response in message containers
        try:
            # Grok renders responses in message blocks — get the last one
            msgs = page.locator('[class*="message-content"], [class*="response-text"], [class*="markdown"]')
            count = await msgs.count()
            if count > 0:
                last_msg = msgs.nth(count - 1)
                text = await last_msg.inner_text()
                if len(text) > 200:
                    log.info(f"[Grok] Extracted {len(text)} chars via message container")
                    return text
        except Exception as exc:
            log.debug(f"[Grok] Message container extraction failed: {exc}")

        # Secondary: try main content area (exclude sidebar)
        try:
            text = await page.evaluate("""
                (() => {
                    const main = document.querySelector('main')
                               || document.querySelector('[class*="chat-container"]')
                               || document.querySelector('[class*="conversation"]');
                    if (main) return main.innerText;
                    return document.body.innerText;
                })()
            """)
            if text and len(text) > 200:
                log.info(f"[Grok] Extracted {len(text)} chars via main container")
                return text
        except Exception as exc:
            log.debug(f"[Grok] Main container extraction failed: {exc}")

        # Last resort: full body text
        text = await page.evaluate("document.body.innerText")
        log.info(f"[Grok] Extracted {len(text)} chars via body.innerText")
        return text
