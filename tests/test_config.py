"""Unit tests for config module.

Tests UT-CF-01 through UT-CF-10 plus detect_chrome_* function coverage.
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add engine directory to sys.path for bare imports
sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "orchestrator" / "engine"))

from config import (
    PLATFORM_URLS,
    PLATFORM_URL_DOMAINS,
    TIMEOUTS,
    RATE_LIMITS,
    STAGGER_DELAY,
    DEFAULT_TIER,
    POLL_INTERVAL,
    STATUS_NEEDS_LOGIN,
    STATUS_ICONS,
    RateLimitConfig,
    detect_chrome_executable,
    detect_chrome_user_data_dir,
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

    def test_ut_cf_09_platform_url_domains_has_seven_entries(self):
        """UT-CF-09: PLATFORM_URL_DOMAINS has 7 entries matching PLATFORM_URLS."""
        assert len(PLATFORM_URL_DOMAINS) == 7, (
            f"Expected 7 URL domain entries, got {len(PLATFORM_URL_DOMAINS)}"
        )
        assert set(PLATFORM_URL_DOMAINS.keys()) == set(PLATFORM_URLS.keys()), (
            "PLATFORM_URL_DOMAINS keys must match PLATFORM_URLS keys"
        )

    def test_ut_cf_10_status_needs_login_has_icon(self):
        """UT-CF-10: STATUS_NEEDS_LOGIN is defined and has an entry in STATUS_ICONS."""
        assert STATUS_NEEDS_LOGIN == "needs_login"
        assert STATUS_NEEDS_LOGIN in STATUS_ICONS, (
            "STATUS_NEEDS_LOGIN must have an icon in STATUS_ICONS"
        )


def _load_real_config():
    """Load the real config module directly by file path, bypassing sys.modules stubs."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_real_config",
        str(Path(__file__).parent.parent / "skills" / "orchestrator" / "engine" / "config.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestDetectChromeFunctions:
    """Tests for detect_chrome_executable and detect_chrome_user_data_dir (lines 12-22, 29-37)."""

    def test_detect_chrome_executable_darwin(self):
        """Returns macOS Chrome path on Darwin."""
        _cfg_mod = _load_real_config()
        with patch.object(_cfg_mod._platform, "system", return_value="Darwin"):
            result = _cfg_mod.detect_chrome_executable()
        assert "Google Chrome" in result
        assert result.endswith("Google Chrome")

    def test_detect_chrome_executable_linux_found(self):
        """Returns first found Linux Chrome binary."""
        _cfg_mod = _load_real_config()
        with patch.object(_cfg_mod._platform, "system", return_value="Linux"), \
             patch.object(_cfg_mod.Path, "exists", return_value=True):
            result = _cfg_mod.detect_chrome_executable()
        assert "google-chrome" in result or "chromium" in result

    def test_detect_chrome_executable_linux_not_found(self):
        """Falls back to 'google-chrome' when no binary found on Linux."""
        _cfg_mod = _load_real_config()
        with patch.object(_cfg_mod._platform, "system", return_value="Linux"), \
             patch.object(_cfg_mod.Path, "exists", return_value=False):
            result = _cfg_mod.detect_chrome_executable()
        assert result == "google-chrome"

    def test_detect_chrome_executable_windows(self):
        """Returns Windows Chrome path on Windows."""
        _cfg_mod = _load_real_config()
        with patch.object(_cfg_mod._platform, "system", return_value="Windows"):
            result = _cfg_mod.detect_chrome_executable()
        assert "chrome.exe" in result

    def test_detect_chrome_executable_unknown(self):
        """Falls back to 'google-chrome' on unknown platform."""
        _cfg_mod = _load_real_config()
        with patch.object(_cfg_mod._platform, "system", return_value="FreeBSD"):
            result = _cfg_mod.detect_chrome_executable()
        assert result == "google-chrome"

    def test_detect_chrome_user_data_dir_darwin(self):
        """Returns macOS Chrome user data dir on Darwin."""
        _cfg_mod = _load_real_config()
        with patch.object(_cfg_mod._platform, "system", return_value="Darwin"):
            result = _cfg_mod.detect_chrome_user_data_dir()
        assert "Library" in result
        assert "Google" in result
        assert "Chrome" in result

    def test_detect_chrome_user_data_dir_linux(self):
        """Returns Linux Chrome user data dir."""
        _cfg_mod = _load_real_config()
        with patch.object(_cfg_mod._platform, "system", return_value="Linux"):
            result = _cfg_mod.detect_chrome_user_data_dir()
        assert "google-chrome" in result

    def test_detect_chrome_user_data_dir_windows(self):
        """Returns Windows Chrome user data dir."""
        _cfg_mod = _load_real_config()
        with patch.object(_cfg_mod._platform, "system", return_value="Windows"):
            result = _cfg_mod.detect_chrome_user_data_dir()
        assert "Chrome" in result
        assert "User Data" in result

    def test_detect_chrome_user_data_dir_unknown(self):
        """Falls back to ~/.config/google-chrome on unknown platform."""
        _cfg_mod = _load_real_config()
        with patch.object(_cfg_mod._platform, "system", return_value="FreeBSD"):
            result = _cfg_mod.detect_chrome_user_data_dir()
        assert "google-chrome" in result
