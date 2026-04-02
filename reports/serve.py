#!/usr/bin/env python3
"""Minimal HTTP server for preview.html — reads PORT from env var."""
import os
import pathlib
import http.server
import socketserver

# Serve from this file's directory (reports/)
os.chdir(pathlib.Path(__file__).parent)

PORT = int(os.environ.get("PORT", 7788))

class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass  # suppress access logs

with socketserver.TCPServer(("", PORT), Handler) as httpd:
    httpd.serve_forever()
