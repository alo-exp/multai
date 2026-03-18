"""Claude.ai platform automation."""

from __future__ import annotations

import logging

from playwright.async_api import Page

from .base import BasePlatform
from prompt_echo import is_prompt_echo

log = logging.getLogger(__name__)


class ClaudeAI(BasePlatform):
    name = "claude_ai"

    def __init__(self):
        super().__init__()
        self._no_stop_polls: int = 0  # Consecutive polls with no stop button visible

    async def check_rate_limit(self, page: Page) -> str | None:
        """Check for Claude.ai-specific rate limit indicators."""
        patterns = [
            "Usage limit reached",
            "too many messages",
            "You've sent too many",
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
        Select Sonnet model (NEVER Opus). Optionally enable Research + Web search (DEEP).
        Rate limit pre-check is now handled by base class check_rate_limit().
        """
        label_parts = ["Sonnet"]

        # Select model: click model selector → pick Sonnet
        try:
            # Model selector button (varies by UI version)
            model_btn = page.locator('button[aria-haspopup="listbox"], [data-testid*="model"]').first
            if await model_btn.count() == 0:
                # Try finding by text content
                model_btn = page.locator('button:has-text("Claude")').first
            if await model_btn.count() == 0:
                model_btn = page.locator('button:has-text("Sonnet"), button:has-text("Opus"), button:has-text("Haiku")').first

            if await model_btn.count() > 0 and await model_btn.is_visible():
                await model_btn.click()
                await page.wait_for_timeout(500)

                # Click Sonnet option (NOT Opus)
                sonnet = page.get_by_text("Sonnet", exact=False).first
                if await sonnet.count() > 0:
                    await sonnet.click()
                    await page.wait_for_timeout(500)
                    log.info("[Claude.ai] Selected Sonnet model")
        except RuntimeError:
            raise
        except Exception as exc:
            log.warning(f"[Claude.ai] Model selection failed: {exc}")

        # DEEP mode: enable Research + Web search
        if mode == "DEEP":
            try:
                # Click + button in composer
                plus_btn = page.locator('button[aria-label*="Add"], button[aria-label*="attach"]').first
                if await plus_btn.count() == 0:
                    plus_btn = page.locator('button:has-text("+")').first
                if await plus_btn.count() > 0 and await plus_btn.is_visible():
                    await plus_btn.click()
                    await page.wait_for_timeout(500)

                    # Enable Research
                    research = page.get_by_text("Research", exact=False).first
                    if await research.count() > 0:
                        await research.click()
                        await page.wait_for_timeout(300)
                        log.info("[Claude.ai] Enabled Research mode")
                        label_parts.append("Research")

                    # Enable Web search
                    websearch = page.get_by_text("Web search", exact=False).first
                    if await websearch.count() > 0:
                        await websearch.click()
                        await page.wait_for_timeout(300)
                        log.info("[Claude.ai] Enabled Web search")
                        label_parts.append("Web search")
            except Exception as exc:
                log.warning(f"[Claude.ai] Research/Web search enablement failed: {exc}")

        return " + ".join(label_parts)

    async def inject_prompt(self, page: Page, prompt: str) -> None:
        """Inject via contenteditable with retry/wait for slow page loads."""
        # Wait for contenteditable to appear (Claude.ai can be slow to render)
        for attempt in range(5):
            ce = page.locator('div[contenteditable="true"]').first
            if await ce.count() > 0 and await ce.is_visible():
                break
            log.debug(f"[Claude.ai] Waiting for contenteditable (attempt {attempt + 1})")
            await page.wait_for_timeout(2000)
        else:
            raise RuntimeError("No contenteditable element found after 10s wait")

        length = await self._inject_exec_command(page, prompt)
        log.info(f"[Claude.ai] Injected {length} chars via execCommand")

    async def completion_check(self, page: Page) -> bool:
        """
        Check for Copy/Download buttons in artifact header.
        Claude.ai does NOT auto-display results — may need to click to reveal.
        Rate limit mid-generation check now handled by base class _poll_completion().

        Stable-state fallback: if no stop button AND no completion signal appear
        for 12 consecutive polls (~2 min), declare complete.  This handles
        REGULAR mode responses that are plain text (no artifact/download button).
        """
        # Check for stop button (still generating)
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

        # Check for explicit completion indicators (artifact copy/download buttons)
        for sel in [
            'button:has-text("Copy")',
            'button:has-text("Download")',
            'button[aria-label*="Copy"]',
        ]:
            try:
                btn = page.locator(sel).first
                if await btn.count() > 0 and await btn.is_visible():
                    return True
            except Exception:
                pass

        # Try clicking artifact card to reveal report (Research mode quirk)
        try:
            artifact = page.locator('[class*="artifact"], [class*="document"]').first
            if await artifact.count() > 0 and await artifact.is_visible():
                await artifact.click()
                await page.wait_for_timeout(1000)
                # Re-check for Copy/Download
                for sel in ['button:has-text("Copy")', 'button:has-text("Download")']:
                    btn = page.locator(sel).first
                    if await btn.count() > 0 and await btn.is_visible():
                        return True
        except Exception:
            pass

        # Content-based: body text > 10 000 chars → likely a substantial response
        try:
            body_len = await page.evaluate("document.body.innerText.length")
            if body_len > 10000:
                return True
        except Exception:
            pass

        # Stable-state: no stop and no copy button for 12 consecutive polls (~2 min).
        # Handles REGULAR mode plain-text responses that never produce an artifact.
        if self._no_stop_polls >= 12:
            log.warning(
                "[Claude.ai] 12 polls with no stop and no copy button — "
                "declaring complete (likely plain-text REGULAR response)."
            )
            return True

        return False

    async def extract_response(self, page: Page) -> str:
        """
        Extract from DOCX artifact download, artifact panel, or body text.
        Claude.ai renders large reports as DOCX artifacts in a cross-origin
        iframe (claudeusercontent.com) — the content is NOT accessible via
        Playwright frames or page.evaluate. We download the DOCX and extract
        text via python-docx.
        """
        # Check for rate limiting
        try:
            rate = page.get_by_text("Usage limit reached", exact=False).first
            if await rate.count() > 0 and await rate.is_visible():
                return "[RATE LIMITED] Claude.ai usage limit reached."
        except Exception:
            pass

        # Ensure artifact panel is open
        try:
            for sel in ['[class*="artifact"]', '[class*="document"]', 'button:has-text("DOCX")']:
                card = page.locator(sel).first
                if await card.count() > 0 and await card.is_visible():
                    await card.click()
                    await page.wait_for_timeout(2000)
                    log.debug("[Claude.ai] Clicked artifact card to open panel")
                    break
        except Exception:
            pass

        # PRIMARY: Download DOCX artifact and extract text via python-docx
        try:
            download_btn = page.locator('button[aria-label="Download"]').first
            if await download_btn.count() > 0 and await download_btn.is_visible():
                async with page.expect_download(timeout=15000) as download_info:
                    await download_btn.click()
                download = await download_info.value
                path = await download.path()
                if path:
                    from docx import Document
                    doc = Document(path)
                    text = "\n".join(p.text for p in doc.paragraphs)
                    if len(text) > 500:
                        log.info(f"[Claude.ai] Extracted {len(text)} chars via DOCX download")
                        return text
                    log.debug(f"[Claude.ai] DOCX too short ({len(text)} chars), trying other methods")
        except Exception as exc:
            log.debug(f"[Claude.ai] DOCX download extraction failed: {exc}")

        # Secondary: artifact panel inner text (works for non-DOCX artifacts)
        try:
            panel = page.locator('.ease-out.duration-200.relative.flex.w-full.flex-1.overflow-x-auto.overflow-y-scroll').first
            if await panel.count() > 0:
                text = await panel.inner_text()
                if len(text) > 5000:
                    log.info(f"[Claude.ai] Extracted {len(text)} chars via panel selector")
                    return text
        except Exception:
            pass

        # Tertiary: body.innerText — find ALL occurrences of generic Markdown
        # heading markers and pick the LAST one that is not a prompt echo.
        try:
            body = await page.evaluate("document.body.innerText")
            for marker in ["# ", "## "]:
                positions = []
                start = 0
                while True:
                    idx = body.find(marker, start)
                    if idx < 0:
                        break
                    positions.append(idx)
                    start = idx + 1

                for idx in reversed(positions):
                    text = body[idx:]
                    if is_prompt_echo(text, self.prompt_sigs):
                        log.debug(f"[Claude.ai] Skipped prompt echo at pos {idx}")
                        continue
                    if len(text) > 500:
                        log.info(f"[Claude.ai] Extracted {len(text)} chars via body marker '{marker}' at pos {idx}")
                        return text
        except Exception:
            pass

        # Last resort: full body text (with prompt-echo guard)
        try:
            body = await page.evaluate("document.body.innerText")
            if is_prompt_echo(body, self.prompt_sigs):
                log.warning("[Claude.ai] body.innerText appears to be a prompt echo — returning as-is (no better option)")
            log.info(f"[Claude.ai] Extracted {len(body)} chars via full body.innerText")
            return body
        except Exception as exc:
            log.error(f"[Claude.ai] All extraction methods failed: {exc}")
            return ""
