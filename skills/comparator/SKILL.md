---
name: comparator
description: >
  Generic Comparison Matrix Builder: creates, populates, and maintains weighted
  XLSX comparison matrices for ANY domain and ANY pair (or set) of solutions.

  Evidence comes from whatever is available — CIRs produced by MultAI's
  solution-researcher, documents in the working folder, LLM knowledge, or user
  description. A CIR is not required.

  Supports two entry points:
    • "compare X vs Y" — full standalone comparison from scratch (Gap 5 flow)
    • matrix operations on an existing XLSX — add-platform, reorder, combo, verify

  USE THIS SKILL when the user wants to: compare solutions head-to-head, build a
  capability matrix, add a platform to a matrix, reorder or verify a matrix, create
  a combo column, or produce a scored comparison of any two products.

  Trigger keywords: "compare", "comparison matrix", "capabilities matrix",
  "add platform", "update the matrix", "reorder", "verify ticks", "combo column",
  "score", "head-to-head", "which is better".
---

# Comparator Skill

Creates and maintains weighted XLSX comparison matrices. Evidence can come from CIRs,
working-folder documents, LLM knowledge, or user description — a pre-existing CIR is
not required. Python scripts (`skills/comparator/matrix_ops.py`,
`skills/comparator/matrix_builder.py`) handle ALL deterministic XLSX work; the LLM
handles capability discovery, evidence reading, and tick judgment.

---

## Phase 0 — Determine Operation & Collect Inputs

Identify which operation the user wants:

| Operation | Trigger | Required Inputs |
|---|---|---|
| **compare** | "compare X vs Y", "which is better", "head-to-head" | Two (or more) solution names or CIR paths |
| **add-platform** | "add X to the matrix" | CIR or context for X, matrix path |
| **build** | "build a new matrix", "create a matrix for…" | Domain + solution list |
| **reorder-columns** | "reorder by score" | Matrix path |
| **combo** | "combo column for A+B" | Matrix path, two platform names |
| **verify** | "verify ticks", "check the matrix" | Matrix path |
| **reorder-rows** | "reorder rows in category X" | Matrix path, category, new order |
| **reorder-categories** | "reorder categories" | Matrix path, new category order |

Also collect:
- **Domain label** — e.g., `devops-platforms` (used to find `domains/{domain}.md` and
  to name output files). Can be inferred from solution names if not provided.
- **Output path** — defaults to `reports/<domain>/<domain>-matrix.xlsx` or a
  timestamped copy of the source matrix.

---

## Phase 1 — Load Context

### Step 1: Domain knowledge (optional)

```bash
ls domains/ 2>/dev/null || echo "no domains dir"
cat domains/{domain}.md 2>/dev/null || echo "no domain file — will bootstrap if needed"
```

If the domain file exists, use it for: archetype validation, inference patterns,
functional equivalence rules, CIR evidence rules, category cross-reference.

**If no domain file exists:** proceed without it. One will be created in Phase 8 after
the first run.

### Step 2: Find available evidence

Search for evidence about the solutions being compared, in priority order:

```bash
# 1. CIRs from solution-researcher
ls reports/*/*.md 2>/dev/null | grep -i "<solution-name>"

# 2. Any markdown/text files in the working folder
ls *.md *.txt 2>/dev/null

# 3. Matrix (if operating on an existing one)
python3 skills/comparator/matrix_ops.py info --src [matrix.xlsx]
python3 skills/comparator/matrix_ops.py extract-features --src [matrix.xlsx]
python3 skills/comparator/matrix_ops.py scores --src [matrix.xlsx]
```

Triage the evidence found:
- **CIR present** → primary evidence source (high confidence)
- **Other document present** → secondary evidence (medium confidence)
- **No documents** → use LLM knowledge (label confidence as "inferred from LLM knowledge")

Announce to the user what evidence was found and its confidence level before proceeding.

---

## Phase 2 — Capability Framework

*Run this phase only for **compare** and **build** operations. Skip for add-platform,
reorder, combo, verify.*

### Step 1: Derive capability categories and features

Using all available evidence (CIRs, documents, LLM knowledge), derive a capability
framework for the domain:

1. Identify **5–12 capability categories** relevant to the solutions being compared
2. For each category, identify **3–10 specific features** that differentiate solutions
3. Number categories: `1. Category Name`, `2. Category Name`, …

Good capability frameworks are:
- **User-facing** — observable behaviours, not implementation details
- **Differentiating** — features where solutions actually differ
- **Comprehensive** — cover the full product surface, not just the most obvious area

Write the proposed framework as a structured list. For example:
```
1. Core Architecture
   - Multi-tenancy support
   - Kubernetes-native deployment
   - Serverless option

2. Developer Experience
   - CLI tool
   - GitOps integration
   - Preview environments
   ...
```

### Step 2: Confirm with user

Present the framework and ask:

> "Here's the capability framework I'll use for this comparison. Does this cover what
> matters to you? Add, remove, or rename any categories or features before I score."

