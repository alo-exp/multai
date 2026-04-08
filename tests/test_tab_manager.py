"""Unit tests for tab_manager.py."""

import json
import os
import sys
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ENGINE_DIR = str(Path(__file__).parent.parent / "skills" / "orchestrator" / "engine")
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

import tab_manager
from tab_manager import (
    _load_tab_state,
    _save_tab_state,
    _find_existing_tab,
    _ensure_playwright_data_dir,
)
from config import PLATFORM_URL_DOMAINS


class TestLoadTabState:
    """Tests for _load_tab_state."""

    def test_load_tab_state_no_file(self, tmp_path):
        """Returns {} when tab state file does not exist."""
        fake_path = tmp_path / "nonexistent.json"
        with patch.object(tab_manager, "_TAB_STATE_FILE", fake_path):
            result = _load_tab_state()
        assert result == {}

    def test_load_tab_state_valid_json(self, tmp_path):
        """Returns loaded dict when file contains valid JSON."""
        state = {"chatgpt": "https://chat.openai.com/chat/123"}
        state_file = tmp_path / "tab-state.json"
        state_file.write_text(json.dumps(state), encoding="utf-8")
        with patch.object(tab_manager, "_TAB_STATE_FILE", state_file):
            result = _load_tab_state()
        assert result == state

    def test_load_tab_state_corrupt_json(self, tmp_path):
        """Returns {} when file contains invalid JSON."""
        state_file = tmp_path / "tab-state.json"
        state_file.write_text("not valid json {{{", encoding="utf-8")
        with patch.object(tab_manager, "_TAB_STATE_FILE", state_file):
            result = _load_tab_state()
        assert result == {}


class TestSaveTabState:
    """Tests for _save_tab_state."""

    def test_save_tab_state(self, tmp_path):
        """Persists tab state to file correctly."""
        state_file = tmp_path / "sub" / "tab-state.json"
        state = {"claude_ai": "https://claude.ai/chat/abc"}
        with patch.object(tab_manager, "_TAB_STATE_FILE", state_file):
            _save_tab_state(state)
        assert state_file.exists()
        saved = json.loads(state_file.read_text(encoding="utf-8"))
        assert saved == state


class TestFindExistingTab:
    """Tests for _find_existing_tab."""

    def test_find_existing_tab_found(self):
        """Returns matching page when platform domain found in URL."""
        import asyncio
        mock_page = MagicMock()
        mock_page.url = "https://claude.ai/new"
        mock_context = MagicMock()
        mock_context.pages = [mock_page]

        result = asyncio.run(_find_existing_tab(mock_context, "claude_ai"))
        assert result is mock_page

    def test_find_existing_tab_not_found(self):
        """Returns None when no page URL matches platform domain."""
        import asyncio
        mock_page = MagicMock()
        mock_page.url = "https://example.com"
        mock_context = MagicMock()
        mock_context.pages = [mock_page]

        result = asyncio.run(_find_existing_tab(mock_context, "claude_ai"))
        assert result is None

    def test_find_existing_tab_no_domain(self):
        """Returns None when platform has no entry in PLATFORM_URL_DOMAINS."""
        import asyncio
        mock_context = MagicMock()
        mock_context.pages = []

        result = asyncio.run(_find_existing_tab(mock_context, "unknown_platform_xyz"))
        assert result is None

    def test_find_existing_tab_multiple_pages(self):
        """Returns correct page when multiple pages open."""
        import asyncio
        mock_page1 = MagicMock()
        mock_page1.url = "https://example.com"
        mock_page2 = MagicMock()
        mock_page2.url = "https://chat.openai.com/chat"
        mock_context = MagicMock()
        mock_context.pages = [mock_page1, mock_page2]

        result = asyncio.run(_find_existing_tab(mock_context, "chatgpt"))
        assert result is mock_page2


