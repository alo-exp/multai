---
name: multi-ai-consolidator
description: >
  Generic Multi-AI Consolidator: synthesizes responses from multiple AI platforms
  into a unified consolidated report. Reads a raw AI responses archive (produced
  by the orchestrator skill) and produces a synthesis highlighting consensus areas,
  disagreements, unique insights, and source reliability.

  If a consolidation guide (.md file) is provided, follows its prescribed output
  structure exactly — the guide is the sole structural authority. Otherwise uses
  a generic synthesis structure.

  USE THIS SKILL after the orchestrator skill has produced a raw responses archive,
  or when any other skill (landscape-researcher, solution-researcher) invokes it
  as part of a larger workflow.
---

# Multi-AI Consolidator Skill

This skill reads raw AI responses and synthesises them into a consolidated report.
Follow the phases below in order.

---

## Phase 0 — Receive Inputs

Accept from the user or calling skill:
- **Raw responses archive** — path to the `{task-name} - Raw AI Responses.md` file (required)
- **Consolidation guide** *(optional)* — path to a `.md` file defining the output structure
- **Domain knowledge file** *(optional)* — path to a `domains/{domain}.md` file for domain context
- **Output path** *(optional)* — where to save the report (default: same directory as the archive)

---

## Phase 1 — Read All Raw Responses

Read the raw responses archive file in full. Identify each platform's response section and note:
- Which platforms responded successfully
- Approximate response lengths
- Any platform-specific caveats (rate limited, partial, failed)

**Source reliability notes (for weighting, not structural guidance):**
- **Claude.ai** in REGULAR mode often produces the deepest analysis. Weight heavily.
- **ChatGPT** Deep Research is highly reliable with web citations.
- **Copilot** Deep Research often crawls GitHub README — high quality for open-source products.
- **Perplexity** provides strong web citations and source links.
- **Grok** may receive condensed prompts — shallower analysis. Weight accordingly.
- **DeepSeek** may fail URL access — exclude if failed.
- **Gemini** Deep Research (when completed) has the highest citation quality — verified against
  live web sources. Weight as primary if present.

---

## Phase 2 — Synthesize

### If a consolidation guide IS provided:

Follow the guide's prescribed structure exactly. The guide is the sole structural authority
for output format — do not introduce knowledge about specific report types (CIR, Market
Landscape, etc.) beyond what the guide specifies. The guide defines:
- Section headings and their purpose
- How to weight different sources
- Domain-specific evaluation criteria
- Output formatting requirements
- Quality checklists to verify before saving

If a domain knowledge file is also provided, use its evaluation categories, terminology,
and criteria weights to inform the synthesis — but the guide's structure takes precedence.

### If NO consolidation guide is provided:

Produce a generic synthesis with the following structure:

1. **Summary** — What the collective AI responses say about the topic
2. **Areas of Consensus** — Where 4+ platforms agree
3. **Areas of Disagreement** — Where platforms contradict each other
4. **Unique Insights** — Points raised by only 1-2 platforms that add significant value
5. **Gaps and Limitations** — What no platform covered adequately
6. **Source Reliability Assessment** — Per-platform rating based on depth, accuracy,
   and citation quality

---

## Phase 3 — Output Consolidated Report

Save the report in the same directory as the raw responses archive.

**Filename conventions:**
- When following a guide: use the filename format specified in the guide
- When generic: `[Topic] - Consolidated Report.md`

Present the report path to the user or return it to the calling skill.

---

## Phase 4 — Domain Knowledge Enrichment

*Only applies when a domain knowledge file was provided and the calling skill has not
already handled domain enrichment (e.g., landscape-researcher and solution-researcher
handle this themselves in their own phases).*

After synthesis, propose timestamped append-only additions to the domain knowledge file.

### What to propose:

- **Source reliability observations** — new patterns about AI platform performance
- **Cross-AI disagreement patterns** — systematic areas where platforms diverge
- **New terminology** discovered during synthesis not in the domain file
- **Evaluation criteria refinements** — insights about which criteria mattered most

### Format:

```markdown
## Additions from [Topic] consolidation ([date]) — consolidator
- Source reliability: [observation]
- Disagreement pattern: [observation]
- New term: [term] — [definition]
```

Present proposed changes to the user or calling skill for approval before writing.

---

## Phase 5 — Self-Improve

After each successful run, append a run log entry noting consolidation quality,
any structural issues encountered, and any improvements worth capturing.

**Scope boundary:** Only update files inside `skills/consolidator/`. The guide files
(in the calling skill's directory) are owned by those skills — do not modify them here.

---

## Run Log

<!-- Append new entries at the top of this section after each run -->
