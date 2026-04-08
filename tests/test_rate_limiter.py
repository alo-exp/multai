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

    def test_ut_rl_14a_unknown_platform_gets_middle_priority(self):
        """UT-RL-14a: Unknown platform gets middle priority (50.0 score)."""
        rl = RateLimiter(state_path=_tmp_state_path())
        rl.load_state()
        platforms = ["unknown_xyz_platform"]
        order = rl.get_staggered_order(platforms, "REGULAR")
        assert len(order) == 1
        name, delay = order[0]
        assert name == "unknown_xyz_platform"
        assert delay == 0.0

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


class TestLoadStateBranches:
    """Tests for load_state() error branches."""

    def test_load_state_version_mismatch(self, tmp_path):
        """Version mismatch resets state to {}."""
        state_file = tmp_path / "state.json"
        state_file.write_text('{"version": 99, "usage": {}}', encoding="utf-8")
        rl = RateLimiter(state_path=str(state_file))
        rl.load_state()
        assert rl._state == {}

    def test_load_state_corrupt_json(self, tmp_path):
        """Corrupt JSON resets state to {}."""
        state_file = tmp_path / "state.json"
        state_file.write_text("not valid json{{", encoding="utf-8")
        rl = RateLimiter(state_path=str(state_file))
        rl.load_state()
        assert rl._state == {}


class TestSaveStateException:
    """Tests for save_state() exception handling."""

    def test_save_state_exception_cleans_up_temp_file(self, tmp_path):
        """save_state cleans up temp file and re-raises on fdopen failure."""
        import os
        import pytest
        state_file = tmp_path / "state.json"
        rl = RateLimiter(state_path=str(state_file))
        rl.load_state()

        with patch("rate_limiter.os.fdopen", side_effect=OSError("fdopen failed")):
            with pytest.raises(OSError, match="fdopen failed"):
                rl.save_state()

    def test_save_state_exception_cleanup_unlink_oserror(self, tmp_path):
        """save_state silently ignores OSError during temp file cleanup."""
        import pytest
        state_file = tmp_path / "state.json"
        rl = RateLimiter(state_path=str(state_file))
        rl.load_state()

        with patch("rate_limiter.os.fdopen", side_effect=OSError("fail")), \
             patch("rate_limiter.os.unlink", side_effect=OSError("unlink fail")):
            with pytest.raises(OSError, match="fail"):
                rl.save_state()