class TestEnsurePlaywrightDataDir:
    """Tests for _ensure_playwright_data_dir."""

    def test_creates_pw_dir_with_correct_permissions(self, tmp_path):
        """Creates ~/.chrome-playwright directory with 0o700 permissions."""
        pw_base = tmp_path / ".chrome-playwright"
        src_chrome = tmp_path / "chrome"
        src_chrome.mkdir()
        (src_chrome / "Default").mkdir()

        with patch.object(Path, "home", return_value=tmp_path):
            result = _ensure_playwright_data_dir(str(src_chrome), "Default")

        assert pw_base.exists()
        mode = oct(pw_base.stat().st_mode)[-3:]
        assert mode == "700"
        assert result == str(pw_base)

    def test_copies_cookies_file(self, tmp_path):
        """Copies Cookies file from real Chrome profile to pw dir."""
        src_chrome = tmp_path / "chrome"
        profile_src = src_chrome / "Default"
        profile_src.mkdir(parents=True)
        cookies_file = profile_src / "Cookies"
        cookies_file.write_bytes(b"fake cookies data")

        with patch.object(Path, "home", return_value=tmp_path):
            _ensure_playwright_data_dir(str(src_chrome), "Default")

        pw_dir = tmp_path / ".chrome-playwright"
        assert (pw_dir / "Default" / "Cookies").exists()

    def test_removes_symlink_at_profile_dst(self, tmp_path):
        """Removes stale symlink at profile_dst before creating directory."""
        src_chrome = tmp_path / "chrome"
        (src_chrome / "Default").mkdir(parents=True)
        pw_dir = tmp_path / ".chrome-playwright"
        pw_dir.mkdir()
        profile_dst = pw_dir / "Default"
        # Create a symlink
        profile_dst.symlink_to(tmp_path)

        with patch.object(Path, "home", return_value=tmp_path):
            _ensure_playwright_data_dir(str(src_chrome), "Default")

        # Symlink replaced by real dir
        assert profile_dst.is_dir()
        assert not profile_dst.is_symlink()

    def test_skips_nonexistent_src_file(self, tmp_path):
        """No error when source login file does not exist."""
        src_chrome = tmp_path / "chrome"
        (src_chrome / "Default").mkdir(parents=True)
        # No Cookies file

        with patch.object(Path, "home", return_value=tmp_path):
            _ensure_playwright_data_dir(str(src_chrome), "Default")  # Should not raise

    def test_copies_local_state(self, tmp_path):
        """Copies Local State from chrome dir to pw_dir."""
        src_chrome = tmp_path / "chrome"
        (src_chrome / "Default").mkdir(parents=True)
        local_state = src_chrome / "Local State"
        local_state.write_text('{"os_crypt": {}}', encoding="utf-8")

        with patch.object(Path, "home", return_value=tmp_path):
            _ensure_playwright_data_dir(str(src_chrome), "Default")

        pw_dir = tmp_path / ".chrome-playwright"
        assert (pw_dir / "Local State").exists()

    def test_copies_non_cookie_files_first_run_only(self, tmp_path):
        """Non-cookie files (e.g., Preferences) only copied if dst doesn't exist."""
        src_chrome = tmp_path / "chrome"
        profile_src = src_chrome / "Default"
        profile_src.mkdir(parents=True)
        prefs = profile_src / "Preferences"
        prefs.write_text('{"settings": {}}', encoding="utf-8")

        with patch.object(Path, "home", return_value=tmp_path):
            _ensure_playwright_data_dir(str(src_chrome), "Default")

        pw_dir = tmp_path / ".chrome-playwright"
        assert (pw_dir / "Default" / "Preferences").exists()

    def test_copies_cookies_when_newer(self, tmp_path):
        """Cookies file updated when source is newer than destination."""
        src_chrome = tmp_path / "chrome"
        profile_src = src_chrome / "Default"
        profile_src.mkdir(parents=True)
        cookies_src = profile_src / "Cookies"
        cookies_src.write_bytes(b"new cookies")

        pw_dir = tmp_path / ".chrome-playwright"
        profile_dst = pw_dir / "Default"
        profile_dst.mkdir(parents=True)
        cookies_dst = profile_dst / "Cookies"
        cookies_dst.write_bytes(b"old cookies")

        # Make src newer by modifying mtime
        import time
        os.utime(str(cookies_src), (time.time() + 10, time.time() + 10))

        with patch.object(Path, "home", return_value=tmp_path):
            _ensure_playwright_data_dir(str(src_chrome), "Default")

        assert cookies_dst.read_bytes() == b"new cookies"

    def test_copies_login_dirs(self, tmp_path):
        """Login directories (e.g., Local Storage) copied on first run."""
        src_chrome = tmp_path / "chrome"
        profile_src = src_chrome / "Default"
        local_storage_src = profile_src / "Local Storage"
        local_storage_src.mkdir(parents=True)
        (local_storage_src / "leveldb").mkdir()
        (local_storage_src / "leveldb" / "data.ldb").write_bytes(b"data")

        with patch.object(Path, "home", return_value=tmp_path):
            _ensure_playwright_data_dir(str(src_chrome), "Default")

        pw_dir = tmp_path / ".chrome-playwright"
        assert (pw_dir / "Default" / "Local Storage").is_dir()
