"""Microsoft Copilot platform automation."""

from __future__ import annotations

import logging

from playwright.async_api import Page

from .base import BasePlatform

log = logging.getLogger(__name__)


class Copilot(BasePlatform):
    name = "copilot"

    def __init__(self):
        super().__init__()
        self._no_stop_polls: int = 0     # Consecutive polls with no stop button visible
        self._last_response_len: int = 0  # Track response length between polls to detect growth

    async def check_rate_limit(self, page: Page) -> str | None:
        """Check for Copilot-specific rate limit indicators."""
        patterns = [
            "conversation limit",
            "daily limit",
            "limit reached",
            "too many",
            "try again",
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
        """
        Enable Think deeper mode; optionally Start deep research (DEEP).
        HAZARD: Avoid clicking near the microphone/voice button.
        """
        label_parts = []

        # Think deeper mode — hover mode selector to reveal dropdown
        try:
            # Look for mode selector button near the composer
            mode_btn = page.locator('[aria-label*="mode"], [aria-label*="Smart"]').first
            if await mode_btn.count() == 0:
                mode_btn = page.get_by_text("Smart", exact=False).first
            if await mode_btn.count() > 0 and await mode_btn.is_visible():
                await mode_btn.hover()
                await page.wait_for_timeout(500)

                think_deeper = page.get_by_text("Think deeper", exact=False).first
                if await think_deeper.count() > 0:
                    await think_deeper.click()
                    await page.wait_for_timeout(500)
                    log.info("[Copilot] Selected Think deeper mode")
                    label_parts.append("Think deeper")
        except Exception as exc:
            log.warning(f"[Copilot] Think deeper selection failed: {exc}")

        # DEEP mode: Start deep research
        if mode == "DEEP":
            try:
                # Look for + button or attach button
                plus_btn = page.locator('button[aria-label*="Add"], button[aria-label*="attach"]').first
                if await plus_btn.count() == 0:
                    plus_btn = page.get_by_text("+").first
                if await plus_btn.count() > 0 and await plus_btn.is_visible():
                    await plus_btn.click()
                    await page.wait_for_timeout(500)

                    dr = page.get_by_text("Start deep research", exact=False).first
                    if await dr.count() > 0:
                        await dr.click()
                        await page.wait_for_timeout(500)
                        log.info("[Copilot] Enabled deep research")
                        label_parts.append("Deep Research")
            except Exception as exc:
                log.warning(f"[Copilot] Deep research enablement failed: {exc}")

        return " + ".join(label_parts) if label_parts else "Default"

    async def inject_prompt(self, page: Page, prompt: str) -> None:
        """Inject via textarea (Copilot uses textarea, not contenteditable)."""
        # Find the visible textarea with the "Message Copilot" placeholder
        textarea = page.locator('textarea[placeholder*="Message"]').first
        if await textarea.count() == 0:
            # Fallback: any visible textarea
            textarea = page.locator('textarea:not([aria-hidden="true"])').first
        if await textarea.count() == 0:
            textarea = page.locator('textarea').first

        if await textarea.count() == 0:
            raise RuntimeError("No textarea found on Copilot")

        await textarea.click()
        await page.wait_for_timeout(300)
        await textarea.fill(prompt)
        # Dispatch events to ensure React picks up the state change
        await textarea.dispatch_event("input")
        log.info(f"[Copilot] Filled textarea with {len(prompt)} chars")

    async def click_send(self, page: Page) -> None:
        """
        Click send button.
        HAZARD: Copilot has a microphone button adjacent to send — avoid it.
        """
        # Try specific selectors that avoid the microphone button
        for selector in [
            'button[aria-label*="Send"]',
            'button[aria-label*="Submit"]',
            'button[data-testid*="send"]',
        ]:
            btn = page.locator(selector).first
            if await btn.count() > 0 and await btn.is_visible():
                # Verify this is NOT the microphone button
                aria = await btn.get_attribute("aria-label") or ""
                if "voice" in aria.lower() or "microphone" in aria.lower() or "mic" in aria.lower():
                    continue
                await btn.click()
                return

        # Fallback: find by role, but verify not microphone
        for text in ["Send", "Submit"]:
            btn = page.get_by_role("button", name=text).first
            if await btn.count() > 0 and await btn.is_visible():
                aria = await btn.get_attribute("aria-label") or ""
                if "voice" in aria.lower() or "microphone" in aria.lower() or "mic" in aria.lower():
                    continue
                await btn.click()
                return

        # Agent fallback: vision-based button finding (avoids microphone hazard)
        try:
            await self._agent_fallback(
                page, "click_send",
                RuntimeError("No send button found via selectors"),
                f"On {self.display_name}: find and click the SEND button (NOT the microphone "
                f"button). The send button submits the typed message.",
            )
            return
        except Exception:
            pass

        await page.keyboard.press("Enter")

    async def post_send(self, page: Page, mode: str) -> None:
        """
        After sending, verify submission and click 'Start research' if plan appears.
        """
        await page.wait_for_timeout(3000)

        # Verify URL changed (indicates successful submission)
        current_url = page.url
        if "copilot.microsoft.com" in current_url and "/chats/" not in current_url:
            log.warning("[Copilot] URL did not change — prompt may not have been sent")
            # Retry send
            await self.click_send(page)
            await page.wait_for_timeout(3000)

        # DEEP mode: look for "Start research" button (research plan appears before crawling)
        if mode == "DEEP":
            for _ in range(6):  # Check for 30 seconds
                try:
                    start_btn = page.get_by_text("Start research", exact=False).first
                    if await start_btn.count() > 0 and await start_btn.is_visible():
                        await start_btn.click()
                        log.info("[Copilot] Clicked 'Start research' button")
                        return
                except Exception:
                    pass
                await page.wait_for_timeout(5000)
            log.warning("[Copilot] 'Start research' button not found after 30s — research may not have started")

    async def completion_check(self, page: Page) -> bool:
        """Check for completion — multi-signal with stable-state fallback.

        Copilot has a "Thinking…" phase before generating. During this phase,
        there's no stop button but the model IS still processing. We must detect
        this and NOT fire stable-state prematurely.
        """
        # 1. Check for stop/cancel button (still generating)
        has_stop = False
        for sel in ['button:has-text("Stop")', 'button:has-text("Cancel")']:
            try:
                stop = page.locator(sel).first
                if await stop.count() > 0 and await stop.is_visible():
                    has_stop = True
                    break
            except Exception:
                pass

        # 2. Check for Copilot's thinking/typing indicator via CSS class selectors
        #    (NOT generic text — "Thinking", "Searching" etc. match words in the
        #    echoed prompt, causing infinite loops)
        is_thinking = False
        try:
            for sel in [
                '[class*="typing-indicator"]',
                '[class*="thinking"]',
                '[class*="spinner"]',
                '[class*="loading-dots"]',
                '[class*="progress"]',
                '[aria-label*="thinking"]',
                '[aria-label*="generating"]',
            ]:
                indicator = page.locator(sel).first
                if await indicator.count() > 0 and await indicator.is_visible():
                    is_thinking = True
                    log.debug(f"[Copilot] Thinking indicator: {sel}")
                    break
        except Exception:
            pass

        # Also check: prompt was sent (URL has /chats/) but no "Copilot said" yet
        if not is_thinking and not has_stop:
            try:
                if "/chats/" in page.url:
                    copilot_replied = await page.evaluate(
                        "document.body.innerText.includes('Copilot said')"
                    )
                    if not copilot_replied:
                        is_thinking = True
                        log.debug("[Copilot] Prompt sent, no response yet — still processing")
            except Exception:
                pass

        if has_stop or is_thinking:
            self._no_stop_polls = 0
            return False

        self._no_stop_polls += 1

        # 3. Track page text growth — if text is still growing, Copilot is
        # still streaming (even without a visible stop button).
        # Try "Copilot said" section first; fall back to total page text length.
        try:
            response_len = await page.evaluate("""
                (() => {
                    const body = document.body.innerText;
                    const copilotIdx = body.indexOf('Copilot said');
                    if (copilotIdx >= 0) {
                        return body.substring(copilotIdx + 12).length;
                    }
                    // Fallback: track total page text length
                    return body.length;
                })()
            """)
            if response_len > self._last_response_len:
                # Text is still growing — reset stable-state counter
                log.debug(f"[Copilot] Page text growing: {self._last_response_len} → {response_len}")
                self._last_response_len = response_len
                self._no_stop_polls = 0
                return False
            else:
                log.debug(f"[Copilot] Page text stable at {response_len} chars (poll {self._no_stop_polls})")
        except Exception:
            pass

        # 4. Stable-state: page text stopped growing for 3 consecutive polls (~30s)
        if self._no_stop_polls >= 3 and self._last_response_len > 5000:
            log.info(f"[Copilot] Page text stable at {self._last_response_len} chars for {self._no_stop_polls} polls — declaring complete")
            return True

        # Extended stable-state: no activity for 8 polls (~80s)
        if self._no_stop_polls >= 8:
            log.info("[Copilot] No activity for 8 polls — declaring complete")
            return True

        return False

    async def extract_response(self, page: Page) -> str:
        """Extract AI response — find 'Copilot said' marker and extract after it."""
        # Primary: extract text after "Copilot said" marker (skip echoed prompt)
        try:
            text = await page.evaluate("""
                (() => {
                    const body = document.body.innerText;
                    const marker = 'Copilot said';
                    const idx = body.indexOf(marker);
                    if (idx >= 0) {
                        let response = body.substring(idx + marker.length).trim();
                        // Remove "See my thinking" prefix if present
                        if (response.startsWith('See my thinking')) {
                            response = response.substring('See my thinking'.length).trim();
                        }
                        return response;
                    }
                    return '';
                })()
            """)
            if text and len(text) > 200:
                log.info(f"[Copilot] Extracted {len(text)} chars via 'Copilot said' marker")
                return text
        except Exception as exc:
            log.debug(f"[Copilot] 'Copilot said' extraction failed: {exc}")

        # Secondary: find generic Markdown heading markers in body text
        try:
            text = await page.evaluate("document.body.innerText")
            if text:
                for marker in ["# ", "## "]:
                    idx = text.find(marker)
                    if idx > 0:
                        report = text[idx:]
                        if len(report) > 200:
                            log.info(f"[Copilot] Extracted {len(report)} chars from marker '{marker}'")
                            return report
        except Exception as exc:
            log.debug(f"[Copilot] Marker extraction failed: {exc}")

        # Last resort: full body text
        text = await page.evaluate("document.body.innerText")
        log.info(f"[Copilot] Extracted {len(text)} chars via body.innerText")
        return text
