"""Unit tests for launch_report.py.

Tests all functions: find_workspace_root, is_port_in_use, start_server,
ensure_chart_data_skeleton, build_url, main.
"""

import json
import socket
import sys
import webbrowser
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add landscape-researcher to sys.path
LANDSCAPE_DIR = str(Path(__file__).parent.parent / "skills" / "landscape-researcher")
if LANDSCAPE_DIR not in sys.path:
    sys.path.insert(0, LANDSCAPE_DIR)

import launch_report as lr


class TestFindWorkspaceRoot:
    """Tests for find_workspace_root()."""

    def test_find_workspace_root_success(self, tmp_path):
        """Returns path when reports/ subdir exists."""
        (tmp_path / "reports").mkdir()
        result = lr.find_workspace_root(tmp_path)
        assert result == tmp_path.resolve()

    def test_find_workspace_root_in_child(self, tmp_path):
        """Walks up from child dir to find reports/."""
        (tmp_path / "reports").mkdir()
        child = tmp_path / "subdir" / "deeper"
        child.mkdir(parents=True)
        result = lr.find_workspace_root(child)
        assert result == tmp_path.resolve()

    def test_find_workspace_root_failure(self, tmp_path):
        """Raises RuntimeError when no reports/ found."""
        import pytest
        # Use a temp dir with no reports/ ancestor
        isolated = tmp_path / "isolated"
        isolated.mkdir()
        with pytest.raises(RuntimeError, match="Could not find workspace root"):
            lr.find_workspace_root(isolated)

    def test_find_workspace_root_hits_fs_root(self):
        """Raises RuntimeError when filesystem root is reached (parent == current)."""
        import pytest
        # Start from filesystem root itself — parent == current immediately
        root = Path("/")
        with pytest.raises(RuntimeError, match="Could not find workspace root"):
            lr.find_workspace_root(root)


class TestIsPortInUse:
    """Tests for is_port_in_use()."""

    def test_is_port_in_use_true(self):
        """Returns True when port is occupied."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("localhost", 0))
            sock.listen(1)
            port = sock.getsockname()[1]
            assert lr.is_port_in_use(port) is True
        finally:
            sock.close()

    def test_is_port_in_use_false(self):
        """Returns False when port is free."""
        # Find a free port by binding then closing
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("localhost", 0))
        port = sock.getsockname()[1]
        sock.close()
        # Port is now free
        assert lr.is_port_in_use(port) is False


class TestStartServer:
    """Tests for start_server()."""

    def test_start_server_success(self, tmp_path):
        """Popen is called and server binds successfully."""
        with patch("launch_report.subprocess.Popen") as mock_popen, \
             patch("launch_report.time.sleep"), \
             patch("launch_report.is_port_in_use", return_value=True):
            lr.start_server(tmp_path, 19876)
        mock_popen.assert_called_once()

    def test_start_server_failure(self, tmp_path):
        """Raises RuntimeError when server fails to start."""
        import pytest
        with patch("launch_report.subprocess.Popen"), \
             patch("launch_report.time.sleep"), \
             patch("launch_report.is_port_in_use", return_value=False):
            with pytest.raises(RuntimeError, match="Server failed to start"):
                lr.start_server(tmp_path, 19877)


class TestEnsureChartDataSkeleton:
    """Tests for ensure_chart_data_skeleton()."""

    def test_ensure_chart_data_skeleton_creates(self, tmp_path):
        """Creates chart-data.json when it doesn't exist."""
        lr.ensure_chart_data_skeleton(tmp_path, "Test Report.md")
        chart_path = tmp_path / "chart-data.json"
        assert chart_path.exists()
        data = json.loads(chart_path.read_text())
        assert "mq_data" in data
        assert "wave_data" in data

    def test_ensure_chart_data_skeleton_noop(self, tmp_path):
        """Does not overwrite existing chart-data.json."""
        chart_path = tmp_path / "chart-data.json"
        chart_path.write_text('{"existing": true}')
        lr.ensure_chart_data_skeleton(tmp_path, "Test Report.md")
        data = json.loads(chart_path.read_text())
        assert data == {"existing": True}

    def test_ensure_chart_data_skeleton_creates_dir(self, tmp_path):
        """Creates parent directory if it doesn't exist."""
        new_dir = tmp_path / "new_report_dir"
        lr.ensure_chart_data_skeleton(new_dir, "Report.md")
        assert (new_dir / "chart-data.json").exists()


