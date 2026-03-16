"""Perplexity AI platform automation."""

from __future__ import annotations

import logging

from playwright.async_api import Page

from .base import BasePlatform

log = logging.getLogger(__name__)


class Perplexity(BasePlatform):
    name = "perplexity"

    def __init__(self):
        super().__init__()
        self._no_stop_polls: int = 0  # Consecutive polls with no stop button visible
        self._last_page_len: int = 0  # Track page text length between polls for growth detection

    async def check_rate_limit(self, page: Page) -> str | None:
        """Check for Perplexity-specific rate limit indicators."""
        patterns = [
            "Pro search limit",
            "limit reached",
            "upgrade to Pro",
            "daily limit",
            "out of Pro searches",
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
        """Select Sonar model; optionally enable Deep Research toggle."""
        # Click model picker
        try:
            model_btn = page.locator('button:has-text("Model")').first
            if await model_btn.count() == 0:
                # Try alternative selector
                model_btn = page.locator('[data-testid="model-selector"]').first
            if await model_btn.count() > 0 and await model_btn.is_visible():
                await model_btn.click()
                await page.wait_for_timeout(500)

                # Select Sonar
                sonar = page.get_by_text("Sonar", exact=False).first
                if await sonar.count() > 0:
                    await sonar.click()
                    await page.wait_for_timeout(500)
                    log.info("[Perplexity] Selected Sonar model")
        except Exception as exc:
            log.warning(f"[Perplexity] Model selection failed: {exc} — proceeding with default")

        # DEEP mode: try to enable Deep Research toggle
        if mode == "DEEP":
            try:
                deep_toggle = page.get_by_text("Deep Research", exact=False).first
                if await deep_toggle.count() > 0 and await deep_toggle.is_visible():
                    await deep_toggle.click()
                    log.info("[Perplexity] Enabled Deep Research")
            except Exception:
                log.info("[Perplexity] Deep Research toggle not found — proceeding without")

        return "Sonar" + (" + Deep Research" if mode == "DEEP" else "")

    async def inject_prompt(self, page: Page, prompt: str) -> None:
        """Inject via contenteditable or textarea."""
        # Perplexity uses contenteditable or textarea depending on version
        ce = page.locator('div[contenteditable="true"]').first
        ta = page.locator('textarea[placeholder]').first

        if await ce.count() > 0 and await ce.is_visible():
            await self._inject_exec_command(page, prompt)
        elif await ta.count() > 0 and await ta.is_visible():
            await ta.click()
            await ta.fill(prompt)
            log.info(f"[Perplexity] Filled textarea with {len(prompt)} chars")
        else:
            raise RuntimeError("No input element found on Perplexity")

    async def click_send(self, page: Page) -> None:
        """Click send button or press Enter."""
        # Try finding send/search button
        for selector in [
            'button[aria-label*="Submit"]',
            'button[aria-label*="Send"]',
            'button[aria-label*="Search"]',
            'button[aria-label*="Ask"]',
        ]:
            btn = page.locator(selector).first
            if await btn.count() > 0 and await btn.is_visible():
                await btn.click()
                return

        # Fallback: find by role
        for text in ["Submit", "Send", "Search", "Ask"]:
            btn = page.get_by_role("button", name=text).first
            if await btn.count() > 0 and await btn.is_visible():
                await btn.click()
                return

        # Agent fallback: vision-based button finding before Enter
        try:
            await self._agent_fallback(
                page, "click_send",
                RuntimeError("No send button found via selectors"),
                f"On {self.display_name}: find and click the send/submit button "
                f"to send the message.",
            )
            return
        except Exception:
            pass

        # Last resort: press Enter (Perplexity submits on Enter)
        await page.keyboard.press("Enter")

    async def completion_check(self, page: Page) -> bool:
        """Check if response is complete — growth-based detection.

        Perplexity shows the prompt text on the page immediately, so we
        cannot use static length thresholds. Instead we track whether page
        text is still growing between polls.
        """
        # 1. Look for stop/cancel button (indicates still generating)
        has_stop = False
        for sel in ['button:has-text("Stop")', 'button:has-text("Cancel")']:
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

        # 2. Track page text growth — if still growing, still generating
        try:
            page_len = await page.evaluate("document.body.innerText.length")
            if page_len > self._last_page_len:
                log.debug(f"[Perplexity] Page text growing: {self._last_page_len} → {page_len}")
                self._last_page_len = page_len
                self._no_stop_polls = 0
                return False
        except Exception:
            pass

        # 3. Check for "Sources" section + substantial prose content
        # Citations can appear while Perplexity is still generating — require
        # both citations AND substantial .prose content (> 3000 chars)
        try:
            sources = page.locator('[class*="source"], [class*="citation"]')
            source_count = await sources.count()
            if source_count >= 2:
                prose_len = 0
                try:
                    prose = page.locator('.prose, [class*="prose"]').first
                    if await prose.count() > 0:
                        prose_len = await prose.evaluate("el => el.innerText.length")
                except Exception:
                    pass
                if prose_len > 3000:
                    log.info(f"[Perplexity] {source_count} citations + {prose_len} chars prose — declaring complete")
                    return True
                else:
                    log.debug(f"[Perplexity] {source_count} citations but prose only {prose_len} chars — waiting")
        except Exception:
            pass

        # 4. Stable-state: page text stopped growing for 3 consecutive polls (~30s)
        if self._no_stop_polls >= 3 and self._last_page_len > 5000:
            log.info(f"[Perplexity] Page text stable at {self._last_page_len} chars for {self._no_stop_polls} polls — declaring complete")
            return True

        # Extended stable-state: 6 polls (~60s) regardless
        if self._no_stop_polls >= 6:
            log.info("[Perplexity] No activity for 6 polls — declaring complete")
            return True

        return False

    async def extract_response(self, page: Page) -> str:
        """Extract from .prose container or full page text."""
        # Primary: .prose selector
        try:
            prose = page.locator('.prose').first
            if await prose.count() > 0:
                text = await prose.inner_text()
                if len(text) > 500:
                    log.info(f"[Perplexity] Extracted {len(text)} chars via .prose")
                    return text
        except Exception as exc:
            log.warning(f"[Perplexity] .prose extraction failed: {exc}")

        # Fallback: try [class*="prose"]
        try:
            prose_alt = page.locator('[class*="prose"]').first
            if await prose_alt.count() > 0:
                text = await prose_alt.inner_text()
                if len(text) > 500:
                    log.info(f"[Perplexity] Extracted {len(text)} chars via [class*=prose]")
                    return text
        except Exception:
            pass

        # Tertiary: try main content area (exclude sidebar/history)
        try:
            text = await page.evaluate("""
                (() => {
                    const main = document.querySelector('main')
                               || document.querySelector('[class*="answer"]')
                               || document.querySelector('[class*="result"]');
                    if (main) return main.innerText;
                    return '';
                })()
            """)
            if text and len(text) > 200:
                log.info(f"[Perplexity] Extracted {len(text)} chars via main container")
                return text
        except Exception:
            pass

        # Last resort: full page inner text
        text = await page.evaluate("document.body.innerText")
        log.info(f"[Perplexity] Extracted {len(text)} chars via body.innerText")
        return text
