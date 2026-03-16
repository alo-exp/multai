#!/usr/bin/env python3
"""
launch_report.py — Landscape Researcher Report Launcher

Starts the preview HTTP server (if not already running) and opens the browser
to the correct report URL with a ?report= query parameter.

Usage:
    python3 skills/landscape-researcher/launch_report.py \
        --report-dir "market-landscape-20260316-1430" \
        --report-file "Platform Engineering Solutions - Market Landscape Report.md" \
        [--port 7788] \
        [--no-browser]
"""

import argparse
import os
import pathlib
import socket
import subprocess
import sys
import time
import urllib.parse
import webbrowser


def find_workspace_root(start: pathlib.Path) -> pathlib.Path:
    """Walk up from start until we find a directory containing 'reports/'."""
    current = start.resolve()
    for _ in range(10):  # Safety: don't walk up more than 10 levels
        if (current / "reports").is_dir():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    raise RuntimeError(
        f"Could not find workspace root (directory containing 'reports/') "
        f"starting from {start}. Run this script from within the multi-ai-skills/ tree."
    )


def is_port_in_use(port: int) -> bool:
    """Return True if something is already listening on the given port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", port)) == 0


def start_server(reports_dir: pathlib.Path, port: int) -> None:
    """Start python3 -m http.server as a detached background daemon."""
    print(f"Starting HTTP server on port {port} (serving {reports_dir}) ...")
    subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--directory", str(reports_dir)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,  # Detach from parent process group
    )
    # Give the server a moment to bind
    time.sleep(1.2)
    if not is_port_in_use(port):
        raise RuntimeError(
            f"Server failed to start on port {port}. "
            f"Check that python3 -m http.server works in {reports_dir}."
        )
    print(f"Server running at http://localhost:{port}/")


def build_url(port: int, report_dir: str, report_file: str) -> str:
    """Build the preview URL with the ?report= query parameter."""
    # URL-encode the combined path (handles spaces and special chars in filenames)
    report_path = f"{report_dir}/{report_file}"
    encoded_path = urllib.parse.quote(report_path, safe="/")
    return f"http://localhost:{port}/preview.html?report={encoded_path}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Start the preview server and open the report in the browser."
    )
    parser.add_argument(
        "--report-dir",
        required=True,
        help="Subdirectory under reports/ containing the report "
             "(e.g., 'market-landscape-20260316-1430')",
    )
    parser.add_argument(
        "--report-file",
        required=True,
        help="Report filename (e.g., 'Platform Engineering Solutions - Market Landscape Report.md')",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=7788,
        help="HTTP server port (default: 7788)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Print the URL but do not open the browser",
    )
    args = parser.parse_args()

    # Resolve workspace root
    script_dir = pathlib.Path(__file__).parent
    workspace_root = find_workspace_root(script_dir)
    reports_dir = workspace_root / "reports"

    # Verify the report file actually exists
    report_path = reports_dir / args.report_dir / args.report_file
    if not report_path.exists():
        print(
            f"WARNING: Report file not found at {report_path}\n"
            f"The server will still start, but the report may not load correctly.",
            file=sys.stderr,
        )

    # Start server if port is not already in use
    if is_port_in_use(args.port):
        print(f"Port {args.port} already in use — assuming server is running.")
    else:
        start_server(reports_dir, args.port)

    # Build and output the URL
    url = build_url(args.port, args.report_dir, args.report_file)
    print(f"\n{'='*60}")
    print(f"  Report URL:")
    print(f"  {url}")
    print(f"{'='*60}\n")

    # Open the browser
    if not args.no_browser:
        print("Opening browser ...")
        webbrowser.open(url)


if __name__ == "__main__":
    main()
