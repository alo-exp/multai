---
status: awaiting_human_verify
trigger: "ChatGPT rate-limit banner not detected early. Engine waits 597s polling the DR iframe then spends 6 more minutes on 12 extraction retries before declaring failure."
created: 2026-04-07T00:00:00Z
updated: 2026-04-07T00:00:00Z
---

## Current Focus

hypothesis: CONFIRMED — check_rate_limit() IS called in _poll_completion() but it only checks page-level text. The bug is that when rate-limited, _poll_completion returns True (not a special sentinel), then extract_response() enters the 12-retry DR panel loop (6 min) before the quota check in extract_response fires. The quota check at the TOP of extract_response uses _DR_QUOTA_PHRASES but does NOT check the broader "usage cap" / "limit reached" patterns that check_rate_limit() uses.
test: Confirmed by reading code — check_rate_limit() in base._poll_completion returns True (line 664) which tells the engine "generation is complete" — triggering extract_response and its 12-retry DR loop before the quota check at the top of extract_response.
expecting: Fix needs to: (1) make _poll_completion raise/return a rate-limited sentinel instead of True, OR (2) add rate-limit check at start of each DR panel retry loop iteration
next_action: Design and apply the fix

## Symptoms

expected: When ChatGPT shows a rate-limit or usage-cap message, the engine should detect it within the first few polls and exit with status=rate_limited
actual: Engine polled for 597s (60 polls), declared "complete" due to timeout, then attempted 12 extraction retries of 30s each (6 more minutes), all returning 0 chars, before finally failing
errors: "WARNING [ChatGPT] DEEP: 60 polls without populated DR iframe — declaring complete", then "DR panel empty (attempt N/12) — waiting 30s..." x12, then "Extraction returned only 0 chars"
reproduction: Run orchestrator with ChatGPT when account has hit Deep Research usage cap
started: Observed in iter 25 (2026-04-07)

## Eliminated

## Evidence

- timestamp: 2026-04-07T00:01:00Z
  checked: base.py _poll_completion() lines 659-664
  found: check_rate_limit() IS called every poll, but on detection it logs a warning then returns True — which means "generation complete". This exits the poll loop normally.
  implication: The run proceeds to extract_response() as if generation succeeded.

- timestamp: 2026-04-07T00:02:00Z
  checked: chatgpt.py extract_response() lines 525-533 (quota check at top of DEEP mode)
  found: There IS a quota check using _DR_QUOTA_PHRASES BEFORE the 12-retry loop. But _DR_QUOTA_PHRASES only covers 4 phrases: "lighter version of deep research", "remaining queries are powered by", "full access resets on", "your remaining queries". The broader patterns in check_rate_limit() ("You've reached the current usage cap", "usage cap", "limit reached", etc.) are NOT checked here.
  implication: If the page shows a usage cap banner with text NOT matching _DR_QUOTA_PHRASES, the quota check at the top of extract_response passes, then the 12-retry loop runs for 6 minutes.

- timestamp: 2026-04-07T00:03:00Z
  checked: chatgpt.py _extract_deep_research_panel() lines 366-373 (retry loop)
  found: The retry loop (12 × 30s = 6 min) has NO rate-limit check inside it. Each iteration calls _try_extract() which only looks at iframe content.
  implication: Once the rate-limit quota check at the top of extract_response is bypassed (due to phrase mismatch), all 12 retries run to completion with no early exit.

- timestamp: 2026-04-07T00:04:00Z
  checked: completion_check() lines 493-495 — the 60-poll fallback
  found: After 60 polls (~597s at ~10s/poll), it declares complete regardless. This matches the observed "597s polling" symptom. The rate-limit banner was not detected in any of those 60 polls because... wait — check_rate_limit() IS called in _poll_completion(). So why wasn't it caught?
  implication: The rate-limit patterns in check_rate_limit() may not match the exact text ChatGPT shows for usage cap. The banner might be a modal/dialog that uses slightly different text than the patterns listed. Need to verify pattern coverage.

- timestamp: 2026-04-07T00:05:00Z
  checked: chatgpt.check_rate_limit() patterns vs _DR_QUOTA_PHRASES
  found: check_rate_limit() has "usage cap", "limit reached", "You've reached the current usage cap", "come back later", "lighter version of deep research", "remaining queries are powered by", "full access resets on", "Your remaining queries". If any of these matched during the 597s polling, _poll_completion would have returned True early (after first poll). The fact that it ran for 60 polls (597s) means NONE of these matched the visible UI text during polling.
  implication: Root cause is twofold: (A) check_rate_limit() patterns don't cover the actual text shown in ChatGPT's usage cap UI during DR polling, AND (B) even if they did match, returning True from _poll_completion is the wrong signal — it should exit with a rate-limited status, not trigger the 12-retry DR extraction loop.

## Resolution

root_cause: Three-part root cause: (1) check_rate_limit() in chatgpt.py was missing patterns that match the actual usage-cap banner text ChatGPT shows (e.g. "You've reached your limit", "daily limit", etc.) and only did DOM-visible element checks — not a body.innerText scan, so shadow DOM or off-screen banners were missed. (2) Even when check_rate_limit() DID fire during _poll_completion(), it returned True (meaning "complete") causing run() to call extract_response() and its 12-retry DR panel loop (6 min) before exiting. (3) The 12-retry loop in _extract_deep_research_panel() had no rate-limit check inside each iteration, so it always ran the full 6 minutes even when a rate-limit banner was visible.
fix: Three changes applied: (A) chatgpt.py check_rate_limit() — expanded patterns list (added "You've reached your limit", "daily/monthly/research limit", "you're out of", "upgrade your plan") and added a second-pass body.innerText scan to catch banners outside the visible DOM. (B) base.py _poll_completion() — now stores rate_msg in self._poll_rate_limit_msg; run() checks this flag after poll and returns STATUS_RATE_LIMITED immediately without calling extract_response. (C) chatgpt.py _extract_deep_research_panel() retry loop — added check_rate_limit() call at the start of each of the 12 iterations; on detection returns [RATE LIMITED] marker immediately instead of waiting 30s.
verification: Syntax verified (ast.parse clean). Awaiting live test with rate-limited ChatGPT account.
files_changed: [skills/orchestrator/engine/platforms/chatgpt.py, skills/orchestrator/engine/platforms/base.py]