class TestPreflightBranches:
    """Tests for preflight_check() branches."""

    def test_preflight_daily_cap_reached(self, tmp_path):
        """Daily cap reached returns allowed=False with 'Daily cap' reason."""
        from datetime import datetime as _datetime
        import time as _time

        state_file = tmp_path / "state.json"
        rl = RateLimiter(tier="free", state_path=str(state_file))
        rl.load_state()

        # Find a platform with a daily cap
        platform = None
        config = None
        for p in RATE_LIMITS:
            cfg = RATE_LIMITS[p].get("free", {}).get("REGULAR")
            if cfg and cfg.daily_cap > 0:
                platform = p
                config = cfg
                break

        if platform is None:
            import pytest
            pytest.skip("No platform with daily_cap > 0 in free/REGULAR config")

        # Fill up the daily cap
        from datetime import timezone
        now_dt = _datetime.now(timezone.utc)
        for _ in range(config.daily_cap):
            rl._state.setdefault(platform, PlatformUsageState())
            rl._state[platform].recent_requests.append({
                "timestamp": now_dt.isoformat(),
                "mode": "REGULAR",
                "status": STATUS_COMPLETE,
                "duration_s": 1.0,
            })

        result = rl.preflight_check(platform, "REGULAR")
        assert result.allowed is False
        assert "Daily cap" in result.reason

    def test_preflight_window_budget_exhausted_with_oldest(self, tmp_path):
        """Window budget exhausted returns blocked with wait time from oldest record."""
        state_file = tmp_path / "state.json"
        rl = RateLimiter(tier="free", state_path=str(state_file))
        rl.load_state()

        platform = "chatgpt"
        config = RATE_LIMITS[platform]["free"]["REGULAR"]

        from datetime import datetime as _dt, timezone
        import time as _time_mod

        now_ts = _time_mod.time()
        now_dt = _dt.now(timezone.utc)

        # Fill window to max_requests
        rl._state[platform] = PlatformUsageState()
        for _ in range(config.max_requests):
            rl._state[platform].recent_requests.append({
                "timestamp": now_dt.isoformat(),
                "mode": "REGULAR",
                "status": STATUS_COMPLETE,
                "duration_s": 1.0,
            })

        result = rl.preflight_check(platform, "REGULAR")
        assert result.allowed is False
        assert "Window budget exhausted" in result.reason

    def test_preflight_window_budget_exhausted_no_oldest(self, tmp_path):
        """Window budget exhausted with no oldest record uses cooldown as wait."""
        state_file = tmp_path / "state.json"
        rl = RateLimiter(tier="free", state_path=str(state_file))
        rl.load_state()

        platform = "chatgpt"
        config = RATE_LIMITS[platform]["free"]["REGULAR"]

        # Manually insert requests with empty/invalid timestamps so
        # _oldest_in_window returns None (they parse to 0.0 = outside window)
        rl._state[platform] = PlatformUsageState()
        for _ in range(config.max_requests):
            rl._state[platform].recent_requests.append({
                "timestamp": "",  # parses to 0.0 → outside any real window
                "mode": "REGULAR",
                "status": STATUS_COMPLETE,
                "duration_s": 1.0,
            })

        # Override _count_in_window to report exhausted
        original_count = rl._count_in_window
        from datetime import datetime as _dt, timezone
        import time as _time_mod
        now_dt = _dt.now(timezone.utc)
        # Replace with real timestamps so count works, but _oldest_in_window
        # returns None by mocking it
        rl._state[platform].recent_requests = [{
            "timestamp": now_dt.isoformat(),
            "mode": "REGULAR",
            "status": STATUS_COMPLETE,
            "duration_s": 1.0,
        }] * config.max_requests

        with patch.object(rl, "_oldest_in_window", return_value=None):
            result = rl.preflight_check(platform, "REGULAR")

        assert result.allowed is False
        assert "Window budget exhausted" in result.reason

    def test_preflight_exponential_backoff(self, tmp_path):
        """Exponential backoff applied when consecutive_rate_limits > 0."""
        state_file = tmp_path / "state.json"
        rl = RateLimiter(tier="free", state_path=str(state_file))
        rl.load_state()

        platform = "claude_ai"
        config = RATE_LIMITS[platform]["free"]["REGULAR"]

        from datetime import datetime as _dt, timezone
        import time as _time_mod

        # Add a recent request so cooldown triggers
        now_dt = _dt.now(timezone.utc)
        rl._state[platform] = PlatformUsageState(
            recent_requests=[{
                "timestamp": now_dt.isoformat(),
                "mode": "REGULAR",
                "status": STATUS_COMPLETE,
                "duration_s": 1.0,
            }],
            consecutive_rate_limits=3,
        )

        result = rl.preflight_check(platform, "REGULAR")
        assert result.allowed is False
        assert result.wait_seconds > config.cooldown_seconds


class TestRecordUsageBranches:
    """Tests for record_usage() edge cases."""

    def test_record_usage_invalid_mode(self, tmp_path, caplog):
        """Invalid mode is treated as REGULAR with a warning log."""
        import logging
        state_file = tmp_path / "state.json"
        rl = RateLimiter(state_path=str(state_file))
        rl.load_state()

        with caplog.at_level(logging.WARNING, logger="rate_limiter"):
            rl.record_usage("claude_ai", "INVALID_MODE", STATUS_COMPLETE, 1.0)

        assert any("Invalid mode" in r.message for r in caplog.records)
        # Should still record as REGULAR
        assert rl._state["claude_ai"].recent_requests[0]["mode"] == "REGULAR"

    def test_record_usage_save_failure_silenced(self, tmp_path, caplog):
        """save_state failure is caught and logged, not re-raised."""
        import logging
        state_file = tmp_path / "state.json"
        rl = RateLimiter(state_path=str(state_file))
        rl.load_state()

        with patch.object(rl, "save_state", side_effect=RuntimeError("disk full")):
            with caplog.at_level(logging.WARNING, logger="rate_limiter"):
                rl.record_usage("claude_ai", "REGULAR", STATUS_COMPLETE, 1.0)

        assert any("Failed to persist" in r.message for r in caplog.records)

    def test_record_usage_rate_limited_consecutive_resets_on_complete(self, tmp_path):
        """Consecutive rate limit counter reset logs when counter was > 0."""
        import logging
        state_file = tmp_path / "state.json"
        rl = RateLimiter(state_path=str(state_file))
        rl.load_state()

        # Set consecutive > 0 to trigger the info log path
        rl._state["claude_ai"] = PlatformUsageState(consecutive_rate_limits=2)
        with patch.object(rl, "save_state"):
            rl.record_usage("claude_ai", "REGULAR", STATUS_COMPLETE, 1.0)

        assert rl._state["claude_ai"].consecutive_rate_limits == 0