Wait for confirmation or edits. Incorporate changes, then proceed.

---

## Phase 3 — Priority Assignment (Optional)

*Run this phase for **compare** and **build** operations. Optional for add-platform
(can use existing priorities from the matrix).*

### Default priorities

If the user wants to proceed with defaults, use:
- **Critical** (weight 5): Must-have capabilities — showstoppers if absent
- **High** (weight 3): Important differentiators
- **Medium** (weight 2): Nice-to-have
- **Low** (weight 1): Minor or edge-case features

Assign default priorities based on the capability framework and domain context.

### Interactive priority review (optional)

Ask the user:

> "Should I assign priorities automatically, or would you like to review them?
> Priorities drive the weighted score — Critical features count 5×, High 3×, Medium 2×,
> Low 1×. (Say 'auto' to skip this step.)"

**If user says 'auto':** assign priorities using LLM judgment and document the
rationale. Proceed.

**If user wants to review:** present each category with proposed priorities and allow
adjustment:

```
1. Core Architecture
   - Multi-tenancy support            → Critical  (showstopper for enterprise)
   - Kubernetes-native deployment     → High      (important but workaroundable)
   - Serverless option                → Low       (niche use case)
```

Accept changes feature by feature or category by category. Produce the final priority
mapping before continuing.

---

## Phase 4 — Process Evidence (Tick Decisions)

**This is where the LLM adds value.** For each solution, read all available evidence
and decide tick / no-tick for every feature in the capability framework.

### Step 1: Identify evidence variant (if a CIR is present)

- **Variant A** — Has status markers (✅ Core, 🔧 Optional, ⚠️ Unverified, ❌ Not Documented).
  Both narrative and checklist are evidence.
- **Variant B** — Has product-agnostic checklist (no status markers, unchecked items).
  Only narrative sections are evidence. Checklist MUST NOT be used for tick decisions.
- **Non-CIR document** — Use judgment; treat all sections as narrative evidence.
- **LLM knowledge only** — Apply with care; flag confidence as "inferred".

### Step 2: Map features — work matrix-first

Go category by category. For each feature:
1. Search all available evidence for that capability
2. Decide tick (✔) or no-tick
3. Apply inference patterns from domain knowledge if available
4. Record confidence: `CIR-confirmed` | `doc-confirmed` | `inferred` | `user-confirmed`

Write features mapping to a temp file:
```bash
cat > /tmp/comparator-features-<solution>.json << 'EOF'
{
  "Single Sign-On (SSO)": true,
  "Multi-tenancy support": true,
  "Custom ingress controller": false
}
EOF
```

**Rules:**
- Every feature in the framework MUST appear — either `true` or `false`. No omissions.
- When no evidence exists for a feature, default to `false` and note "no evidence found".
- Check archetype alignment if domain knowledge defines archetypes.

### Step 3: New rows (if any)

If evidence reveals capabilities not in the framework:
1. Apply the new row criteria (genuine user-facing capability, not implementation detail)
2. For mature matrices (400+ features), zero new rows is expected
3. Write to a temp file:
```bash
cat > /tmp/comparator-new-rows.json << 'EOF'
[{"category": "3. CI/CD", "feature": "Pipeline analytics dashboard", "priority": "Medium", "ticked": true}]
EOF
```

---

## Phase 5 — Execute (Python)

### For **compare** (new matrix from scratch):

First, build the config JSON:
```bash
cat > /tmp/comparator-build-config.json << 'EOF'
{
  "title": "<Domain> — Capability Comparison Matrix",
  "categories": [
    {
      "name": "1. Category Name",
      "features": [
        {"name": "Feature A", "priority": "Critical"},
        {"name": "Feature B", "priority": "High"}
      ]
    }
  ],
  "platforms": [
    {"name": "Solution A", "features": ["Feature A"]},
    {"name": "Solution B", "features": ["Feature A", "Feature B"]}
  ]
}
EOF
```

Then build the matrix:
```bash
python3 skills/comparator/matrix_builder.py \
    --config /tmp/comparator-build-config.json \
    --out [output.xlsx]
```

Then reorder columns by score:
```bash
python3 skills/comparator/matrix_ops.py reorder-columns \
    --src [output.xlsx] --out [output.xlsx]
```

### For **add-platform** (existing matrix):

```bash
python3 skills/comparator/matrix_ops.py add-platform \
    --src [matrix.xlsx] \
    --out [output.xlsx] \
    --platform "[Platform Name]" \
    --features /tmp/comparator-features-<platform>.json \
    --new-rows /tmp/comparator-new-rows.json

python3 skills/comparator/matrix_ops.py reorder-columns \
    --src [output.xlsx] --out [output.xlsx]
```

### For other operations:

```bash
# Combo column
python3 skills/comparator/matrix_ops.py combo \
    --src [matrix] --out [output] --name "A+B" --platform-a "A" --platform-b "B"

# Verify ticks
python3 skills/comparator/matrix_ops.py verify --src [matrix]

# Reorder rows within category
python3 skills/comparator/matrix_ops.py reorder-rows \
    --src [matrix] --out [output] --category "Category Name" --order /tmp/order.json

# Reorder categories
python3 skills/comparator/matrix_ops.py reorder-categories \
    --src [matrix] --out [output] --order /tmp/cat-order.json
```

---

## Phase 6 — Verify

```bash
python3 skills/comparator/matrix_ops.py scores --src [output.xlsx]
```

Cross-check:
- Does the tick count align with the expected archetype range (if domain knowledge defines archetypes)?
- Are the strong/weak category patterns consistent with the evidence?
- Orphans list from `add-platform`: if > 0, investigate — wrong feature name or new row candidate.

---

## Phase 7 — Markdown Summary

**Always produce this output**, regardless of operation type. Write to
`reports/<domain>/<task-name>-comparison-summary.md`.

Structure:

```markdown
# <Solution A> vs <Solution B> — Comparison Summary
*Generated: YYYY-MM-DD | Matrix: <filename> | Total capabilities: N*

## Overall Scores (Priority-Weighted)

| Rank | Solution | Weighted Score | Raw Tick Count |
|---|---|---|---|
| 1 | Solution A | 142 | 67 |
| 2 | Solution B | 118 | 61 |

**Winner: Solution A** (+24 weighted points, +6 raw capabilities)

## Category-by-Category Breakdown

| Category | Solution A | Solution B | Winner |
|---|---|---|---|
| 1. Core Architecture | 28 | 22 | Solution A |
| 2. Developer Experience | 35 | 40 | Solution B |
| ... | | | |

## Key Differentiators

**Solution A leads on:**
- [feature] — present in A, absent in B (Priority: Critical)
- ...

**Solution B leads on:**
- [feature] — present in B, absent in A (Priority: High)
- ...

## Shared Capabilities
Both solutions support: [feature list]

## Gaps in Both
Neither solution supports: [feature list] — potential shortlist criterion.

## Evidence Quality
| Solution | Primary Source | Confidence |
|---|---|---|
| Solution A | CIR: reports/... | CIR-confirmed |
| Solution B | LLM knowledge | Inferred |
```

For operations other than compare (reorder, combo, verify), produce a shorter summary
covering: what changed, new rankings, output file location.

---

## Phase 8 — Domain Knowledge Enrichment

After completing the operation, propose timestamped append-only additions to
`domains/{domain}.md`.

**If no domain file exists:** create it with this structure:

```markdown
# <Domain> Domain Knowledge

## Evaluation Categories
[list from the capability framework]

## Key Terminology
[domain-specific terms identified during this run]

## Platform Archetypes
[archetypes identified, with expected tick ranges]

## Inference Patterns
[patterns used during tick decisions]

## CIR Evidence Rules
[rules applied]
```

**If domain file exists:** propose additions only:
- New archetype discovered
- New inference pattern
- Tick-count baseline update
- New feature name equivalence
- New evaluation category

Always ask for approval before writing. Additions are append-only and timestamped.

---

## Phase 9 — Present Results

Show the user:
1. **Ranked scores table** (from `scores` command)
2. **Markdown summary** (path to the generated file)
3. **Matrix file location**
4. **What changed:** platforms added, new rows, orphans, columns reordered
5. **Domain knowledge additions** (pending approval)
6. **Evidence used and confidence level** for each solution

---

## Phase 10 — Self-Improve

After each successful operation, append a run log entry.

```
### {YYYY-MM-DD} — {Operation}: {Solution(s)}
- Matrix: {file}
- Evidence: {CIR / document / LLM knowledge}
- Tick count: {count per solution} (archetype: {expected range or N/A})
- New rows added: {count}
- Orphan features: {count}
- Priority adjustments: {any user changes}
- Observations: {accuracy notes, patterns}
- Changes made: {any script updates}
```

**Scope boundary:** Only update files inside `skills/comparator/`. Never modify
other skills' files.

---

## Run Log

<!-- Append new entries at the top of this section after each run -->

### 2026-03-18 — Northflank (IT-SC-05) — add-platform
- Matrix: `/tmp/it-sc05-matrix.xlsx` (test fixture, 4 existing platforms, 7 feature rows)
- Output: `/tmp/it-sc05-matrix-northflank.xlsx`
- Evidence: CIR (solution-researcher output)
- Tick count: 6/7 (archetype: PaaS/IDP K8s-native — expected range 5–8 ✓)
- Features ticked: GitOps ✓, Blue/Green Deployments ✓, CLI Tool ✓, Preview Environments ✓, Kubernetes Support ✓, Multi-cloud ✓
- Features not ticked: Canary Deployments ✗ (no mention in any of 4 responding AI sources — inferred absent)
- New rows added: 0
- Orphans: 0
- Observations: `matrix_ops.py add-platform --out` flag required (not `--dst`); inference from CIR evidence for Canary was reliable
- Changes made: none
