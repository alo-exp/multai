## Code Review: MultAI Engine Pre-Release

**Reviewed:** 2026-04-08  
**Depth:** Standard (full file read, language-specific checks)  
**Files Reviewed:** 18  
**Reviewer:** Claude (gsd-code-reviewer)

---

### Summary

The engine is a well-structured, mature async Python codebase built on Playwright. The split into focused modules (orchestrator, cli, engine_setup, tab_manager, status_writer, prompt_loader, retry_handler, platforms/) is clean and the separation of concerns is sound. Platform-specific logic is properly isolated via mixin-based inheritance (BrowserMixin, InjectMixin, ChatGPTExtractorMixin). The completion-detection strategies are sophisticated and include multiple fallback layers, which is appropriate given the adversarial nature of scraping live AI UIs.

The test suite covers the most complex and fragile paths (rate-limit detection, completion heuristics) using well-structured IsolatedAsyncioTestCase classes with controlled mocks.

Issues found fall into three categories: (1) a hard-coded absolute path in test files that will break on any machine that isn't the author's; (2) several security-relevant patterns around subprocess input, path traversal, and secret handling in the .env parser; (3) a collection of correctness and reliability risks including an unhandled race in the Chrome Preferences write, missing error propagation in the DeepSeek stable-state fallback, a silent-swallow pattern in `_poll_completion` that can loop forever, and a fragile inline CSS class selector used as the only secondary extraction path in `claude_ai.py`.

---

### Critical Issues (🔴)

#### CR-01: Hard-coded absolute path in test files breaks portability

**Files:**  
- `tests/test_chatgpt_rate_limit.py:8`  
- `tests/test_deepseek_completion.py:7`  
- `tests/test_gemini_completion.py:7`

**Issue:** All three test files contain:
```python
sys.path.insert(0, "/Users/shafqat/Documents/Projects/MultAI/skills/orchestrator/engine")
```
This is the developer's personal home directory. Any other developer, CI runner, or deployment path will silently fail to import `tests.conftest`, causing every test to crash with an `ImportError` before a single assertion runs.

**Fix:** Use a path relative to the test file itself:
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
```
Or, better, add a `pyproject.toml` / `setup.cfg` and run tests with `pytest` from the engine root so `sys.path` is managed by the test runner.

---

#### CR-02: Chrome Preferences file overwritten non-atomically — data loss on crash

**File:** `orchestrator.py:247-252`

**Issue:** The Chrome `Preferences` JSON is written back with:
```python
prefs_path.write_text(json.dumps(prefs, ensure_ascii=False), encoding="utf-8")
```
`write_text` is not atomic: if the process is killed, signals, or an exception occurs between the open and close of the file handle, the Preferences file is left truncated or empty. Chrome will then fail to launch on the next run with a corrupted profile.

**Fix:** Write to a temp file in the same directory and rename atomically:
```python
import tempfile, os
with tempfile.NamedTemporaryFile(
    mode="w", encoding="utf-8",
    dir=prefs_path.parent, delete=False, suffix=".tmp"
) as tmp:
    json.dump(prefs, tmp, ensure_ascii=False)
    tmp_path = tmp.name
os.replace(tmp_path, prefs_path)
```

---

### High Issues (🟠)

#### HR-01: `_load_dotenv` strips quotes from values, leaving passwords with embedded quotes silently broken

**File:** `engine_setup.py:28`

**Issue:**
```python
value = value.strip().strip('"').strip("'")
```
This strips ALL leading/trailing quotes, including a single outer pair. A `.env` value like `SECRET="it's alive"` becomes `it's alive` (correct), but `SECRET=it's alive` becomes `its alive` — the apostrophe's surrounding single-quote stripping eats the trailing `e`. More critically, a value like `SECRET='don't'` strips both outer single quotes and leaves `don't` missing both quotes. The parser also does not handle `KEY="value with = sign"` correctly because `partition("=")` is used — this is actually fine, but the quote-stripping is order-dependent and will mangle multi-line or embedded-quote secrets without any warning.

**Fix:** Use a proper quote-aware parser. The stdlib `shlex` module handles this correctly:
```python
import shlex
try:
    value = shlex.split(value)[0]
except ValueError:
    value = value.strip()
