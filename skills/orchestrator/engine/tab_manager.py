"""Tab state persistence, Chrome data dir setup, and existing-tab discovery."""

from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path

from config import PLATFORM_URL_DOMAINS

log = logging.getLogger(__name__)

_TAB_STATE_FILE = Path.home() / ".chrome-playwright" / "tab-state.json"


def _load_tab_state() -> dict:
    """Load the persisted mapping of platform_name -> last known tab URL."""
    if _TAB_STATE_FILE.exists():
        try:
            return json.loads(_TAB_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_tab_state(tab_state: dict) -> None:
    """Persist the mapping of platform_name -> current tab URL."""
    _TAB_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _TAB_STATE_FILE.write_text(
        json.dumps(tab_state, indent=2, ensure_ascii=False), encoding="utf-8"
    )


async def _find_existing_tab(context, platform_name: str):
    """Search open Chrome tabs for a page belonging to this platform.

    Matches by PLATFORM_URL_DOMAINS substring in the page URL.
    Returns the Page if found, None otherwise.
    """
    domain = PLATFORM_URL_DOMAINS.get(platform_name, "")
    if not domain:
        return None
    for page in context.pages:
        if domain in page.url:
            return page
    return None


def _ensure_playwright_data_dir(real_chrome_dir: str, profile_name: str) -> str:
    """Create a persistent non-default data dir with COPIED login files.

    WHY: Chrome blocks --remote-debugging-pipe (used by Playwright) and
    --remote-debugging-port when user_data_dir IS Chrome's actual default
    profile path. By using a different directory, Chrome sees a non-default
    path. We COPY essential login files (Cookies, Login Data, Local Storage,
    etc.) from the real profile so that existing sessions are available on
    first launch.

    The macOS keychain key is user-scoped, not path-scoped, so cookie
    decryption works from any data directory. The directory is PERSISTENT
    so Chrome can be left running between orchestrator runs.
    """
    pw_dir = Path.home() / ".chrome-playwright"
    pw_dir.mkdir(parents=True, exist_ok=True)
    pw_dir.chmod(0o700)

    profile_dst = pw_dir / profile_name
    profile_src = Path(real_chrome_dir) / profile_name

    if profile_dst.is_symlink():
        log.info("Removing stale profile symlink — switching to copy-based approach")
        profile_dst.unlink()

    profile_dst.mkdir(parents=True, exist_ok=True)

    _LOGIN_FILES = [
        "Cookies", "Cookies-journal",
        "Web Data", "Web Data-journal",
        "Extension Cookies", "Extension Cookies-journal",
        "Preferences", "Secure Preferences",
    ]
    _LOGIN_DIRS = ["Local Storage", "Session Storage", "IndexedDB"]

    for fname in _LOGIN_FILES:
        src = profile_src / fname
        dst = profile_dst / fname
        if not src.exists():
            continue
        if fname.startswith("Cookies"):
            if not dst.exists() or os.path.getmtime(str(src)) > os.path.getmtime(str(dst)):
                shutil.copy2(str(src), str(dst))
                log.debug(f"Copied {fname} from real profile")
        else:
            if not dst.exists():
                shutil.copy2(str(src), str(dst))
                log.debug(f"Copied {fname} from real profile (first run)")

    for dname in _LOGIN_DIRS:
        src = profile_src / dname
        dst = profile_dst / dname
        if src.is_dir() and not dst.exists():
            shutil.copytree(str(src), str(dst), dirs_exist_ok=True)
            log.debug(f"Copied {dname}/ from real profile (first run)")

    ls_src = os.path.join(real_chrome_dir, "Local State")
    ls_dst = pw_dir / "Local State"
    if os.path.exists(ls_src):
        if not ls_dst.exists() or os.path.getmtime(ls_src) > os.path.getmtime(str(ls_dst)):
            shutil.copy2(ls_src, str(ls_dst))

    return str(pw_dir)
