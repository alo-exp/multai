"""Unit tests for rate_limiter module.

Tests UT-RL-01 through UT-RL-14.
"""

import json
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

# Add engine directory to sys.path for bare imports
sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "orchestrator" / "engine"))

from rate_limiter import RateLimiter, PreflightResult, PlatformUsageState
from config import (
    DEFAULT_TIER,
    RATE_LIMITS,
    STAGGER_DELAY,
    STATUS_COMPLETE,
    STATUS_RATE_LIMITED,
)


def _tmp_state_path() -> str:
    """Return a temp file path for rate limiter state."""
    fd, path = tempfile.mkstemp(suffix=".json", prefix="rl-test-")
    import os
    os.close(fd)
    os.unlink(path)  # RateLimiter will create it on save
    return path


class TestRateLimiterInit:
    """Tests for RateLimiter construction and state management."""

    def test_ut_rl_01_default_tier(self):
        """UT-RL-01: Default tier is 'free'."""
        rl = RateLimiter(state_path=_tmp_state_path())
        assert rl._tier == DEFAULT_TIER
        assert rl._tier == "free"

    def test_ut_rl_02_custom_tier(self):
        """UT-RL-02: Constructor accepts custom tier."""
        rl = RateLimiter(tier="paid", state_path=_tmp_state_path())
        assert rl._tier == "paid"

    def test_ut_rl_03_load_empty_state(self):
        """UT-RL-03: load_state with no file starts fresh (no error)."""
        path = _tmp_state_path()
        rl = RateLimiter(state_path=path)
        rl.load_state()  # Should not raise
        assert rl._state == {}

    def test_ut_rl_04_save_and_reload_state(self):
        """UT-RL-04: save_state persists and load_state restores."""
        path = _tmp_state_path()
        rl = RateLimiter(state_path=path)
        rl.load_state()

        # Record some usage
        rl.record_usage("claude_ai", "REGULAR", STATUS_COMPLETE, 10.0)

        # Create a new limiter and reload
        rl2 = RateLimiter(state_path=path)
        rl2.load_state()
        assert "claude_ai" in rl2._state
        assert len(rl2._state["claude_ai"].recent_requests) == 1


class TestPreflightCheck:
    """Tests for preflight_check()."""

    def test_ut_rl_05_preflight_fresh_allows(self):
        """UT-RL-05: Preflight on fresh state allows all platforms."""
        rl = RateLimiter(state_path=_tmp_state_path())
        rl.load_state()
        result = rl.preflight_check("claude_ai", "REGULAR")
        assert result.allowed is True
        assert result.wait_seconds == 0

    def test_ut_rl_06_preflight_returns_budget(self):
        """UT-RL-06: Preflight returns correct budget_total from config."""
        rl = RateLimiter(tier="free", state_path=_tmp_state_path())
        rl.load_state()
        result = rl.preflight_check("claude_ai", "REGULAR")
        expected_total = RATE_LIMITS["claude_ai"]["free"]["REGULAR"].max_requests
        assert result.budget_total == expected_total

    def test_ut_rl_07_preflight_unknown_platform_allows(self):
        """UT-RL-07: Unknown platform is allowed by default."""
        rl = RateLimiter(state_path=_tmp_state_path())
        rl.load_state()
        result = rl.preflight_check("unknown_platform_xyz", "REGULAR")
        assert result.allowed is True

    def test_ut_rl_08_cooldown_blocks_immediate_reuse(self):
        """UT-RL-08: After recording usage, cooldown blocks immediate reuse."""
        path = _tmp_state_path()
        rl = RateLimiter(tier="free", state_path=path)
        rl.load_state()

        # Record a usage just now
        rl.record_usage("claude_ai", "REGULAR", STATUS_COMPLETE, 10.0)

        # Immediately check — should be blocked by cooldown
        result = rl.preflight_check("claude_ai", "REGULAR")
        assert result.allowed is False
        assert result.wait_seconds > 0
        assert "Cooldown" in result.reason