```

---

#### HR-02: `_inject_clipboard_paste` exposes full prompt text via system clipboard to any concurrently running process

**File:** `inject_utils.py:48-83`

**Issue:** When `execCommand` fails, the full prompt is written to the system clipboard via `pbcopy`/`xclip`/`clip`. Any application with clipboard access (other Electron apps, password managers, clipboard history tools) can read the entire prompt at the moment of paste. On macOS this is particularly significant because clipboard history apps often persist clipboard contents permanently.

This is an accepted architectural trade-off for this type of automation, but it should be explicitly documented in the code and there should be a best-effort clipboard clear after paste:

**Fix:** After the paste operation completes, clear the clipboard:
```python
# After paste succeeds, clear clipboard to reduce exposure window
if sys.platform == "darwin":
    subprocess.run(["pbcopy"], input=b"", timeout=5)
elif sys.platform == "linux":
    # try xclip/xsel/wl-copy with empty input
    ...
```
And add a doc comment noting the security trade-off explicitly.

---

#### HR-03: `_resolve_output_dir` path-traversal check uses string prefix — bypassable on case-insensitive filesystems

**File:** `cli.py:113-117`

**Issue:**
```python
if not str(resolved).startswith(str(_PROJECT_ROOT)):
```
On macOS (HFS+/APFS case-insensitive) a path like `/Users/shafqat/documents/projects/multai/../../../etc/passwd` resolves to `/etc/passwd` whose string representation does NOT start with the project root — so that case IS caught. However, a path that differs only in case (e.g., `/Users/Shafqat/Documents/Projects/MultAI/../../secret`) will resolve to a path outside the root but whose string prefix check may pass if `_PROJECT_ROOT` was computed with a different case. More concretely: `Path.resolve()` normalises symlinks but not case on macOS. Also, the check passes when `_PROJECT_ROOT` is a prefix of another sibling directory (e.g., project root is `/home/user/multai` and user passes `/home/user/multai-private/...`).

**Fix:** Use `Path.is_relative_to()` (Python 3.9+) which performs a proper path-component comparison:
```python
if not resolved.is_relative_to(_PROJECT_ROOT):
    log.error(...)
    sys.exit(1)
```

---

#### HR-04: `handle_login_retries` mutates `final_results` in-place via index, but index mapping is built before retries; concurrent modification risk

**File:** `retry_handler.py:35-43`

**Issue:** `login_pending` is a list of `(idx, r)` tuples captured before any retries run. The retry loop then does `final_results[idx] = retry`. This is safe only because retries are sequential. However, `handle_agent_fallbacks` is called immediately after and also mutates `final_results` by index using a separately-captured `failed_idxs`. If a retried platform changes from `needs_login` to `failed`, `handle_agent_fallbacks` will NOT pick it up (because `failed_idxs` was built from the original `final_results` before the login retry ran). This is a silent correctness hole: a platform that goes `needs_login → retry → failed` never gets the agent fallback.

**Fix:** Rebuild `failed_idxs` inside `handle_agent_fallbacks` after `handle_login_retries` has completed, or pass the live list by reference and scan it at invocation time (which is already the case for `final_results`, but `failed_idxs` is captured at the top of `handle_agent_fallbacks` before any fallbacks run — the issue only materialises across the two functions). The simplest fix is to call `handle_agent_fallbacks` after all retries have settled and ensure it rescans the list fresh, which it already does — the actual fix needed is in orchestrator.py calling order; it should be documented that these two functions must always be called sequentially with the same `final_results` list, and the retry handler should not hide its mutations.

---

### Medium Issues (🟡)

#### MD-01: `_poll_completion` silently swallows consecutive exceptions and can mask permanent failure states

**File:** `platforms/base.py:268-280`

**Issue:** When `completion_check` raises an exception 5 times in a row, the code attempts an agent fallback. If the agent fallback also raises, the exception propagates — but only after 5 consecutive failures. Between failures 1-4, the exception is silently swallowed with `log.debug(...)`, and the poll loop continues sleeping. If `completion_check` is consistently raising (e.g., page navigated away, browser crashed), the platform will silently spin for the full `max_wait_s` before surfacing an error.

```python
except Exception as exc:
    consecutive_errors += 1
    if consecutive_errors >= 5:
        ...
        raise  # Only raises after 5 consecutive errors
    log.debug(...)  # Swallows 1-4 errors silently
