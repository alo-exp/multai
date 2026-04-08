"""Unit tests for collate_responses module.

Tests UT-CR-01 through UT-CR-09.
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

# Add engine directory to sys.path for bare imports
sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "orchestrator" / "engine"))

from collate_responses import collate

FIXTURES = Path(__file__).parent / "fixtures"

# The 5 fixture raw response files
_RAW_FILES = [
    "Claude.ai-raw-response.md",
    "ChatGPT-raw-response.md",
    "Perplexity-raw-response.md",
    "DeepSeek-raw-response.md",
    "Google-Gemini-raw-response.md",
]


def _setup_tmpdir_with_fixtures() -> str:
    """Create a tmp dir with the 5 raw response files and status.json."""
    tmpdir = tempfile.mkdtemp(prefix="collate-test-")
    for fname in _RAW_FILES:
        shutil.copy2(str(FIXTURES / fname), str(Path(tmpdir) / fname))
    shutil.copy2(str(FIXTURES / "sample-status.json"), str(Path(tmpdir) / "status.json"))
    return tmpdir


class TestCollate:
    """Tests for collate()."""

    def test_ut_cr_01_archive_created_and_ordering(self):
        """UT-CR-01: Archive is created and Claude.ai appears before Google-Gemini."""
        tmpdir = _setup_tmpdir_with_fixtures()
        result = collate(tmpdir, "Test Task")
        assert result is not None, "collate() should return a Path"
        assert result.exists(), f"Archive file should exist at {result}"

        content = result.read_text(encoding="utf-8")
        claude_pos = content.find("Claude.ai")
        gemini_pos = content.find("Google Gemini")
        assert claude_pos >= 0, "Claude.ai should appear in archive"
        assert gemini_pos >= 0, "Google Gemini should appear in archive"
        assert claude_pos < gemini_pos, (
            f"Claude.ai (pos {claude_pos}) should appear before "
            f"Google Gemini (pos {gemini_pos})"
        )

    def test_ut_cr_02_archive_filename_contains_task_name(self):
        """UT-CR-02: Archive filename includes the task name."""
        tmpdir = _setup_tmpdir_with_fixtures()
        result = collate(tmpdir, "My Research Task")
        assert result is not None
        assert "My Research Task" in result.name

    def test_ut_cr_03_archive_contains_all_platforms(self):
        """UT-CR-03: Archive contains all 5 platform sections."""
        tmpdir = _setup_tmpdir_with_fixtures()
        result = collate(tmpdir, "Test Task")
        content = result.read_text(encoding="utf-8")
        for name in ["Claude.ai", "ChatGPT", "Perplexity", "DeepSeek", "Google Gemini"]:
            assert name in content, f"Archive should contain {name}"

    def test_ut_cr_04_empty_dir_returns_none(self):
        """UT-CR-04: Empty directory returns None."""
        tmpdir = tempfile.mkdtemp(prefix="collate-empty-")
        result = collate(tmpdir, "Empty Task")
        assert result is None

    def test_ut_cr_05_archive_header_contains_task_name(self):
        """UT-CR-05: Archive header line contains the task name."""
        tmpdir = _setup_tmpdir_with_fixtures()
        result = collate(tmpdir, "Solution Analysis")
        content = result.read_text(encoding="utf-8")
        assert "# Solution Analysis" in content

    def test_ut_cr_06_archive_contains_platform_count(self):
        """UT-CR-06: Archive header shows correct platform count (5/5 successful)."""
        tmpdir = _setup_tmpdir_with_fixtures()
        result = collate(tmpdir, "Test Task")
        content = result.read_text(encoding="utf-8")
        assert "5/5 successful" in content

    def test_ut_cr_07_archive_includes_response_content(self):
        """UT-CR-07: Archive includes the actual response content from fixture files."""
        tmpdir = _setup_tmpdir_with_fixtures()
        result = collate(tmpdir, "Test Task")
        content = result.read_text(encoding="utf-8")
        # Each fixture file has "Executive Summary"
        assert "Executive Summary" in content
        assert "Feature A: Yes" in content

    def test_ut_cr_08_metadata_from_status_json(self):
        """UT-CR-08: status.json metadata (chars, duration) flows into archive sections."""
        tmpdir = _setup_tmpdir_with_fixtures()
        result = collate(tmpdir, "Test Task")
        content = result.read_text(encoding="utf-8")
        # Status.json has chars: 5432 for Claude.ai — should appear as "5,432 chars"
        assert "5,432 chars" in content, (
            "Claude.ai metadata (5,432 chars) should appear in archive"
        )
        # Status.json has mode: REGULAR — should appear in header
        assert "**Mode:** REGULAR" in content

    def test_ut_cr_09_status_json_timestamp_in_header(self):
        """UT-CR-09: status.json timestamp appears in archive header."""
        tmpdir = _setup_tmpdir_with_fixtures()
        result = collate(tmpdir, "Test Task")
        content = result.read_text(encoding="utf-8")
        # Fixture has timestamp: "2026-03-15T21:28:00" → formatted as "2026-03-15 21:28"
        assert "2026-03-15 21:28" in content, (
            "Timestamp from status.json should be formatted in archive header"
        )

    def test_ut_cr_10_invalid_status_json_graceful(self):
        """Lines 72-73: Invalid status.json is handled gracefully — archive still created."""
        tmpdir = _setup_tmpdir_with_fixtures()
        # Overwrite status.json with invalid content
        (Path(tmpdir) / "status.json").write_text("NOT VALID JSON {{{", encoding="utf-8")
        result = collate(tmpdir, "Test Task")
        assert result is not None, "Should still create archive even with corrupt status.json"
        assert result.exists()

    def test_ut_cr_11_invalid_timestamp_falls_back(self):
        """Lines 79-80: Non-ISO timestamp in status.json falls back to raw string."""
        tmpdir = _setup_tmpdir_with_fixtures()
        import json as _json
        status = _json.loads((Path(tmpdir) / "status.json").read_text())
        status["timestamp"] = "NOT_A_TIMESTAMP"
        (Path(tmpdir) / "status.json").write_text(_json.dumps(status))
        result = collate(tmpdir, "Test Task")
        content = result.read_text(encoding="utf-8")
        assert "NOT_A_TIMESTAMP" in content

    def test_ut_cr_12_file_read_error_shown_in_archive(self):
        """Lines 111-112: Unreadable response file — error message appears in archive."""
        tmpdir = _setup_tmpdir_with_fixtures()
        # Patch Path.read_text to raise only for raw-response.md files
        from unittest.mock import patch
        original_read = Path.read_text

        def patched_read(self, *args, **kw):
            if "raw-response" in str(self):
                raise OSError("permission denied")
            return original_read(self, *args, **kw)

        with patch.object(Path, "read_text", patched_read):
            result = collate(tmpdir, "Test Task")

        content = result.read_text(encoding="utf-8")
        assert "ERROR reading file" in content

    def test_ut_cr_13_non_complete_status_shown_in_meta(self):
        """Line 126: Platform with non-complete status shows status in metadata."""
        import json as _json
        tmpdir = _setup_tmpdir_with_fixtures()
        status = _json.loads((Path(tmpdir) / "status.json").read_text())
        # Set Claude.ai status to "timeout"
        for plat in status.get("platforms", []):
            if "Claude.ai" in plat.get("file", ""):
                plat["status"] = "timeout"
                break
        (Path(tmpdir) / "status.json").write_text(_json.dumps(status))
        result = collate(tmpdir, "Test Task")
        content = result.read_text(encoding="utf-8")
        assert "status: timeout" in content


class TestCollateMain:
    """Tests for collate_responses.main() — lines 173-181."""

    def test_main_no_args_exits_1(self):
        """Lines 173-175: main() with no args prints usage and exits 1."""
        import sys
        from unittest.mock import patch
        from collate_responses import main
        with patch.object(sys, "argv", ["collate_responses.py"]), \
             pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1

    def test_main_with_empty_dir_exits_1(self, tmp_path):
        """Lines 176-181: main() with empty dir exits 1 (no raw files)."""
        import sys
        from unittest.mock import patch
        from collate_responses import main
        with patch.object(sys, "argv", ["collate_responses.py", str(tmp_path)]), \
             pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1

    def test_main_with_valid_dir_exits_0(self, tmp_path):
        """Lines 176-181: main() with valid dir exits 0."""
        import sys, shutil
        from unittest.mock import patch
        from collate_responses import main
        # Set up a valid directory
        for fname in _RAW_FILES:
            shutil.copy2(str(FIXTURES / fname), str(tmp_path / fname))
        with patch.object(sys, "argv", ["collate_responses.py", str(tmp_path), "My Task"]), \
             pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
