"""Unit tests for chrome_selectors module — CSS selector constants."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "orchestrator" / "engine" / "platforms"))

from chrome_selectors import PLATFORM_CHROME, PLATFORM_ORDER, PLATFORM_DISPLAY


class TestChromeSelectors:
    """Tests for chrome_selectors constants."""

    def test_platform_chrome_has_seven_platforms(self):
        """PLATFORM_CHROME defines selectors for all 7 platforms."""
        assert len(PLATFORM_CHROME) == 7

    def test_platform_chrome_each_has_required_keys(self):
        """Each platform entry has url, input_sel, submit_sel, input_type, login_signals."""
        required_keys = {"url", "input_sel", "submit_sel", "input_type", "login_signals"}
        for name, cfg in PLATFORM_CHROME.items():
            assert required_keys.issubset(cfg.keys()), (
                f"{name} missing keys: {required_keys - cfg.keys()}"
            )

    def test_platform_order_has_seven_entries(self):
        """PLATFORM_ORDER has 7 entries matching PLATFORM_CHROME keys."""
        assert len(PLATFORM_ORDER) == 7
        assert set(PLATFORM_ORDER) == set(PLATFORM_CHROME.keys())

    def test_platform_display_has_seven_entries(self):
        """PLATFORM_DISPLAY has 7 display name entries."""
        assert len(PLATFORM_DISPLAY) == 7
        assert set(PLATFORM_DISPLAY.keys()) == set(PLATFORM_CHROME.keys())