```

**Fix:** At a minimum, escalate log level from `debug` to `warning` after 2-3 consecutive errors so operators see the polling is degraded. Add a hard cap of 10 total consecutive errors regardless of fallback to prevent infinite spin.

---

#### MD-02: `DeepSeek.completion_check` silently passes over the stable-state threshold evaluation when `page.evaluate` raises

**File:** `platforms/deepseek.py:294-309`

**Issue:** The text-growth tracking block wraps the entire threshold check in a bare `except Exception: pass`:
```python
try:
    if self._stable_text_polls >= min_stable_polls and self._prev_text_len > 500:
        ...
        return True
except Exception:
    pass
```
`self._stable_text_polls >= min_stable_polls` cannot raise — this is a plain integer comparison. Wrapping it in a try/except masks the fact that if `page.evaluate` failed (earlier in the block, also caught), `_prev_text_len` is stale and the completion check will never return `True` via this path. The platform will then time out rather than complete normally, producing a `STATUS_TIMEOUT` instead of `STATUS_COMPLETE`.

**Fix:** Move the evaluate call into its own try/except and only fall through to the comparison unconditionally:
```python
try:
    current_text_len = await page.evaluate("() => document.body.innerText.length")
    if current_text_len > self._prev_text_len:
        self._stable_text_polls = 0
        self._prev_text_len = current_text_len
        return False
    else:
        self._stable_text_polls += 1
        self._prev_text_len = current_text_len
except Exception:
    pass  # Can't read page — don't update counters

if self._stable_text_polls >= min_stable_polls and self._prev_text_len > 500:
    return True
```

---

#### MD-03: `claude_ai.py` secondary extraction relies on a fragile compound Tailwind CSS selector

**File:** `platforms/claude_ai.py:302`

**Issue:**
```python
panel = page.locator('.ease-out.duration-200.relative.flex.w-full.flex-1.overflow-x-auto.overflow-y-scroll').first
```
This selector chains 8 Tailwind utility classes. Claude.ai's production build uses content-hash class name mangling in some build configurations, and Tailwind's JIT purge + minification can change or remove these classes across any UI update. This will silently return 0 results after a UI change with no error logged, and the extraction falls through to the next method (which is acceptable), but it also means there is no alerting when this method stops working.

**Fix:** Replace with a semantic selector or add a log entry when this path returns 0 results:
```python
try:
    panel = page.locator('.ease-out.duration-200.relative.flex.w-full.flex-1.overflow-x-auto.overflow-y-scroll').first
    if await panel.count() == 0:
        log.debug("[Claude.ai] Tailwind panel selector returned 0 results — selector may need updating")
    elif ...:
        ...
```
Also consider adding `[data-testid*="artifact-content"]` or `[class*="artifact-content"]` as the primary selector before falling back to utility class chains.

---

#### MD-04: `ChatGPT.post_send` loops for 15s checking for conversation ID but does not break on navigation errors

**File:** `platforms/chatgpt.py:114-121`

**Issue:**
```python
for _ in range(15):
    await page.wait_for_timeout(1000)
    url = page.url
    if "/c/" in url:
        ...
        break
```
If the page navigates to an error page or gets redirected (e.g., ChatGPT shows a "something went wrong" interstitial), `page.url` will not contain `/c/` and this loop runs the full 15 seconds unconditionally. The conversation ID is never captured in this case, but more importantly, the function returns normally rather than raising, so the subsequent `completion_check` runs against an error state it cannot recover from.

**Fix:** Add a navigation check inside the loop:
```python
if await self.is_sign_in_page(page) or not await self.is_chat_ready(page):
    log.warning("[ChatGPT] Page in error/login state while waiting for conversation ID")
    break
```

---

#### MD-05: `_gather_with_timeout` result extraction is incorrect when task raised an exception

**File:** `orchestrator.py:159-164`

**Issue:** The result reconstruction after a timeout cancel:
```python
(task.exception() if not task.cancelled() and task.exception() else task.result())
if task.done() and not task.cancelled()
else asyncio.TimeoutError("Global ceiling exceeded")
```
`task.exception()` re-raises if the task was cancelled (it raises `CancelledError`). The guard `not task.cancelled()` is correct, but `task.exception()` itself raises `InvalidStateError` if the task is not done yet. The outer `task.done()` check prevents the `InvalidStateError` case, so this is fine — but the condition `not task.cancelled() and task.exception()` evaluates `task.exception()` as a boolean. `task.exception()` returns the exception object or `None`; if it's `None` (task completed normally), the expression short-circuits to `task.result()` which is correct. However if the task has not fully cancelled yet (still in the `await asyncio.gather(*async_tasks, return_exceptions=True)` cancellation drain), `task.done()` may be `True` but `task.cancelled()` may also be `True`, meaning we'd fall to the else branch. This path is safe but produces a `TimeoutError` instead of the actual cancellation error.

**Fix:** Simplify to:
```python
results = []
for task in async_tasks:
    if task.cancelled():
        results.append(asyncio.TimeoutError("Global ceiling exceeded"))
    elif task.exception():
        results.append(task.exception())
    else:
        results.append(task.result())
