"""browser-use Agent fallback for Playwright selector failures.

When all deterministic Playwright selectors fail, the AgentFallbackManager
uses a browser-use Agent (vision-based) to find and interact with elements.
All fallback events are logged to agent-fallback-log.json so that Playwright
scripts can be updated to match the current UI.

Requires: ANTHROPIC_API_KEY environment variable and browser-use ≥0.12 package.
If either is missing, the fallback is disabled and original exceptions propagate.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


class FallbackStep(str, Enum):
    """Which lifecycle step triggered the fallback."""
    CONFIGURE_MODE = "configure_mode"
    INJECT_PROMPT = "inject_prompt"
    CLICK_SEND = "click_send"
    POST_SEND = "post_send"
    COMPLETION_CHECK = "completion_check"
    EXTRACT_RESPONSE = "extract_response"


@dataclass
class FallbackEvent:
    """A single Agent fallback invocation record."""
    timestamp: str
    platform: str
    step: str
    original_error: str
    agent_task: str
    agent_result: str
    agent_success: bool
    playwright_script_path: str = ""
    duration_s: float = 0.0


class AgentFallbackManager:
    """
    Manages browser-use Agent fallback invocations.

    - Serialized access via asyncio.Lock (one Agent at a time across all platforms)
    - Logs all fallback events to agent-fallback-log.json
    - Disabled if ANTHROPIC_API_KEY is not set or browser-use is not installed
    """

    def __init__(self, cdp_url: str, output_dir: str, max_steps: int = 5):
        self._cdp_url = cdp_url
        self._output_dir = output_dir
        self._max_steps = max_steps
        self._lock = asyncio.Lock()
        self._events: list[FallbackEvent] = []

        # Prefer Anthropic; fall back to Google Gemini if only that key is present
        if os.environ.get("ANTHROPIC_API_KEY"):
            self._llm_provider = "anthropic"
        elif os.environ.get("GOOGLE_API_KEY"):
            self._llm_provider = "google"
        else:
            self._llm_provider = None
        self._enabled = self._llm_provider is not None

        if not self._enabled:
            log.info("AgentFallbackManager DISABLED — neither ANTHROPIC_API_KEY nor GOOGLE_API_KEY is set")
        else:
            log.info(
                f"AgentFallbackManager enabled — provider: {self._llm_provider}, "
                f"CDP: {cdp_url}, max_steps: {max_steps}"
            )

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def fallback(
        self,
        page,  # playwright.async_api.Page
        platform_name: str,
        step: FallbackStep,
        original_error: Exception,
        task_description: str,
    ) -> Optional[str]:
        """
        Execute an Agent fallback. Returns the Agent's result text, or None on failure.
        Raises the original_error if Agent is disabled or also fails.
        """
        if not self._enabled:
            raise original_error

        log.warning(
            f"[{platform_name}] AGENT FALLBACK triggered for {step.value}: {original_error}"
        )

        async with self._lock:
            return await self._run_agent(
                page, platform_name, step, original_error, task_description
            )

    async def _run_agent(
        self,
        page,
        platform_name: str,
        step: FallbackStep,
        original_error: Exception,
        task_description: str,
    ) -> Optional[str]:
        """Run browser-use Agent under the serialization lock."""
        t0 = time.monotonic()

        try:
            # Lazy import — module loads even when browser-use not installed
            # browser-use ≥0.12 uses its own LLM abstraction (browser_use.llm)
            from browser_use import Agent, BrowserSession

            # Bring the target tab to front so Agent can screenshot it
            await page.bring_to_front()
            await asyncio.sleep(0.5)

            # Connect to existing Chrome via CDP
            session = BrowserSession(cdp_url=self._cdp_url)

            # Select LLM based on which API key is available
            from config import AGENT_MODEL_ANTHROPIC, AGENT_MODEL_GOOGLE

            if self._llm_provider == "anthropic":
                from browser_use.llm.anthropic.chat import ChatAnthropic
                llm = ChatAnthropic(
                    model=AGENT_MODEL_ANTHROPIC,
                    timeout=60,
                    max_tokens=4096,
                )
            else:
                from browser_use.llm.google.chat import ChatGoogle
                llm = ChatGoogle(
                    model=AGENT_MODEL_GOOGLE,
                    api_key=os.environ.get("GOOGLE_API_KEY"),
                )

            agent = Agent(
                task=task_description,
                llm=llm,
                browser_session=session,
                max_steps=self._max_steps,
            )

            history = await agent.run()
            raw = history.final_result() if history else None
            result_text = str(raw) if raw is not None else ""

            duration = time.monotonic() - t0
            event = FallbackEvent(
                timestamp=datetime.now().isoformat(),
                platform=platform_name,
                step=step.value,
                original_error=str(original_error),
                agent_task=task_description,
                agent_result=result_text[:500],
                agent_success=True,
                duration_s=round(duration, 1),
            )
            self._events.append(event)
            self._save_log()

            log.info(
                f"[{platform_name}] Agent fallback SUCCEEDED for {step.value} "
                f"({duration:.1f}s)"
            )
            return result_text

        except Exception as agent_exc:
            duration = time.monotonic() - t0
            event = FallbackEvent(
                timestamp=datetime.now().isoformat(),
                platform=platform_name,
                step=step.value,
                original_error=str(original_error),
                agent_task=task_description,
                agent_result=str(agent_exc),
                agent_success=False,
                duration_s=round(duration, 1),
            )
            self._events.append(event)
            self._save_log()

            log.error(
                f"[{platform_name}] Agent fallback FAILED for {step.value}: {agent_exc}"
            )
            # Re-raise the ORIGINAL error (not the agent error)
            raise original_error from agent_exc

    def _save_log(self) -> None:
        """Persist all fallback events to agent-fallback-log.json."""
        log_path = Path(self._output_dir) / "agent-fallback-log.json"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(
            json.dumps(
                [asdict(e) for e in self._events],
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
