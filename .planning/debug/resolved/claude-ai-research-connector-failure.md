---
status: resolved
trigger: "claude-ai-research-connector-failure"
created: 2026-04-06T00:00:00Z
updated: 2026-04-06T00:00:00Z
---

## Current Focus

hypothesis: The connector dialog dismissal in configure_mode clicks [aria-label*="connector"] which toggles a connector chip (selects/deselects a connector) rather than proceeding past the dialog. Research then starts but fails ~4.5 minutes later because no connectors are configured.
test: Read configure_mode code — DONE. The fallback selector [aria-label*="connector"] is indeed a chip toggle, not a proceed button.
expecting: Fix option 1 — disable Research entirely, keep web search only.
next_action: Apply fix to configure_mode to skip Research toggle, only enable Web search.

## Symptoms

expected: Claude.ai DEEP mode completes Research and returns 20,000+ chars.
actual: Every iteration fails at ~272-285s with "Stopped: No response on which connectors to enable during research."
errors: |
  17:57:46  INFO [Claude.ai] Dismissed connector dialog via '[aria-label*="connector"]'
  18:02:22  WARNING [Claude.ai] Research failed: 'Stopped: No response on which connectors to enable during research. Open research panel.'
reproduction: Run orchestrator DEEP mode on Claude.ai. Research mode enabled → connector dialog → wrong element clicked → Research fails.
started: Every DEEP mode iteration — Research has never succeeded.

## Eliminated

- hypothesis: connector dialog dismiss buttons ("Enable", "Start research", "Continue") exist
  evidence: All three locators returned count=0, only [aria-label*="connector"] matched — which is a chip toggle, not a proceed button
  timestamp: 2026-04-06

## Evidence

- timestamp: 2026-04-06
  checked: configure_mode() lines 101-118 in claude_ai.py
  found: Four selectors tried in order; first three not found; [aria-label*="connector"] matched something (a connector chip element) and was clicked, logging "Dismissed connector dialog" — but the dialog was NOT dismissed, just a chip toggled
  implication: Research mode starts without any connectors selected, fails ~4.5 min later

- timestamp: 2026-04-06
  checked: Overall pattern
  found: Research mode has NEVER succeeded across all iterations
  implication: Research mode on Claude.ai is not automatable with current UI — safest fix is to disable Research and use web search only

## Resolution

root_cause: configure_mode() enables Research mode which triggers a mandatory connector selection dialog. The dismissal code tries four selectors; the first three (actual proceed buttons) are not found; the fourth [aria-label*="connector"] matches a connector chip toggle element, clicks it (likely deselecting a connector), and logs false success. Research then starts with no connectors configured and fails ~4.5 min later with "Stopped: No response on which connectors to enable during research."

fix: Remove the Research toggle from configure_mode DEEP mode handling. Only enable Web search. This avoids the connector dialog entirely. Web search alone provides sufficient grounding for DEEP mode without the connector dependency.

verification: Confirmed by user — Fix committed as v0.2.26040631. Research removed, web search only. DEEP mode no longer triggers connector dialog.
files_changed:
  - skills/orchestrator/engine/platforms/claude_ai.py