return results
```

---

#### MD-06: `_ensure_playwright_data_dir` copies login cookies without checking if source is locked by Chrome

**File:** `tab_manager.py:91-93`

**Issue:**
```python
if not dst.exists() or os.path.getmtime(str(src)) > os.path.getmtime(str(dst)):
    shutil.copy2(str(src), str(dst))
```
Chrome holds an exclusive lock on its `Cookies` SQLite file while running. `shutil.copy2` on a locked SQLite file on macOS will succeed (macOS does not enforce exclusive file locks at the OS level the way Windows does), but the copy may contain an in-progress WAL (write-ahead log) transaction, leaving the destination database in a potentially inconsistent state. Subsequent Chrome launches against the copied database may fail to decrypt cookies or may silently see an empty cookie store.

**Fix:** Also copy the associated `-journal` and `-wal` files atomically. The code already copies `Cookies-journal` separately, but does not handle `Cookies-wal`. Add `"Cookies-wal"` to `_LOGIN_FILES`. More robustly, check if the source Chrome process is running before copying.

---

### Suggestions (🔵)

#### SG-01: `engine_setup.py` pins exact package versions in `print` messages but not in the `pip install` calls

`_ensure_dependencies` installs `playwright==1.58.0` and `browser-use==0.12.2`. These versions are also printed in warning messages. Consider extracting them to constants at the top of the file to prevent drift between the install command and the warning message, and to make future version bumps a single-line change.

---

#### SG-02: `cli.py:146` only cleans up prompt files under `/tmp/` — other temp paths are not cleaned

The cleanup guard `str(prompt_path).startswith("/tmp/")` is macOS/Linux specific. On macOS, `tempfile.mkstemp()` actually produces paths under `/var/folders/...`, not `/tmp/`. If callers use `tempfile` instead of writing directly to `/tmp`, the file will never be cleaned up. Consider using `prompt_path.parent == Path(tempfile.gettempdir())` or simply always cleaning up if the file still exists after the run and the caller owns it.

---

#### SG-03: `status_writer.py` uses `datetime.now()` — should use `datetime.now(timezone.utc)` for UTC timestamps

**File:** `status_writer.py:19`

```python
"timestamp": datetime.now().isoformat(),
```
This produces a local-time timestamp with no timezone marker, which is ambiguous in `status.json` when the file is shared or read in a different timezone. Use `datetime.now(timezone.utc).isoformat()` to produce an unambiguous ISO 8601 UTC timestamp.

---

#### SG-04: `chatgpt.py` REGULAR mode model selection list includes `"o4"` which does not exist as of April 2026

**File:** `platforms/chatgpt.py:79`

```python
for model_name in ["o3", "o4-mini", "o4", "o3-mini"]:
```
As of April 2026, OpenAI's available reasoning models are `o3`, `o3-mini`, and `o4-mini`. There is no `o4` model. This is a low-priority issue because the fallback to `"Default"` handles it gracefully, but the dead list entry adds noise to logs and could cause confusion if `o4` is eventually released with different characteristics than expected.

---

#### SG-05: `retry_handler.py` login retry countdown uses `asyncio.sleep(10)` in a loop — blocks event loop for 90s

**File:** `retry_handler.py:31-33`

```python
for remaining in range(90, 0, -10):
    log.info(f"  Sign-in retry countdown: {remaining}s remaining...")
    await asyncio.sleep(10)
