"""Centralized rate limiting for Multi-AI Orchestrator.

Tracks per-platform usage, enforces cooldowns and budget limits, provides
staggered launch ordering, and persists state across sessions.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from config import (
    DEFAULT_TIER,
    PLATFORM_DISPLAY_NAMES,
    RATE_LIMIT_STATE_DIR,
    RATE_LIMITS,
    RateLimitConfig,
    STAGGER_DELAY,
    STATUS_COMPLETE,
    STATUS_RATE_LIMITED,
)

log = logging.getLogger("rate_limiter")

_STATE_VERSION = 1
_STATE_FILENAME = "rate-limit-state.json"

# Maximum exponential backoff exponent (2^4 = 16x multiplier)
_MAX_BACKOFF_EXP = 4


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class UsageRecord:
    """A single platform usage event."""
    timestamp: str       # ISO 8601 with timezone
    mode: str            # "DEEP" or "REGULAR"
    status: str          # Terminal status from config.py
    duration_s: float    # How long the run took


@dataclass
class PlatformUsageState:
    """Aggregated state for a single platform."""
    recent_requests: list[dict] = field(default_factory=list)
    last_rate_limited_at: str = ""
    consecutive_rate_limits: int = 0


@dataclass
class PreflightResult:
    """Result of a pre-flight rate limit check."""
    allowed: bool
    wait_seconds: int = 0
    reason: str = ""
    budget_remaining: int = 0
    budget_total: int = 0


# ---------------------------------------------------------------------------
# RateLimiter
# ---------------------------------------------------------------------------

class RateLimiter:
    """Centralized rate limiting for the Multi-AI Orchestrator.

    Responsibilities:
      1. Pre-flight check: can a platform be safely invoked?
      2. Usage tracking: record each invocation outcome
      3. Persistence: load/save state to JSON file
      4. Cooldown enforcement: calculate wait time before next safe invocation
      5. Staggered launch ordering: determine platform launch sequence
    """

    def __init__(
        self,
        tier: str = DEFAULT_TIER,
        state_path: str | None = None,
    ):
        self._tier = tier
        self._state_path = Path(state_path) if state_path else (
            Path(RATE_LIMIT_STATE_DIR) / _STATE_FILENAME
        )
        # platform_name -> PlatformUsageState
        self._state: dict[str, PlatformUsageState] = {}

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def load_state(self) -> None:
        """Load state from JSON file and prune expired records."""
        if not self._state_path.exists():
            log.debug(f"No rate-limit state file at {self._state_path} — starting fresh")
            self._state = {}
            return

        try:
            raw = json.loads(self._state_path.read_text(encoding="utf-8"))
            version = raw.get("version", 0)
            if version != _STATE_VERSION:
                log.warning(f"State file version mismatch ({version} != {_STATE_VERSION}) — resetting")
                self._state = {}
                return

            # Restore tier if it was saved (but CLI flag takes precedence)
            usage = raw.get("usage", {})
            for platform_name, pstate in usage.items():
                self._state[platform_name] = PlatformUsageState(
                    recent_requests=pstate.get("recent_requests", []),
                    last_rate_limited_at=pstate.get("last_rate_limited_at", ""),
                    consecutive_rate_limits=pstate.get("consecutive_rate_limits", 0),
                )

            # Prune expired records for all platforms
            for platform_name in list(self._state.keys()):
                self._prune_expired(platform_name)

            log.debug(f"Loaded rate-limit state for {len(self._state)} platforms")

        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            log.warning(f"Corrupt rate-limit state file — resetting: {exc}")
            self._state = {}

    def save_state(self) -> None:
        """Persist current state to JSON via atomic write."""
        data = {
            "version": _STATE_VERSION,
            "tier": self._tier,
            "usage": {},
        }
        for platform_name, pstate in self._state.items():
            data["usage"][platform_name] = {
                "recent_requests": pstate.recent_requests,
                "last_rate_limited_at": pstate.last_rate_limited_at,
                "consecutive_rate_limits": pstate.consecutive_rate_limits,
            }

        # Ensure directory exists
        self._state_path.parent.mkdir(parents=True, exist_ok=True)

        # Atomic write: write to temp file, then rename
        fd, tmp_path = tempfile.mkstemp(
            dir=str(self._state_path.parent),
            prefix=".rate-limit-",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, str(self._state_path))
        except Exception:
            # Clean up temp file on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    # ------------------------------------------------------------------
    # Pre-flight check
    # ------------------------------------------------------------------

    def preflight_check(self, platform: str, mode: str) -> PreflightResult:
        """Check if a platform can be safely invoked given current budget.

        Returns a PreflightResult indicating whether the platform is allowed,
        how long to wait if not, and the reason for blocking.
        """
        config = self._get_config(platform, mode)
        if config is None:
            # Unknown platform/tier/mode — allow by default
            return PreflightResult(allowed=True, budget_remaining=0, budget_total=0)

        now = time.time()
        state = self._state.get(platform, PlatformUsageState())

        # Count requests in the rolling window
        count_in_window = self._count_in_window(platform, mode, now)
        budget_remaining = max(0, config.max_requests - count_in_window)
        budget_total = config.max_requests

        # Check 1: Daily cap (mode-specific — only count requests of the same mode)
        if config.daily_cap > 0:
            count_today = self._count_today(platform, mode, now)
            if count_today >= config.daily_cap:
                seconds_until_midnight = self._seconds_until_midnight()
                return PreflightResult(
                    allowed=False,
                    wait_seconds=int(seconds_until_midnight),
                    reason=f"Daily cap reached ({count_today}/{config.daily_cap})",
                    budget_remaining=0,
                    budget_total=budget_total,
                )

        # Check 2: Rolling window budget
        if count_in_window >= config.max_requests:
            oldest_in_window = self._oldest_in_window(platform, mode, now, config.window_seconds)
            if oldest_in_window:
                wait = config.window_seconds - (now - oldest_in_window)
                wait = max(0, wait)
            else:
                wait = config.cooldown_seconds
            return PreflightResult(
                allowed=False,
                wait_seconds=int(wait),
                reason=f"Window budget exhausted ({count_in_window}/{config.max_requests})",
                budget_remaining=0,
                budget_total=budget_total,
            )

        # Check 3: Cooldown since last request
        effective_cooldown = config.cooldown_seconds

        # Check 4: Exponential backoff if recently rate-limited
        if state.consecutive_rate_limits > 0:
            backoff_exp = min(state.consecutive_rate_limits, _MAX_BACKOFF_EXP)
            effective_cooldown = config.cooldown_seconds * (2 ** backoff_exp)

        last_ts = self._last_request_timestamp(platform, now)
        if last_ts is not None:
            elapsed = now - last_ts
            if elapsed < effective_cooldown:
                return PreflightResult(
                    allowed=False,
                    wait_seconds=int(effective_cooldown - elapsed),
                    reason=f"Cooldown active ({int(elapsed)}s / {int(effective_cooldown)}s)",
                    budget_remaining=budget_remaining,
                    budget_total=budget_total,
                )

        return PreflightResult(
            allowed=True,
            wait_seconds=0,
            budget_remaining=budget_remaining,
            budget_total=budget_total,
        )

    # ------------------------------------------------------------------
    # Usage recording
    # ------------------------------------------------------------------

    def record_usage(
        self,
        platform: str,
        mode: str,
        status: str,
        duration_s: float,
    ) -> None:
        """Record a platform invocation outcome and persist immediately."""
        if platform not in self._state:
            self._state[platform] = PlatformUsageState()

        state = self._state[platform]

        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": mode,
            "status": status,
            "duration_s": round(duration_s, 1),
        }
        state.recent_requests.append(record)

        # Update rate-limit tracking
        if status == STATUS_RATE_LIMITED:
            state.consecutive_rate_limits += 1
            state.last_rate_limited_at = record["timestamp"]
            log.warning(
                f"[{PLATFORM_DISPLAY_NAMES.get(platform, platform)}] "
                f"Rate limited — consecutive count: {state.consecutive_rate_limits}"
            )
        elif status == STATUS_COMPLETE:
            if state.consecutive_rate_limits > 0:
                log.info(
                    f"[{PLATFORM_DISPLAY_NAMES.get(platform, platform)}] "
                    f"Successful run — resetting consecutive rate limit counter"
                )
            state.consecutive_rate_limits = 0

        # Persist immediately (so state survives crashes)
        try:
            self.save_state()
        except Exception as exc:
            log.warning(f"Failed to persist rate-limit state: {exc}")

    # ------------------------------------------------------------------
    # Staggered launch ordering
    # ------------------------------------------------------------------

    def get_staggered_order(
        self,
        platforms: list[str],
        mode: str,
        stagger_delay: float = STAGGER_DELAY,
    ) -> list[tuple[str, float]]:
        """Return platforms sorted by launch priority with stagger delays.

        Priority (higher = launch first):
          - Platforms with most remaining budget percentage get higher priority
          - Platforms recently rate-limited get lower priority
        """
        scored: list[tuple[str, float]] = []
        now = time.time()

        for name in platforms:
            config = self._get_config(name, mode)
            if config is None:
                scored.append((name, 50.0))  # Unknown — middle priority
                continue

            count = self._count_in_window(name, mode, now)
            remaining_pct = (config.max_requests - count) / max(config.max_requests, 1)

            # Penalty for recent rate limits
            state = self._state.get(name, PlatformUsageState())
            rl_penalty = state.consecutive_rate_limits * 20.0

            score = remaining_pct * 100.0 - rl_penalty
            scored.append((name, score))

        # Sort descending by score (highest budget first)
        scored.sort(key=lambda x: x[1], reverse=True)

        # Assign stagger delays
        result: list[tuple[str, float]] = []
        for i, (name, _score) in enumerate(scored):
            delay = i * stagger_delay
            result.append((name, delay))

        return result

    # ------------------------------------------------------------------
    # Budget summary
    # ------------------------------------------------------------------

    def get_budget_summary(self, mode: str) -> dict[str, dict]:
        """Return human-readable budget for each platform.

        Returns: {platform_name: {remaining, total, next_available_in, cooldown, tier, notes}}
        """
        now = time.time()
        summary: dict[str, dict] = {}

        for platform_name in RATE_LIMITS:
            config = self._get_config(platform_name, mode)
            if config is None:
                continue

            count = self._count_in_window(platform_name, mode, now)
            remaining = max(0, config.max_requests - count)

            # Calculate next available time
            preflight = self.preflight_check(platform_name, mode)

            display_name = PLATFORM_DISPLAY_NAMES.get(platform_name, platform_name)
            summary[platform_name] = {
                "display_name": display_name,
                "remaining": remaining,
                "total": config.max_requests,
                "next_available_in": preflight.wait_seconds,
                "cooldown": config.cooldown_seconds,
                "daily_cap": config.daily_cap,
                "tier": self._tier,
                "notes": config.notes,
            }

        return summary

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_config(self, platform: str, mode: str) -> RateLimitConfig | None:
        """Look up rate limit config for platform/tier/mode."""
        platform_cfg = RATE_LIMITS.get(platform)
        if not platform_cfg:
            return None
        tier_cfg = platform_cfg.get(self._tier)
        if not tier_cfg:
            # Fall back to free tier
            tier_cfg = platform_cfg.get("free")
        if not tier_cfg:
            return None
        return tier_cfg.get(mode)

    def _prune_expired(self, platform: str) -> None:
        """Remove records older than the largest window for this platform."""
        if platform not in self._state:
            return

        # Find the largest window across all modes for this platform
        max_window = 0
        platform_cfg = RATE_LIMITS.get(platform, {})
        for tier_cfg in platform_cfg.values():
            for mode_cfg in tier_cfg.values():
                max_window = max(max_window, mode_cfg.window_seconds)

        if max_window == 0:
            max_window = 86400  # Default: 24 hours

        cutoff = time.time() - max_window
        state = self._state[platform]
        original_count = len(state.recent_requests)
        state.recent_requests = [
            r for r in state.recent_requests
            if self._parse_timestamp(r.get("timestamp", "")) > cutoff
        ]
        pruned = original_count - len(state.recent_requests)
        if pruned > 0:
            log.debug(f"[{platform}] Pruned {pruned} expired usage records")

    def _count_in_window(self, platform: str, mode: str, now: float) -> int:
        """Count requests within the rolling window for a platform/mode."""
        config = self._get_config(platform, mode)
        if config is None:
            return 0

        state = self._state.get(platform)
        if state is None:
            return 0

        cutoff = now - config.window_seconds
        return sum(
            1 for r in state.recent_requests
            if (r.get("mode") == mode
                and self._parse_timestamp(r.get("timestamp", "")) > cutoff)
        )

    def _count_today(self, platform: str, mode: str, now: float) -> int:
        """Count requests today for a specific mode, for daily cap check.

        Uses LOCAL midnight as the day boundary, consistent with
        _seconds_until_midnight() which reports wait time until local midnight.
        AI platform daily caps reset at calendar-day boundaries in the user's
        timezone, not at UTC midnight.
        """
        state = self._state.get(platform)
        if state is None:
            return 0

        # Start of today (local midnight — must match _seconds_until_midnight)
        today_start = datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        ).timestamp()

        return sum(
            1 for r in state.recent_requests
            if (r.get("mode") == mode
                and self._parse_timestamp(r.get("timestamp", "")) >= today_start)
        )

    def _oldest_in_window(
        self, platform: str, mode: str, now: float, window_seconds: int,
    ) -> float | None:
        """Return timestamp of the oldest request in the window, or None."""
        state = self._state.get(platform)
        if state is None:
            return None

        cutoff = now - window_seconds
        timestamps = [
            self._parse_timestamp(r.get("timestamp", ""))
            for r in state.recent_requests
            if (r.get("mode") == mode
                and self._parse_timestamp(r.get("timestamp", "")) > cutoff)
        ]
        return min(timestamps) if timestamps else None

    def _last_request_timestamp(self, platform: str, now: float) -> float | None:
        """Return timestamp of the most recent request (any mode), or None."""
        state = self._state.get(platform)
        if state is None or not state.recent_requests:
            return None

        timestamps = [
            self._parse_timestamp(r.get("timestamp", ""))
            for r in state.recent_requests
        ]
        latest = max(timestamps) if timestamps else None
        return latest

    @staticmethod
    def _parse_timestamp(ts: str) -> float:
        """Parse ISO 8601 timestamp to Unix epoch seconds."""
        if not ts:
            return 0.0
        try:
            dt = datetime.fromisoformat(ts)
            return dt.timestamp()
        except (ValueError, TypeError):
            return 0.0

    @staticmethod
    def _seconds_until_midnight() -> float:
        """Seconds remaining until local midnight."""
        now = datetime.now()
        midnight = now.replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        # Next midnight
        from datetime import timedelta
        next_midnight = midnight + timedelta(days=1)
        return (next_midnight - now).total_seconds()