class TestRecordUsage:
    """Tests for record_usage()."""

    def test_ut_rl_09_record_creates_state_entry(self):
        """UT-RL-09: record_usage creates platform state entry."""
        rl = RateLimiter(state_path=_tmp_state_path())
        rl.load_state()
        assert "chatgpt" not in rl._state

        rl.record_usage("chatgpt", "REGULAR", STATUS_COMPLETE, 15.0)
        assert "chatgpt" in rl._state
        assert len(rl._state["chatgpt"].recent_requests) == 1
        assert rl._state["chatgpt"].recent_requests[0]["status"] == STATUS_COMPLETE

    def test_ut_rl_10_rate_limited_increments_counter(self):
        """UT-RL-10: Recording a rate_limited status increments consecutive counter."""
        rl = RateLimiter(state_path=_tmp_state_path())
        rl.load_state()

        rl.record_usage("claude_ai", "REGULAR", STATUS_RATE_LIMITED, 5.0)
        assert rl._state["claude_ai"].consecutive_rate_limits == 1

        rl.record_usage("claude_ai", "REGULAR", STATUS_RATE_LIMITED, 5.0)
        assert rl._state["claude_ai"].consecutive_rate_limits == 2

    def test_ut_rl_11_success_resets_rate_limit_counter(self):
        """UT-RL-11: A successful run resets the consecutive rate limit counter."""
        rl = RateLimiter(state_path=_tmp_state_path())
        rl.load_state()

        rl.record_usage("claude_ai", "REGULAR", STATUS_RATE_LIMITED, 5.0)
        rl.record_usage("claude_ai", "REGULAR", STATUS_RATE_LIMITED, 5.0)
        assert rl._state["claude_ai"].consecutive_rate_limits == 2

        rl.record_usage("claude_ai", "REGULAR", STATUS_COMPLETE, 10.0)
        assert rl._state["claude_ai"].consecutive_rate_limits == 0


class TestStaggeredOrder:
    """Tests for get_staggered_order()."""

    def test_ut_rl_12_stagger_returns_all_platforms(self):
        """UT-RL-12: get_staggered_order returns all requested platforms."""
        rl = RateLimiter(state_path=_tmp_state_path())
        rl.load_state()
        platforms = ["claude_ai", "chatgpt", "perplexity"]
        order = rl.get_staggered_order(platforms, "REGULAR")
        returned_names = [name for name, _delay in order]
        assert set(returned_names) == set(platforms)

    def test_ut_rl_13_stagger_delays_are_incremental(self):
        """UT-RL-13: Stagger delays increase incrementally."""
        rl = RateLimiter(state_path=_tmp_state_path())
        rl.load_state()
        platforms = ["claude_ai", "chatgpt", "perplexity"]
        order = rl.get_staggered_order(platforms, "REGULAR", stagger_delay=5)
        delays = [delay for _name, delay in order]
        assert delays[0] == 0.0
        assert delays[1] == 5.0
        assert delays[2] == 10.0

    def test_ut_rl_14_rate_limited_platform_gets_lower_priority(self):
        """UT-RL-14: A recently rate-limited platform is deprioritized."""
        rl = RateLimiter(state_path=_tmp_state_path())
        rl.load_state()

        # Record rate limiting for claude_ai
        rl.record_usage("claude_ai", "REGULAR", STATUS_RATE_LIMITED, 5.0)
        rl.record_usage("claude_ai", "REGULAR", STATUS_RATE_LIMITED, 5.0)

        platforms = ["claude_ai", "chatgpt", "perplexity"]
        order = rl.get_staggered_order(platforms, "REGULAR")
        ordered_names = [name for name, _delay in order]

        # claude_ai should NOT be first since it has consecutive rate limits
        assert ordered_names[0] != "claude_ai", (
            f"Rate-limited platform should not be first, got order: {ordered_names}"
        )
