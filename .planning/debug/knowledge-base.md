# GSD Debug Knowledge Base

Resolved debug sessions. Used by `gsd-debugger` to surface known-pattern hypotheses at the start of new investigations.

---

## deepseek-premature-completion — DeepSeek stable-state fallback fires at 51s while still generating
- **Date:** 2026-04-06
- **Error patterns:** premature completion, stable-state fallback, no stop button, ds-icon-button, SVG icon button, completion_check, _no_stop_polls, DeepThink, truncated response
- **Root cause:** DeepSeek's stop button is a ds-icon-button (div[role="button"] with class ds-icon-button) containing only an SVG icon — no text and no aria-label="Stop". All stop-detection selectors used text matching or aria-label substring which fail against a text-free SVG icon button. The stable-state threshold of 6 polls (60s) is also too low for DEEP mode responses (3-5 minutes).
- **Fix:** (1) JS DOM walk from textarea to find ds-icon-button in input container for stop detection. (2) Stable-state threshold scaled to max(6, max(60, max_wait_s // 2) // POLL_INTERVAL) — DEEP mode gets 30 polls (300s). (3) base.py stores max_wait_s as self._current_max_wait_s for subclass access.
- **Files changed:** skills/orchestrator/engine/platforms/deepseek.py, skills/orchestrator/engine/platforms/base.py
---
