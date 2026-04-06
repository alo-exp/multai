---
status: resolved
trigger: "DeepSeek completion_check fires prematurely — stable-state fallback (6 consecutive polls with no stop button) declares complete after ~51s while DeepSeek is still actively generating."
created: 2026-04-06T00:00:00Z
updated: 2026-04-06T00:00:00Z
---

## Current Focus

hypothesis: DeepSeek's stop button uses `.ds-icon-button` with an SVG icon only (no text). Current selectors check for text "Stop" which DeepSeek's stop button does NOT contain. The animated thinking indicator selector `[class*="thinking"]` also misses because DeepSeek uses a different class. All stop-detection paths fail → 6 polls × 10s → premature "complete" at ~51s.

Secondary: The `>3000 chars` content check fires on chain-of-thought (markdown-body) text accumulated during DeepThink, which IS inside a `.markdown-body` even though it's thinking output — if the thinking CoT text is NOT inside a `[class*="think"]` ancestor, the leaf-block filter won't exclude it, and the content check triggers premature completion.

test: Read the completion_check code, examine stop button selectors vs. DeepSeek's actual button structure, then cross-reference with the send button selector (which uses ds-icon-button). Also examine whether any logs show "thinking" or "loading" class detection.

expecting: Stop button detection fails because DeepSeek's stop button is a `.ds-icon-button` SVG icon with no readable text content — matching on `:has-text("Stop")` and `aria-label*="Stop"` both fail. The `_no_stop_polls` counter climbs to 6 and the fallback fires.

next_action: Implement fix — add SVG/icon-based stop button selectors and increase the stable-state threshold for DEEP mode.

## Symptoms

expected: completion_check() should only return True when DeepSeek has fully finished generating (stop button disappears naturally OR copy/regenerate buttons appear). A complete deep-research response should be 20,000+ chars.

actual: completion_check() returns True after ~51s (6 polls × ~10s) via the stable-state fallback. The stop button was never detected during that time despite DeepSeek actively generating. The extracted response is 5747 chars, truncated mid-sentence: "found that messages acknowledging current approaches before challenging them had"

errors: |
  16:49:13  INFO [DeepSeek] No stop button for 6 polls — declaring complete
  16:49:13  INFO [DeepSeek] Response complete (51s)
  16:49:13  INFO [DeepSeek] Extracted 5747 chars via JS leaf response blocks

reproduction: Run orchestrator with DEEP mode on DeepSeek with a complex prompt (7000+ chars). DeepSeek enters DeepThink+Search mode. Completion declared at ~51s, response truncated.

started: Since DeepThink mode was added. Observed in multiple iterations (iter 22).

## Eliminated

- hypothesis: Secondary (content check firing on CoT text > 3000 chars)
  evidence: The log shows "No stop button for 6 polls — declaring complete" — meaning the stable-state fallback fired. If the >3000 char content check had fired, a different log line would have appeared. The stable-state counter hit 6.
  timestamp: 2026-04-06

- hypothesis: Stop button detection works but DeepSeek finishes in 51s
  evidence: Response is 5747 chars, truncated mid-sentence "...had" — DeepSeek was clearly still generating. A real completion would produce 20k+ chars.
  timestamp: 2026-04-06

## Evidence

- timestamp: 2026-04-06
  checked: completion_check() selectors for stop button
  found: |
    Three selectors used:
      'button:has-text("Stop")'           — matches HTML <button> with text "Stop"
      'button[aria-label*="Stop"]'        — matches <button> with aria-label containing "Stop"
      '[role="button"]:has-text("Stop")' — matches div[role=button] with text "Stop"
    AND animated indicator: '[class*="thinking"], [class*="loading"], [class*="typing"]'
  implication: If DeepSeek renders its stop button as an SVG icon button with NO visible text and no aria-label containing "Stop" — all selectors miss.

