"""Unit tests for config module.

Tests UT-CF-01 through UT-CF-08.
"""

import sys
from pathlib import Path

# Add engine directory to sys.path for bare imports
sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "orchestrator" / "engine"))

from config import (
    PLATFORM_URLS,
    TIMEOUTS,
    RATE_LIMITS,
    STAGGER_DELAY,
    DEFAULT_TIER,
    POLL_INTERVAL,
    RateLimitConfig,
)


class TestConfigValues:
    """Tests for config module constants."""

    def test_ut_cf_01_platform_urls_has_seven_entries(self):
        """UT-CF-01: PLATFORM_URLS has 7 platform entries."""
        assert len(PLATFORM_URLS) == 7, f"Expected 7 platform URLs, got {len(PLATFORM_URLS)}"

    def test_ut_cf_02_platform_urls_are_https(self):
        """UT-CF-02: All platform URLs start with https://."""
        for name, url in PLATFORM_URLS.items():
            assert url.startswith("https://"), (
                f"Platform {name} URL should start with https://, got: {url}"
            )

    def test_ut_cf_03_timeouts_has_seven_entries(self):
        """UT-CF-03: TIMEOUTS has 7 entries matching platforms."""
        assert len(TIMEOUTS) == 7, f"Expected 7 timeout entries, got {len(TIMEOUTS)}"

    def test_ut_cf_04_timeouts_deep_gte_regular(self):
        """UT-CF-04: Deep timeout >= regular timeout for all platforms."""
        for name, tc in TIMEOUTS.items():
            assert tc.deep >= tc.regular, (
                f"Platform {name}: deep timeout ({tc.deep}) should be >= "
                f"regular timeout ({tc.regular})"
            )

    def test_ut_cf_05_default_tier_is_free(self):
        """UT-CF-05: DEFAULT_TIER is 'free'."""
        assert DEFAULT_TIER == "free"

    def test_ut_cf_06_stagger_delay_positive(self):
        """UT-CF-06: STAGGER_DELAY is a positive integer."""
        assert isinstance(STAGGER_DELAY, int)
        assert STAGGER_DELAY > 0

    def test_ut_cf_07_rate_limits_structure(self):
        """UT-CF-07: RATE_LIMITS has correct nested structure for all platforms."""
        assert len(RATE_LIMITS) == 7, f"Expected 7 rate limit entries, got {len(RATE_LIMITS)}"
        for platform, tiers in RATE_LIMITS.items():
            assert "free" in tiers, f"Platform {platform} missing 'free' tier"
            for tier_name, modes in tiers.items():
                assert "REGULAR" in modes, (
                    f"Platform {platform}/{tier_name} missing 'REGULAR' mode"
                )
                assert "DEEP" in modes, (
                    f"Platform {platform}/{tier_name} missing 'DEEP' mode"
                )
                for mode_name, cfg in modes.items():
                    assert isinstance(cfg, RateLimitConfig), (
                        f"Platform {platform}/{tier_name}/{mode_name} should be RateLimitConfig"
                    )
                    assert cfg.max_requests > 0
                    assert cfg.window_seconds > 0
                    assert cfg.cooldown_seconds >= 0

    def test_ut_cf_08_poll_interval_positive(self):
        """UT-CF-08: POLL_INTERVAL is a positive number."""
        assert isinstance(POLL_INTERVAL, (int, float))
        assert POLL_INTERVAL > 0