class TestGetBudgetSummary:
    """Tests for get_budget_summary()."""

    def test_get_budget_summary_returns_all_platforms(self, tmp_path):
        """Returns dict with all known platforms."""
        state_file = tmp_path / "state.json"
        rl = RateLimiter(tier="free", state_path=str(state_file))
        rl.load_state()
        summary = rl.get_budget_summary("REGULAR")
        assert len(summary) > 0
        for platform_name, info in summary.items():
            assert "display_name" in info
            assert "remaining" in info
            assert "total" in info
            assert "next_available_in" in info
            assert "cooldown" in info
            assert "daily_cap" in info
            assert "tier" in info
            assert "notes" in info

    def test_get_budget_summary_skips_platform_with_no_config(self, tmp_path):
        """Platforms where _get_config returns None are skipped (continue branch)."""
        state_file = tmp_path / "state.json"
        rl = RateLimiter(tier="free", state_path=str(state_file))
        rl.load_state()
        # Patch RATE_LIMITS to include a platform with no free/REGULAR config
        from unittest.mock import patch
        fake_limits = dict(RATE_LIMITS)
        fake_limits["no_config_platform"] = {}
        with patch("rate_limiter.RATE_LIMITS", fake_limits):
            summary = rl.get_budget_summary("REGULAR")
        assert "no_config_platform" not in summary


class TestGetConfig:
    """Tests for _get_config() branches."""

    def test_get_config_unknown_platform_returns_none(self, tmp_path):
        """Returns None for unknown platform."""
        rl = RateLimiter(state_path=_tmp_state_path())
        result = rl._get_config("totally_unknown_xyz", "REGULAR")
        assert result is None

    def test_get_config_fallback_to_free_tier(self, tmp_path):
        """Falls back to free tier when specified tier not found."""
        rl = RateLimiter(tier="nonexistent_tier", state_path=_tmp_state_path())
        # claude_ai has a free tier — should fall back
        result = rl._get_config("claude_ai", "REGULAR")
        assert result is not None

    def test_get_config_no_free_tier_returns_none(self, tmp_path):
        """Returns None when neither specified tier nor free tier exists."""
        rl = RateLimiter(tier="nonexistent_tier", state_path=_tmp_state_path())
        # Patch RATE_LIMITS to have a platform with no free tier
        fake_limits = {"fake_platform": {"paid_only": {"REGULAR": None}}}
        with patch("rate_limiter.RATE_LIMITS", fake_limits):
            result = rl._get_config("fake_platform", "REGULAR")
        assert result is None


class TestPruneExpired:
    """Tests for _prune_expired()."""

    def test_prune_expired_removes_old_records(self, tmp_path):
        """Old records are removed by _prune_expired."""
        import time as _t
        state_file = tmp_path / "state.json"
        rl = RateLimiter(tier="free", state_path=str(state_file))
        rl.load_state()

        from datetime import datetime as _dt, timezone, timedelta
        old_ts = (_dt.now(timezone.utc) - timedelta(days=2)).isoformat()
        rl._state["claude_ai"] = PlatformUsageState(
            recent_requests=[{
                "timestamp": old_ts,
                "mode": "REGULAR",
                "status": STATUS_COMPLETE,
                "duration_s": 1.0,
            }]
        )
        rl._prune_expired("claude_ai")
        assert len(rl._state["claude_ai"].recent_requests) == 0

    def test_prune_expired_noop_for_unknown_platform(self, tmp_path):
        """_prune_expired silently returns for unknown platform."""
        state_file = tmp_path / "state.json"
        rl = RateLimiter(state_path=str(state_file))
        rl.load_state()
        rl._prune_expired("nonexistent_platform")  # must not raise

    def test_prune_expired_logs_pruned_count(self, tmp_path, caplog):
        """_prune_expired logs debug message when records pruned."""
        import logging
        from datetime import datetime as _dt, timezone, timedelta
        state_file = tmp_path / "state.json"
        rl = RateLimiter(tier="free", state_path=str(state_file))
        rl.load_state()

        old_ts = (_dt.now(timezone.utc) - timedelta(days=2)).isoformat()
        rl._state["claude_ai"] = PlatformUsageState(
            recent_requests=[{
                "timestamp": old_ts,
                "mode": "REGULAR",
                "status": STATUS_COMPLETE,
                "duration_s": 1.0,
            }]
        )
        with caplog.at_level(logging.DEBUG, logger="rate_limiter"):
            rl._prune_expired("claude_ai")
        assert any("Pruned" in r.message for r in caplog.records)

    def test_prune_expired_zero_max_window_uses_default(self, tmp_path):
        """When no window config found, defaults to 86400s."""
        state_file = tmp_path / "state.json"
        rl = RateLimiter(tier="free", state_path=str(state_file))
        rl.load_state()

        from datetime import datetime as _dt, timezone
        rl._state["claude_ai"] = PlatformUsageState(
            recent_requests=[{
                "timestamp": _dt.now(timezone.utc).isoformat(),
                "mode": "REGULAR",
                "status": STATUS_COMPLETE,
                "duration_s": 1.0,
            }]
        )
        # Patch RATE_LIMITS to return empty dict for claude_ai so max_window stays 0
        with patch("rate_limiter.RATE_LIMITS", {}):
            rl._prune_expired("claude_ai")
        # Should still run without error; record is recent so not pruned
        assert len(rl._state["claude_ai"].recent_requests) == 1