```
This is functionally correct but prevents any other async operations from running during the 90s wait. In practice, since login retries are sequential and happen after all platform tasks complete, this is acceptable — but it's worth noting that this cannot be parallelised with other work. A single `await asyncio.sleep(90)` is cleaner.

---

#### SG-06: Tests clear sys.modules by matching module name substring — fragile under parallel test execution

**Files:** `tests/test_chatgpt_rate_limit.py:33-36`, `tests/test_deepseek_completion.py:50-53`, `tests/test_gemini_completion.py:49-52`

```python
for mod in list(sys.modules):
    if "chatgpt" in mod:
        del sys.modules[mod]
```
`sys.modules` is a process-global dict. If tests are run in parallel (e.g., `pytest-xdist`), one test deleting a module that another test is actively using will cause intermittent `AttributeError` or `ImportError`. This pattern is also fragile against future third-party packages whose module name happens to contain the platform name substring. Use `importlib.reload()` or isolate stubs per test class with `setUp`/`tearDown` instead.

---

#### SG-07: `inject_utils.py` does not verify that clipboard paste actually landed correct content

**File:** `inject_utils.py:79-83`

After the clipboard paste, the code reads `textContent.length` from the contenteditable to verify. It does not compare the actual pasted text to `prompt`, only the length. If the clipboard was modified between `pbcopy` and the paste (e.g., by a concurrent clipboard-watching process), the wrong content could be injected silently. Add a spot-check of the first and last N characters of the pasted content.

---

### What Looks Good

- **Module decomposition** — The refactor from a monolithic `orchestrator.py` into `cli.py`, `engine_setup.py`, `tab_manager.py`, `status_writer.py`, `prompt_loader.py`, and `retry_handler.py` is clean. Each module has a single responsibility and minimal coupling.

- **Completion detection heuristics** — Each platform's `completion_check()` is thorough and layered. The Gemini implementation in particular shows careful thinking around the `_seen_stop` / `_dr_start_unconfirmed` state machine, and the comments explaining WHY each fallback threshold was chosen (e.g., "raised from 120 because research was being cut off mid-run") demonstrate real-world iteration.

- **Mixin architecture** — `BrowserMixin`, `InjectMixin`, and `ChatGPTExtractorMixin` are composed cleanly without diamond-inheritance issues. The MRO is `ChatGPT → ChatGPTExtractorMixin → BasePlatform → InjectMixin → BrowserMixin`, which is correct.

- **`_inject_exec_command` fallback chain** — The three-tier injection strategy (execCommand → clipboard paste → physical type) with length verification is well-designed. The 50% length threshold for detecting silent execCommand failure is pragmatic and correctly documented.

- **Test structure** — The three test modules use `IsolatedAsyncioTestCase`, which correctly handles async test cases. Mocks are minimal and focused. The `_load_*` factory functions cleanly isolate platform instances. Test names are descriptive and each test has a single assertion focus.

- **Prompt size guard** — `prompt_loader.py:28-31` enforcing a 500 KB ceiling on prompt files is a good defensive measure that prevents runaway memory use.

- **`_ensure_playwright_data_dir` chmod** — Setting `pw_dir.chmod(0o700)` on the `.chrome-playwright` directory is correct. Cookie files and login data should not be world-readable.

- **Rate-limit pre-flight logging** — Logging budget warnings as warnings (not errors) and proceeding anyway (`log.warning(...) — proceeding anyway`) is the right user experience for a tool where rate limits are expected and the user may want to override.

---

### Verdict: Request Changes

The codebase is production-quality in structure and sophistication. No issues rise to the level of a security exploit in the primary threat model (local single-user automation tool). However, **CR-01** (hardcoded paths in tests) will break CI immediately on any machine that is not the author's, and **CR-02** (non-atomic Preferences write) is a real data-loss risk on a crash. Both are quick fixes. The High issues (HR-01 through HR-04) should be addressed before a public or team release. Medium issues can be tracked as follow-up but are worth fixing before 1.0.

**Recommended actions before release:**
1. Fix `sys.path` in all three test files (CR-01) — 5 min fix.
2. Make Chrome Preferences write atomic (CR-02) — 10 min fix.
3. Replace quote-stripping in `_load_dotenv` with `shlex.split` (HR-01).
4. Use `Path.is_relative_to()` in `_resolve_output_dir` (HR-03).
5. Document the login-retry → agent-fallback ordering dependency (HR-04).
6. Add `timezone.utc` to `datetime.now()` in `status_writer.py` (SG-03).

---

_Reviewed: 2026-04-08_  
_Reviewer: Claude (gsd-code-reviewer / Sonnet 4.6)_  
_Depth: Standard_
