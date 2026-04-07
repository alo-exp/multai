"""Write orchestration status.json and print the summary table."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from config import STATUS_ICONS

log = logging.getLogger(__name__)


def write_status(results: list[dict], output_dir: str, mode: str) -> None:
    """Write status.json and print summary table."""
    status_path = Path(output_dir) / "status.json"
    status_data = {
        "timestamp": datetime.now().isoformat(),
        "mode": mode,
        "platforms": results,
    }
    status_path.write_text(json.dumps(status_data, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info(f"Status written to {status_path}")

    print("\n" + "=" * 80)
    print(f"  ORCHESTRATION COMPLETE — {mode} mode")
    print("=" * 80)
    print(f"  {'Platform':<20} {'Status':<12} {'Chars':>8}  {'Time':>8}  Notes")
    print("-" * 80)
    for r in results:
        icon = STATUS_ICONS.get(r["status"], "?")
        name = r["display_name"]
        status = f"{icon} {r['status']}"
        chars = f"{r['chars']:,}" if r["chars"] else "-"
        time_s = f"{r['duration_s']:.0f}s" if r["duration_s"] else "-"
        notes = r.get("error", "") or r.get("mode_used", "")
        print(f"  {name:<20} {status:<12} {chars:>8}  {time_s:>8}  {notes}")
    print("=" * 80)

    complete = sum(1 for r in results if r["status"] == "complete")
    total = len(results)
    print(f"\n  {complete}/{total} platforms completed successfully.")
    print(f"  Raw responses saved to: {output_dir}/")
    print(f"  Status file: {status_path}\n")
