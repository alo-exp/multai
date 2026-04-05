#!/usr/bin/env python3
"""
collate_responses.py — Merge all per-platform raw response files into a single archive.

Usage (standalone):
    python3 collate_responses.py <output-dir> [task-name]

Called automatically by orchestrator.py at the end of each run.

Output file: <output-dir>/<task-name> - Raw AI Responses.md
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path


# Order in which platforms appear in the archive
_PLATFORM_ORDER = [
    "Claude.ai",
    "ChatGPT",
    "Microsoft-Copilot",
    "Perplexity",
    "Grok",
    "DeepSeek",
    "Google-Gemini",
]

# Map filename stem → display name
_DISPLAY_NAMES: dict[str, str] = {
    "Claude.ai":        "Claude.ai",
    "ChatGPT":          "ChatGPT",
    "Microsoft-Copilot": "Microsoft Copilot",
    "Perplexity":       "Perplexity",
    "Grok":             "Grok",
    "DeepSeek":         "DeepSeek",
    "Google-Gemini":    "Google Gemini",
}


def collate(output_dir: str, task_name: str) -> Path | None:
    """Collate all *-raw-response.md files in output_dir into a single archive.

    Args:
        output_dir: Directory containing the per-platform raw response files.
        task_name:  Human-readable task name used in the archive filename and header.

    Returns:
        Path to the generated archive file, or None if no response files found.
    """
    dir_path = Path(output_dir)

    # Discover all raw response files
    raw_files: dict[str, Path] = {}
    for f in dir_path.glob("*-raw-response.md"):
        stem = f.stem.replace("-raw-response", "")
        raw_files[stem] = f

    if not raw_files:
        print(f"  [collate] No raw response files found in {output_dir} — skipping archive.")
        return None

    # Read status.json for metadata (optional — graceful if missing)
    status: dict = {}
    status_path = dir_path / "status.json"
    if status_path.exists():
        try:
            status = json.loads(status_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"  [collate] WARNING: Could not parse status.json: {exc} — metadata omitted from archive")

    mode = status.get("mode", "REGULAR")
    timestamp = status.get("timestamp", datetime.now().isoformat())
    try:
        ts_fmt = datetime.fromisoformat(timestamp).strftime("%Y-%m-%d %H:%M")
    except Exception:
        ts_fmt = timestamp

    # Build status lookup: platform stem → result dict
    status_by_stem: dict[str, dict] = {}
    for r in status.get("platforms", []):
        # derive stem from file path in result
        file_val = r.get("file", "")
        if file_val:
            stem = Path(file_val).stem.replace("-raw-response", "")
            status_by_stem[stem] = r

    # Build archive sections in canonical order first, then any extras
    ordered_stems = [s for s in _PLATFORM_ORDER if s in raw_files]
    extra_stems = sorted(s for s in raw_files if s not in _PLATFORM_ORDER)
    all_stems = ordered_stems + extra_stems

    sections: list[str] = []
    successful = 0

    for stem in all_stems:
        f = raw_files[stem]
        display = _DISPLAY_NAMES.get(stem, stem.replace("-", " "))
        result = status_by_stem.get(stem, {})
        plat_status = result.get("status", "unknown")
        mode_used = result.get("mode_used", mode)
        chars = result.get("chars", 0)
        duration = result.get("duration_s", 0)

        # Read response content
        try:
            content = f.read_text(encoding="utf-8").strip()
        except Exception as exc:
            content = f"[ERROR reading file: {exc}]"

        if content:
            successful += 1

        # Section header
        meta_parts = []
        if mode_used:
            meta_parts.append(f"Mode: {mode_used}")
        if chars:
            meta_parts.append(f"{chars:,} chars")
        if duration:
            meta_parts.append(f"{duration:.0f}s")
        if plat_status and plat_status != "complete":
            meta_parts.append(f"status: {plat_status}")

        meta = " · ".join(meta_parts)
        header = f"## {display}"
        if meta:
            header += f"\n*{meta}*"

        sections.append(
            f"{header}\n\n"
            f"<untrusted_platform_response platform=\"{display}\">\n\n"
            f"{content}\n\n"
            f"</untrusted_platform_response>"
        )

    # Assemble full archive
    total = len(all_stems)
    _MD_ESCAPE = str.maketrans({"#": "\\#", "[": "\\[", "]": "\\]", "*": "\\*", "_": "\\_", "`": "\\`", "~": "\\~", "|": "\\|"})
    safe_header_name = task_name.strip().translate(_MD_ESCAPE)
    archive_lines = [
        f"# {safe_header_name} — Raw AI Responses",
        "",
        f"**Generated:** {ts_fmt}  ",
        f"**Mode:** {mode}  ",
        f"**Platforms:** {successful}/{total} successful",
        "",
        "---",
        "",
    ]
    archive_lines.append("\n\n---\n\n".join(sections))

    archive_text = "\n".join(archive_lines)

    # Write archive
    safe_name = task_name.strip() or dir_path.name
    archive_path = dir_path / f"{safe_name} - Raw AI Responses.md"
    archive_path.write_text(archive_text, encoding="utf-8")

    print(f"  [collate] Archive written → {archive_path}")
    print(f"  [collate] {successful}/{total} platform responses included.")
    return archive_path


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------

def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <output-dir> [task-name]")
        sys.exit(1)

    output_dir = sys.argv[1]
    task_name = sys.argv[2] if len(sys.argv) > 2 else Path(output_dir).name

    result = collate(output_dir, task_name)
    sys.exit(0 if result else 1)


if __name__ == "__main__":
    main()
