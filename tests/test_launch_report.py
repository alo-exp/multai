"""Unit tests for launch_report.py.

Tests TC-LAUNCH-1 / IT-LR-01 and IT-LR-02.
"""

import socket
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
LAUNCH_SCRIPT = PROJECT_ROOT / "skills" / "landscape-researcher" / "launch_report.py"


class TestLaunchReport:
    """Tests for launch_report.py CLI."""

    def test_tc_launch_1_no_browser_outputs_url(self):
        """TC-LAUNCH-1 / IT-LR-01: --no-browser outputs preview URL and exits 0."""
        result = subprocess.run(
            [
                sys.executable, str(LAUNCH_SCRIPT),
                "--report-dir", "test-dir",
                "--report-file", "Test Report.md",
                "--no-browser",
            ],
            capture_output=True, text=True,
            cwd=str(PROJECT_ROOT),
            timeout=30,
        )
        # The script should exit 0 (it starts a server or finds one already running)
        assert result.returncode == 0, (
            f"Expected exit code 0, got {result.returncode}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        # URL should contain the encoded report path
        assert "preview.html?report=test-dir/Test%20Report.md" in result.stdout, (
            f"Expected preview URL in stdout, got:\n{result.stdout}"
        )

    def test_it_lr_02_port_already_in_use(self):
        """IT-LR-02: When port is occupied, script handles it gracefully (no crash)."""
        # Bind a socket to port 7789 (use non-default to avoid conflicts)
        test_port = 7789
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("localhost", test_port))
            sock.listen(1)

            result = subprocess.run(
                [
                    sys.executable, str(LAUNCH_SCRIPT),
                    "--report-dir", "test-dir",
                    "--report-file", "Test Report.md",
                    "--port", str(test_port),
                    "--no-browser",
                ],
                capture_output=True, text=True,
                cwd=str(PROJECT_ROOT),
                timeout=30,
            )
            # Should not crash — either reuses the port or reports it's in use
            assert result.returncode == 0, (
                f"Expected exit code 0, got {result.returncode}\n"
                f"stdout: {result.stdout}\nstderr: {result.stderr}"
            )
            # Should mention port is already in use
            assert "already in use" in result.stdout.lower() or "preview.html" in result.stdout, (
                f"Expected port-in-use message or URL in stdout:\n{result.stdout}"
            )
        finally:
            sock.close()
