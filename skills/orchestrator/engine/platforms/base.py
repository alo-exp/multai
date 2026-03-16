"""Base class for all platform automation modules."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from playwright.async_api import Page

from config import (
    INJECTION_METHODS,
    PLATFORM_DISPLAY_NAMES,
    PLATFORM_URLS,
    POLL_INTERVAL,
    STATUS_COMPLETE,
    STATUS_FAILED,
    STATUS_PARTIAL,
    STATUS_RATE_LIMITED,
    STATUS_TIMEOUT,
    TIMEOUTS,
)

log = logging.getLogger(__name__)


@dataclass
class PlatformResult:
    """Result returned by each platform run."""
    platform: str
    display_name: str
    status: str
    chars: int = 0
    file: str = ""
    mode_used: str = ""
    error: str = ""
    duration_s: float = 0.0


class BasePlatform:
    """
    Base class for platform automation.

    Subclasses must implement:
        - configure_mode(page, mode)
        - completion_check(page) -> bool
        - extract_response(page) -> str

    Optional overrides:
        - inject_prompt(page, prompt)   — default uses INJECTION_METHODS config
        - click_send(page)              — default finds send button by text
        - post_send(page)               — hook for actions after send (e.g., Gemini "Start research")
    """

    name: str = ""                 # e.g. "perplexity"
    url: str = ""                  # e.g. "https://www.perplexity.ai"
    display_name: str = ""         # e.g. "Perplexity"

    def __init__(self):
        self.url = PLATFORM_URLS.get(self.name, "")
        self.display_name = PLATFORM_DISPLAY_NAMES.get(self.name, self.name)
        self.agent_manager = None           # Set by orchestrator to AgentFallbackManager instance
        self.prompt_sigs: list[str] = []    # Set by orchestrator for prompt-echo detection

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def run(
        self,
        page: Page,
        prompt: str,
        mode: str,
        output_dir: str,
    ) -> PlatformResult:
        """Execute the full platform lifecycle: navigate → configure → inject → send → poll → extract → save."""
        t0 = time.monotonic()
        timeout = TIMEOUTS.get(self.name)
        if timeout is None:
            log.warning(f"[{self.display_name}] No timeout config found, using defaults")
            from config import TimeoutConfig
            timeout = TimeoutConfig()
        max_wait = timeout.deep if mode == "DEEP" else timeout.regular

        try:
            # 1. Navigate
            log.info(f"[{self.display_name}] Navigating to {self.url}")
            await page.goto(self.url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)  # Let JS frameworks initialise

            # 1b. Rate limit pre-check (before any interaction)
            rate_msg = await self.check_rate_limit(page)
            if rate_msg:
                log.warning(f"[{self.display_name}] Rate limited on page load: {rate_msg}")
                return PlatformResult(
                    platform=self.name, display_name=self.display_name,
                    status=STATUS_RATE_LIMITED, mode_used="",
                    error=f"Rate limited: {rate_msg}",
                    duration_s=time.monotonic() - t0,
                )

            # 2. Configure mode
            log.info(f"[{self.display_name}] Configuring mode: {mode}")
            try:
                mode_label = await self.configure_mode(page, mode)
            except Exception as exc:
                await self._agent_fallback(
                    page, "configure_mode", exc,
                    f"On {self.display_name}: configure the AI model for {mode} mode. "
                    f"Select the appropriate model and enable required features.",
                )
                mode_label = "Agent-configured"

            # 3. Inject prompt
            log.info(f"[{self.display_name}] Injecting prompt ({len(prompt)} chars)")
            try:
                await self.inject_prompt(page, prompt)
            except Exception as exc:
                # Agent finds and focuses input, then Playwright retries via keyboard
                await self._agent_fallback(
                    page, "inject_prompt", exc,
                    f"On {self.display_name}: find and click/focus the main text input "
                    f"field where messages are typed. Do NOT type any text — just click on it.",
                )
                await page.keyboard.type(prompt, delay=1)
            await page.wait_for_timeout(500)

            # 4. Send
            log.info(f"[{self.display_name}] Sending prompt")
            await self.click_send(page)
            await page.wait_for_timeout(2000)

            # 5. Post-send hook
            try:
                await self.post_send(page, mode)
            except Exception as exc:
                try:
                    await self._agent_fallback(
                        page, "post_send", exc,
                        f"On {self.display_name}: look for any 'Start research' or "
                        f"similar confirmation button and click it if present.",
                    )
                except Exception:
                    log.warning(f"[{self.display_name}] post_send failed (non-fatal): {exc}")

            # 6. Poll for completion
            log.info(f"[{self.display_name}] Waiting for response (max {max_wait}s)")
            completed = await self._poll_completion(page, max_wait)

            if not completed:
                log.warning(f"[{self.display_name}] Timed out after {max_wait}s")
                # Try to extract whatever is available
                try:
                    response = await self.extract_response(page)
                    if response and len(response) > 500:
                        return self._save_and_result(
                            response, output_dir, mode_label, t0, STATUS_PARTIAL,
                            error="Timed out but partial content extracted"
                        )
                except Exception:
                    pass
                return PlatformResult(
                    platform=self.name, display_name=self.display_name,
                    status=STATUS_TIMEOUT, mode_used=mode_label,
                    error=f"Timed out after {max_wait}s",
                    duration_s=time.monotonic() - t0,
                )

            # 7. Extract response
            log.info(f"[{self.display_name}] Extracting response")
            try:
                response = await self.extract_response(page)
            except Exception as exc:
                result = await self._agent_fallback(
                    page, "extract_response", exc,
                    f"On {self.display_name}: extract the complete AI-generated response "
                    f"text from the page. Copy ALL the text from the AI's reply.",
                )
                response = result if result else ""

            # Skip Agent fallback if response is a known error/status message
            _is_status_msg = response and any(
                tag in response for tag in ("[RATE LIMITED]", "[FAILED]")
            )
            if not _is_status_msg and (not response or len(response) < 200):
                # Try Agent fallback if extraction returned too little content
                try:
                    result = await self._agent_fallback(
                        page, "extract_response",
                        RuntimeError(f"Extraction returned only {len(response) if response else 0} chars"),
                        f"On {self.display_name}: extract the complete AI response text. "
                        f"Scroll through the entire response and capture all visible text.",
                    )
                    # Use agent result if it returned any meaningful content
                    # (even if shorter than the raw body.innerText — the agent
                    # targets the actual AI response, not the whole page)
                    if result and len(result) >= 50:
                        response = result
                except Exception:
                    pass

            if not response or len(response) < 200:
                # Preserve status message text for rate-limited/failed responses
                if _is_status_msg:
                    status = STATUS_RATE_LIMITED if "[RATE LIMITED]" in response else STATUS_FAILED
                    return PlatformResult(
                        platform=self.name, display_name=self.display_name,
                        status=status, mode_used=mode_label,
                        error=response,
                        duration_s=time.monotonic() - t0,
                    )
                return PlatformResult(
                    platform=self.name, display_name=self.display_name,
                    status=STATUS_FAILED, mode_used=mode_label,
                    error=f"Extraction returned only {len(response) if response else 0} chars",
                    duration_s=time.monotonic() - t0,
                )

            # 8. Save
            return self._save_and_result(response, output_dir, mode_label, t0, STATUS_COMPLETE)

        except Exception as exc:
            log.exception(f"[{self.display_name}] Failed: {exc}")
            return PlatformResult(
                platform=self.name, display_name=self.display_name,
                status=STATUS_FAILED, mode_used="",
                error=str(exc),
                duration_s=time.monotonic() - t0,
            )

    # ------------------------------------------------------------------
    # Methods subclasses MUST override
    # ------------------------------------------------------------------

    async def configure_mode(self, page: Page, mode: str) -> str:
        """Configure the platform's model/mode. Return a label like 'Sonnet + Research'."""
        raise NotImplementedError

    async def completion_check(self, page: Page) -> bool:
        """Return True if the platform has finished generating."""
        raise NotImplementedError

    async def extract_response(self, page: Page) -> str:
        """Extract the full response text from the page."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Rate limit detection (subclasses SHOULD override)
    # ------------------------------------------------------------------

    async def check_rate_limit(self, page: Page) -> str | None:
        """Check for platform-specific rate limit indicators on the page.

        Returns:
            A descriptive string if rate-limited (e.g., "Usage limit reached"),
            or None if no rate limit detected.

        Subclasses should override this with platform-specific selectors.
        Default implementation checks common patterns.
        """
        common_patterns = [
            "rate limit",
            "too many requests",
            "limit reached",
            "try again later",
            "quota exceeded",
        ]
        try:
            for pattern in common_patterns:
                el = page.get_by_text(pattern, exact=False).first
                if await el.count() > 0 and await el.is_visible():
                    return pattern
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # Methods subclasses CAN override
    # ------------------------------------------------------------------

    async def inject_prompt(self, page: Page, prompt: str) -> None:
        """Inject the research prompt into the platform's input field."""
        method = INJECTION_METHODS.get(self.name, "execCommand")

        if method == "execCommand":
            await self._inject_exec_command(page, prompt)
        elif method == "physical_type":
            await self._inject_physical_type(page, prompt)
        elif method == "fill":
            await self._inject_fill(page, prompt)
        else:
            raise NotImplementedError(f"Unknown injection method: {method}")

    async def click_send(self, page: Page) -> None:
        """Click the send/submit button."""
        # Try common send button selectors
        for selector in [
            'button[aria-label*="Send"]',
            'button[aria-label*="send"]',
            'button[aria-label*="Submit"]',
            'button[data-testid*="send"]',
            'button[type="submit"]',
        ]:
            btn = page.locator(selector).first
            if await btn.count() > 0 and await btn.is_visible():
                await btn.click()
                return

        # Fallback: find button with send-like text
        for text in ["Send", "Submit", "Search", "Ask"]:
            btn = page.get_by_role("button", name=text).first
            if await btn.count() > 0 and await btn.is_visible():
                await btn.click()
                return

        # Agent fallback: try vision-based button finding before Enter
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

        # Last resort: press Enter
        log.warning(f"[{self.display_name}] No send button found, pressing Enter")
        await page.keyboard.press("Enter")

    async def post_send(self, page: Page, mode: str) -> None:
        """Hook for actions after sending (e.g., Gemini 'Start research' click)."""
        pass

    # ------------------------------------------------------------------
    # Agent fallback
    # ------------------------------------------------------------------

    async def _agent_fallback(
        self, page: Page, step: str, error: Exception, task_description: str,
    ):
        """Invoke browser-use Agent fallback. Re-raises original error if disabled or fails."""
        if self.agent_manager is None or not self.agent_manager.enabled:
            raise error
        from agent_fallback import FallbackStep
        return await self.agent_manager.fallback(
            page, self.name, FallbackStep(step), error, task_description,
        )

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    async def _poll_completion(self, page: Page, max_wait_s: int) -> bool:
        """Poll until completion_check returns True or timeout."""
        start = time.monotonic()
        consecutive_errors = 0
        max_consecutive_errors = 5

        while time.monotonic() - start < max_wait_s:
            # Check for rate limiting during polling
            try:
                rate_msg = await self.check_rate_limit(page)
                if rate_msg:
                    log.warning(f"[{self.display_name}] Rate limited during polling: {rate_msg}")
                    return True  # Exit poll; extract_response will detect the rate limit
            except Exception:
                pass  # Non-fatal — continue polling

            try:
                if await self.completion_check(page):
                    log.info(f"[{self.display_name}] Response complete ({time.monotonic() - start:.0f}s)")
                    return True
                consecutive_errors = 0
            except Exception as exc:
                consecutive_errors += 1
                if consecutive_errors >= max_consecutive_errors:
                    # Try Agent fallback before aborting
                    try:
                        result = await self._agent_fallback(
                            page, "completion_check", exc,
                            f"On {self.display_name}: check if the AI has finished generating. "
                            f"Look for: no stop/cancel button, copy/share buttons visible, "
                            f"or fully rendered response. Answer 'yes' if complete, 'no' if still generating.",
                        )
                        if result and "yes" in result.lower():
                            return True
                        consecutive_errors = 0  # Agent worked; reset counter
                        continue
                    except Exception:
                        log.error(f"[{self.display_name}] {consecutive_errors} consecutive poll errors, aborting: {exc}")
                        raise
                log.debug(f"[{self.display_name}] Poll check error ({consecutive_errors}/{max_consecutive_errors}): {exc}")

            await asyncio.sleep(POLL_INTERVAL)
        return False

    # ------------------------------------------------------------------
    # Injection helpers
    # ------------------------------------------------------------------

    async def _inject_exec_command(self, page: Page, prompt: str) -> int:
        """Inject into a contenteditable div via document.execCommand. Returns verified char count."""
        await page.evaluate("""(prompt) => {
            const el = document.querySelector('div[contenteditable="true"]')
                      || document.querySelector('[contenteditable="true"]');
            if (!el) throw new Error('No contenteditable element found');
            el.focus();
            document.execCommand('selectAll', false, null);
            document.execCommand('insertText', false, prompt);
        }""", prompt)
        # Verify injection
        length = await page.evaluate("""
            (document.querySelector('div[contenteditable="true"]')
             || document.querySelector('[contenteditable="true"]')).textContent.length
        """)
        log.info(f"[{self.display_name}] Injected {length} chars via execCommand")
        return length

    async def _inject_physical_type(self, page: Page, prompt: str) -> None:
        """Physical keyboard typing for React textareas (e.g., Grok)."""
        textarea = page.locator("textarea").first
        await textarea.click()
        await page.wait_for_timeout(300)
        await textarea.type(prompt, delay=5)  # 5ms between keystrokes
        log.info(f"[{self.display_name}] Typed {len(prompt)} chars physically")

    async def _inject_fill(self, page: Page, prompt: str) -> None:
        """Fill a React textarea using Playwright's fill() (triggers React state)."""
        textarea = page.locator("textarea").first
        await textarea.click()
        await page.wait_for_timeout(300)
        await textarea.fill(prompt)
        # Dispatch input event to trigger React state update
        await textarea.dispatch_event("input")
        log.info(f"[{self.display_name}] Filled textarea with {len(prompt)} chars")

    # ------------------------------------------------------------------
    # Save helpers
    # ------------------------------------------------------------------

    def _save_and_result(
        self,
        response: str,
        output_dir: str,
        mode_label: str,
        t0: float,
        status: str,
        error: str = "",
    ) -> PlatformResult:
        """Save response to file and return PlatformResult."""
        filename = f"{self.display_name.replace(' ', '-')}-raw-response.md"
        filepath = Path(output_dir) / filename
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(response, encoding="utf-8")
        log.info(f"[{self.display_name}] Saved {len(response)} chars to {filepath}")
        return PlatformResult(
            platform=self.name,
            display_name=self.display_name,
            status=status,
            chars=len(response),
            file=str(filepath),
            mode_used=mode_label,
            error=error,
            duration_s=time.monotonic() - t0,
        )