- timestamp: 2026-04-06
  checked: click_send() in deepseek.py — uses ds-icon-button selector
  found: |
    The send button is '[role="button"].ds-icon-button' — DeepSeek's icon buttons are
    div[role="button"] with class ds-icon-button. These contain ONLY an SVG <path> child —
    no text content. The stop button during generation uses the SAME component pattern,
    just with a different SVG icon (square/stop shape vs. send arrow).
  implication: ':has-text("Stop")' and 'aria-label*="Stop"' BOTH fail because:
    (a) there is no text content in a ds-icon-button,
    (b) DeepSeek does not set aria-label="Stop" on the button.
    This is confirmed by the send button working fine with a pure class+role selector,
    not text-based selection.

- timestamp: 2026-04-06
  checked: POLL_INTERVAL constant
  found: POLL_INTERVAL = 10 seconds (config.py line 98)
  implication: 6 polls × 10s = 60s. Log shows 51s — first poll happens immediately,
    meaning polls at t≈0, 10, 20, 30, 40, 50 → _no_stop_polls hits 6 → fires at ~50s.

- timestamp: 2026-04-06
  checked: Log from iter22-cmf.log — DeepSeek timing
  found: |
    16:48:22  INFO  [DeepSeek] Waiting for response (max 600s)
    16:49:13  INFO  [DeepSeek] No stop button for 6 polls — declaring complete
    Elapsed: 51s exactly. No stop button detection log entry at all.
  implication: All stop detection paths failed for all 6 polls. The animated thinking
    indicator check also failed — likely because DeepSeek's thinking animation uses
    a different class (e.g. ds-thinking, _thinking, etc.) rather than `thinking`.

- timestamp: 2026-04-06
  checked: _no_stop_polls reset logic
  found: |
    _no_stop_polls is initialized in __init__ to 0.
    It is reset to 0 only when has_stop=True.
    It is incremented every poll where has_stop=False.
    The threshold is >= 6 (fires on the 6th consecutive failing poll).
  implication: If DEEP mode takes 3-5 minutes for DeepSeek (as expected), threshold
    of 6 (60s) is far too low. It should be much higher for DEEP mode, or driven by
    max_wait_s (e.g., 80% of max_wait_s must pass before stable-state fires).

## Resolution

root_cause: |
  DeepSeek's stop button during generation is a ds-icon-button (div[role="button"]
  with class "ds-icon-button") containing ONLY an SVG icon — no text and no
  aria-label="Stop". All three stop-detection selectors in completion_check() use
  text matching (:has-text("Stop")) or aria-label substring ("Stop"), which ALL
  fail against a text-free SVG icon button. The animated thinking indicator check
  also fails because DeepSeek uses a specific class name that does not contain
  "thinking", "loading", or "typing".

  Result: _no_stop_polls increments to 6 in 60s (6 × POLL_INTERVAL=10s), and the
  stable-state fallback fires — declaring "complete" while DeepSeek is still in
  DeepThink mode actively generating a full response.

  The secondary flaw: the stable-state threshold of 6 polls (60s) is appropriate
  for standard mode, but in DEEP mode DeepSeek takes 3-5 minutes. Even if a
  slightly-better selector catches SOME polls, a threshold that fires at 60s will
  truncate DEEP mode responses.

fix: |
  Three changes applied:

  1. completion_check() rewritten — copy/regenerate check moved FIRST (definitive
     completion signal). Then ds-icon-button detection scoped to the input container
     via JS DOM walk from the textarea (avoids false positives from post-response
     action buttons that also use ds-icon-button). Broad animated-indicator sweep
     added. Content-size heuristic (>3000 chars) REMOVED — it was a secondary
     false-positive risk.

  2. Stable-state threshold scaled to max_wait_s:
     stable_state_s = max(60, max_wait_s // 2)
     stable_state_polls = max(6, stable_state_s // POLL_INTERVAL)
     DEEP mode (max_wait=600s): 30 polls = 300s before stable-state fires.
     Regular mode (max_wait=120s): 6 polls = 60s (unchanged behavior).

  3. base.py _poll_completion: stores max_wait_s as self._current_max_wait_s before
     the polling loop so completion_check() overrides can read it.

verification: Confirmed by user — fix committed as v0.2.26040629. JS DOM walk from textarea to find ds-icon-button in input container works. Scaled stable-state threshold (max_wait_s // 2) prevents premature completion in DEEP mode.
files_changed:
  - skills/orchestrator/engine/platforms/deepseek.py
  - skills/orchestrator/engine/platforms/base.py