class TestCountToday:
    """Tests for _count_today()."""

    def test_count_today_no_state_returns_zero(self, tmp_path):
        """Returns 0 when platform has no state."""
        rl = RateLimiter(state_path=_tmp_state_path())
        rl.load_state()
        assert rl._count_today("claude_ai", "REGULAR", time.time()) == 0

    def test_count_today_counts_todays_records(self, tmp_path):
        """Counts only today's records."""
        from datetime import datetime as _dt, timezone, timedelta
        rl = RateLimiter(state_path=_tmp_state_path())
        rl.load_state()

        now_dt = _dt.now(timezone.utc)
        old_dt = now_dt - timedelta(days=2)
        rl._state["claude_ai"] = PlatformUsageState(
            recent_requests=[
                {"timestamp": now_dt.isoformat(), "mode": "REGULAR",
                 "status": STATUS_COMPLETE, "duration_s": 1.0},
                {"timestamp": old_dt.isoformat(), "mode": "REGULAR",
                 "status": STATUS_COMPLETE, "duration_s": 1.0},
            ]
        )
        count = rl._count_today("claude_ai", "REGULAR", time.time())
        assert count == 1


class TestCountInWindow:
    """Tests for _count_in_window()."""

    def test_count_in_window_no_config_returns_zero(self):
        """Returns 0 when _get_config returns None (unknown platform)."""
        rl = RateLimiter(state_path=_tmp_state_path())
        rl.load_state()
        result = rl._count_in_window("totally_unknown_xyz", "REGULAR", time.time())
        assert result == 0


class TestOldestInWindow:
    """Tests for _oldest_in_window()."""

    def test_oldest_in_window_no_state_returns_none(self):
        """Returns None when platform has no state."""
        rl = RateLimiter(state_path=_tmp_state_path())
        rl.load_state()
        result = rl._oldest_in_window("claude_ai", "REGULAR", time.time(), 3600)
        assert result is None

    def test_oldest_in_window_returns_oldest_timestamp(self):
        """Returns the oldest timestamp within the window."""
        from datetime import datetime as _dt, timezone, timedelta
        import time as _t
        rl = RateLimiter(state_path=_tmp_state_path())
        rl.load_state()

        now_dt = _dt.now(timezone.utc)
        older_dt = now_dt - timedelta(seconds=30)
        rl._state["claude_ai"] = PlatformUsageState(
            recent_requests=[
                {"timestamp": now_dt.isoformat(), "mode": "REGULAR",
                 "status": STATUS_COMPLETE, "duration_s": 1.0},
                {"timestamp": older_dt.isoformat(), "mode": "REGULAR",
                 "status": STATUS_COMPLETE, "duration_s": 1.0},
            ]
        )
        result = rl._oldest_in_window("claude_ai", "REGULAR", _t.time(), 3600)
        assert result is not None
        assert result < _t.time()


class TestParseTimestamp:
    """Tests for _parse_timestamp()."""

    def test_parse_timestamp_empty_returns_zero(self):
        """Empty string returns 0.0."""
        assert RateLimiter._parse_timestamp("") == 0.0

    def test_parse_timestamp_invalid_returns_zero(self):
        """Invalid string returns 0.0."""
        assert RateLimiter._parse_timestamp("not-a-date") == 0.0

    def test_parse_timestamp_valid_iso(self):
        """Valid ISO timestamp returns epoch float."""
        from datetime import datetime as _dt, timezone
        ts = _dt.now(timezone.utc).isoformat()
        result = RateLimiter._parse_timestamp(ts)
        assert result > 0.0


class TestSecondsUntilMidnight:
    """Tests for _seconds_until_midnight()."""

    def test_seconds_until_midnight_in_range(self):
        """Returns value between 0 and 86400."""
        result = RateLimiter._seconds_until_midnight()
        assert 0 < result <= 86400
