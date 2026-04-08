"""Unit tests for status_writer.py."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

ENGINE_DIR = str(Path(__file__).parent.parent / "skills" / "orchestrator" / "engine")
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

from status_writer import write_status


def _make_result(**kwargs):
    defaults = {
        "platform": "test",
        "display_name": "Test Platform",
        "status": "complete",
        "chars": 1000,
        "file": "/tmp/test.md",
        "mode_used": "REGULAR",
        "error": "",
        "duration_s": 5.0,
    }
    defaults.update(kwargs)
    return defaults


class TestWriteStatus:
    """Tests for write_status()."""

    def test_write_status_creates_json(self, tmp_path):
        """write_status creates status.json with correct structure."""
        results = [_make_result()]
        write_status(results, str(tmp_path), "REGULAR")
        status_file = tmp_path / "status.json"
        assert status_file.exists()
        data = json.loads(status_file.read_text(encoding="utf-8"))
        assert "timestamp" in data
        assert data["mode"] == "REGULAR"
        assert "platforms" in data
        assert data["platforms"] == results

    def test_write_status_prints_table(self, tmp_path, capsys):
        """write_status prints ORCHESTRATION COMPLETE header."""
        results = [_make_result()]
        write_status(results, str(tmp_path), "REGULAR")
        captured = capsys.readouterr()
        assert "ORCHESTRATION COMPLETE" in captured.out

    def test_write_status_counts_complete(self, tmp_path, capsys):
        """write_status shows correct complete/total count."""
        results = [
            _make_result(status="complete"),
            _make_result(display_name="Platform 2", status="complete"),
            _make_result(display_name="Platform 3", status="failed"),
        ]
        write_status(results, str(tmp_path), "REGULAR")
        captured = capsys.readouterr()
        assert "2/3" in captured.out

    def test_write_status_handles_zero_chars(self, tmp_path, capsys):
        """write_status displays '-' for chars=0."""
        results = [_make_result(chars=0)]
        write_status(results, str(tmp_path), "REGULAR")
        captured = capsys.readouterr()
        # chars=0 is falsy -> displayed as '-'
        assert "-" in captured.out

    def test_write_status_handles_zero_duration(self, tmp_path, capsys):
        """write_status displays '-' for duration_s=0."""
        results = [_make_result(duration_s=0)]
        write_status(results, str(tmp_path), "REGULAR")
        captured = capsys.readouterr()
        assert "-" in captured.out

    def test_write_status_shows_error_in_notes(self, tmp_path, capsys):
        """write_status shows error in notes column when error is set."""
        results = [_make_result(status="failed", error="Timeout", mode_used="")]
        write_status(results, str(tmp_path), "REGULAR")
        captured = capsys.readouterr()
        assert "Timeout" in captured.out

    def test_write_status_shows_mode_in_notes(self, tmp_path, capsys):
        """write_status shows mode_used in notes when no error."""
        results = [_make_result(error="", mode_used="DEEP")]
        write_status(results, str(tmp_path), "REGULAR")
        captured = capsys.readouterr()
        assert "DEEP" in captured.out

    def test_write_status_multiple_results(self, tmp_path, capsys):
        """write_status handles multiple results correctly."""
        results = [
            _make_result(display_name="Claude.ai", chars=5000, duration_s=10.0),
            _make_result(display_name="ChatGPT", chars=3000, duration_s=8.5),
        ]
        write_status(results, str(tmp_path), "DEEP")
        captured = capsys.readouterr()
        assert "Claude.ai" in captured.out
        assert "ChatGPT" in captured.out
        assert "DEEP" in captured.out