class TestBuildUrl:
    """Tests for build_url()."""

    def test_build_url_basic(self):
        """Returns correct URL format."""
        url = lr.build_url(7788, "my-dir", "My Report.md")
        assert url == "http://localhost:7788/preview.html?report=my-dir/My%20Report.md"

    def test_build_url_encodes_special_chars(self):
        """Encodes spaces and special characters in path."""
        url = lr.build_url(8080, "dir name", "file name.md")
        assert "dir%20name" in url
        assert "file%20name.md" in url


class TestMain:
    """Tests for main()."""

    def _make_args(self, tmp_path, no_browser=True):
        (tmp_path / "reports").mkdir(exist_ok=True)
        return [
            "--report-dir", "test-dir",
            "--report-file", "Test Report.md",
            "--port", "17890",
            *(["--no-browser"] if no_browser else []),
        ]

    def test_main_no_browser(self, tmp_path, capsys):
        """--no-browser: webbrowser.open NOT called."""
        (tmp_path / "reports").mkdir(exist_ok=True)
        with patch("launch_report.find_workspace_root", return_value=tmp_path), \
             patch("launch_report.is_port_in_use", return_value=True), \
             patch("launch_report.ensure_chart_data_skeleton"), \
             patch("launch_report.webbrowser.open") as mock_open, \
             patch("sys.argv", ["launch_report.py",
                                "--report-dir", "test-dir",
                                "--report-file", "Test.md",
                                "--no-browser"]):
            lr.main()
        mock_open.assert_not_called()

    def test_main_with_browser(self, tmp_path):
        """Without --no-browser: webbrowser.open IS called."""
        (tmp_path / "reports").mkdir(exist_ok=True)
        with patch("launch_report.find_workspace_root", return_value=tmp_path), \
             patch("launch_report.is_port_in_use", return_value=True), \
             patch("launch_report.ensure_chart_data_skeleton"), \
             patch("launch_report.webbrowser.open") as mock_open, \
             patch("sys.argv", ["launch_report.py",
                                "--report-dir", "test-dir",
                                "--report-file", "Test.md"]):
            lr.main()
        mock_open.assert_called_once()

    def test_main_report_not_found_warns(self, tmp_path, capsys):
        """Prints WARNING to stderr when report file not found."""
        (tmp_path / "reports").mkdir(exist_ok=True)
        with patch("launch_report.find_workspace_root", return_value=tmp_path), \
             patch("launch_report.is_port_in_use", return_value=True), \
             patch("launch_report.ensure_chart_data_skeleton"), \
             patch("launch_report.webbrowser.open"), \
             patch("sys.argv", ["launch_report.py",
                                "--report-dir", "nonexistent-dir",
                                "--report-file", "Missing.md",
                                "--no-browser"]):
            lr.main()
        captured = capsys.readouterr()
        assert "WARNING" in captured.err

    def test_main_starts_server_when_port_free(self, tmp_path):
        """Calls start_server when port is not in use."""
        (tmp_path / "reports").mkdir(exist_ok=True)
        with patch("launch_report.find_workspace_root", return_value=tmp_path), \
             patch("launch_report.is_port_in_use", return_value=False), \
             patch("launch_report.start_server") as mock_start, \
             patch("launch_report.ensure_chart_data_skeleton"), \
             patch("launch_report.webbrowser.open"), \
             patch("sys.argv", ["launch_report.py",
                                "--report-dir", "test-dir",
                                "--report-file", "Test.md",
                                "--no-browser"]):
            lr.main()
        mock_start.assert_called_once()
