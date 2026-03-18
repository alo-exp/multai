---
name: comparator
description: >
  Generic Comparison Matrix Builder: creates and maintains head-to-head
  weighted XLSX comparison matrices for ANY domain from Consolidated Intelligence
  Reports. Python scripts handle all XLSX manipulation; the LLM handles CIR reading
  and tick judgment calls.

  USE THIS SKILL when the user wants to: compare solutions, build a comparison matrix,
  add a platform to a matrix, reorder or verify a matrix, create a combo column,
  or when a new CIR has been produced and a matrix exists for that domain.

  Trigger keywords: "comparison matrix", "capabilities matrix", "add platform",
  "update the matrix", "reorder", "verify ticks", "combo column", "compare solutions".
---

# Comparator Skill

Creates and maintains weighted XLSX comparison matrices from Consolidated Intelligence Reports. Python scripts (`skills/comparator/matrix_ops.py`, `skills/comparator/matrix_builder.py`) handle ALL deterministic XLSX work. The LLM handles CIR reading and tick judgment only.

---

## Phase 0 — Determine Operation & Collect Inputs

Identify which operation the user wants:

| Operation | Command | Required Inputs |
|-----------|---------|----------------|
| Add platform | `add-platform` | CIR path, matrix path, platform name |
| Build new matrix | `build` | Build config JSON, output path |
| Reorder columns by score | `reorder-columns` | Matrix path |
| Create combo column | `combo` | Matrix path, two platform names, combo name |
| Verify ticks | `verify` | Matrix path, CIR path(s) |
| Reorder rows | `reorder-rows` | Matrix path, category name, new order |
| Reorder categories | `reorder-categories` | Matrix path, new category order |

Also collect:
- **Domain** — e.g., `devops-platforms` (used to find `domains/{domain}.md`)
- **Output path** — where to save the updated matrix (defaults to same path or timestamped copy)

---

## Phase 1 — Load Context

### Step 1: Read domain knowledge (if it exists)

```bash
# Check for domain-specific knowledge
cat domains/{domain}.md
```

Use domain knowledge for: archetype validation, inference patterns, functional equivalence, CIR evidence rules, category cross-reference.

### Step 2: Query the matrix

For existing matrices, run these to understand current state:

```bash
cd <workspace-root>
python3 skills/comparator/matrix_ops.py info --src [matrix.xlsx]
python3 skills/comparator/matrix_ops.py extract-features --src [matrix.xlsx]
python3 skills/comparator/matrix_ops.py scores --src [matrix.xlsx]
```

This gives you: platform list, category list, feature count, current rankings. No need to open the XLSX manually.

---

## Phase 2 — Process CIR (LLM Judgment)

**This phase is where the LLM adds value.** Read the CIR and make tick/no-tick decisions for every feature.

### Step 1: Identify CIR variant

Read the CIR and determine which variant it is:
- **Variant A** — Has status markers (✅ Core, 🔧 Optional, ⚠️ Unverified, ❌ Not Documented). Both narrative and checklist are evidence.
- **Variant B** — Has product-agnostic checklist (no status markers, unchecked items). Only narrative sections are evidence. Checklist section MUST NOT be used for tick decisions.

See `domains/{domain}.md` → "CIR Evidence Rules" for detailed variant identification rules.

### Step 2: Map features

Work **matrix-first**: go category by category through the extracted features list. For each feature:

1. Search the CIR for evidence of that capability
2. Apply the domain's evidence rules to decide tick/no-tick
3. Apply inference patterns from domain knowledge (auth-backbone, compliance certification, functional equivalence, networking abstraction caveat)
4. Record the decision in the features JSON

Write features mapping to a temp file:
```json
{
  "Single Sign-On (SSO)": true,
  "Multi-tenancy support": true,
  "Custom ingress controller": false,
  "...": "..."
}
```

**Critical rules:**
- Every feature in the matrix MUST appear in the JSON — either `true` or `false`. No omissions.
- Include a CIR section reference as a comment for audit trail.
- When the domain file defines platform archetypes, check if the tick count aligns with the expected range for the platform's archetype.

### Step 3: Identify new rows (if any)

If the CIR reveals capabilities not covered by any existing matrix feature:
1. Apply the new row criteria from domain knowledge (genuine user-facing capability, not implementation detail)
2. For mature matrices (400+ features), **zero new rows is expected** — don't force it
3. Write new rows to a temp file:
```json
[
  {"category": "6. CI/CD & Build Automation", "feature": "Pipeline analytics dashboard", "priority": "Medium", "ticked": true}
]
```

### Step 4: Write JSON files

```bash
# Write features mapping
cat > /tmp/comparator-features.json << 'EOF'
{... feature mapping ...}
EOF

# Write new rows (if any)
cat > /tmp/comparator-new-rows.json << 'EOF'
[... new rows ...]
EOF
```

---

## Phase 3 — Execute (Python)

### For add-platform:

```bash
cd <workspace-root>
python3 skills/comparator/matrix_ops.py add-platform \
    --src [matrix.xlsx] \
    --out [output.xlsx] \
    --platform "[Platform Name]" \
    --features /tmp/comparator-features.json \
    --new-rows /tmp/comparator-new-rows.json
```

Then auto-reorder columns by score:

```bash
python3 skills/comparator/matrix_ops.py reorder-columns \
    --src [output.xlsx] \
    --out [output.xlsx]
```

### For build (new matrix):

```bash
python3 skills/comparator/matrix_builder.py \
    --config /tmp/comparator-build-config.json \
    --out [output.xlsx]
```

### For other operations:

```bash
# Combo column
python3 skills/comparator/matrix_ops.py combo --src [matrix] --out [output] \
    --name "A+B" --platform-a "A" --platform-b "B"

# Verify ticks
python3 skills/comparator/matrix_ops.py verify --src [matrix]

# Reorder rows within category
python3 skills/comparator/matrix_ops.py reorder-rows --src [matrix] --out [output] \
    --category "Category Name" --order /tmp/order.json

# Reorder categories
python3 skills/comparator/matrix_ops.py reorder-categories --src [matrix] --out [output] \
    --order /tmp/cat-order.json
```

Read JSON output to confirm results.

---

## Phase 4 — Verify

### Step 1: Check scores

```bash
python3 skills/comparator/matrix_ops.py scores --src [output.xlsx]
```

### Step 2: Cross-check against archetype

If domain knowledge defines archetypes, check:
- Does the tick count fall within the expected range for this platform's archetype?
- Are the strong/weak category patterns consistent?
- Flag anomalies (e.g., a PaaS scoring 250+ or a Full K8s platform scoring <200)

### Step 3: Check for orphans

The `add-platform` output includes an `orphans` list — features the LLM ticked that don't exist in the matrix. If orphans > 0, investigate: either the feature name was slightly wrong (fix the JSON) or it's a new row candidate.

---

## Phase 5 — Domain Knowledge Enrichment

After completing the matrix operation, review what was learned and propose timestamped append-only additions to `domains/{domain}.md`.

### What to propose:

- **New archetype** discovered (a platform that doesn't fit existing archetypes)
- **New inference pattern** (a pattern that worked during this mapping that could be reused)
- **Tick-count baseline update** (if the archetype's expected range needs adjustment)
- **New feature name equivalence** (CIR name → matrix name mapping that was manually resolved)
- **New evaluation category** (if a significant capability area was discovered)

### Format:

```markdown
## Additions from [Platform Name] comparator (YYYY-MM-DD)
- [observation/addition]
```

If the domain is entirely new (no `domains/{domain}.md` exists), create it with the standard structure:
- Evaluation Categories
- Key Terminology
- Evaluation Criteria

Then populate from the first CIR's content.

---

## Phase 6 — Present Results

Show the user:

1. **Ranked scores table** from `python3 skills/comparator/matrix_ops.py scores`
2. **What was done:**
   - Platforms added / removed
   - New rows added (if any) with their categories and priorities
   - Orphan features flagged (if any)
   - Columns reordered (new ranking)
3. **Domain knowledge proposed** (additions to domain file, pending user approval)
4. **Output file location**

---

## Phase 7 — Self-Improve

After each successful matrix operation, append a run log entry and update scripts if needed.

1. **Append a run log entry** to the `## Run Log` section:
   ```
   ### {YYYY-MM-DD} — {Platform Name} ({operation})
   - Matrix: {matrix file}
   - Tick count: {count} (archetype: {expected range})
   - New rows added: {count}
   - Orphan features: {count}
   - Observations: {accuracy notes, inference patterns that worked/failed}
   - Changes made: {any updates to matrix_ops.py, matrix_builder.py}
   ```

2. **Update `matrix_ops.py` or `matrix_builder.py`** if a script bug or limitation was encountered.

**Scope boundary:** Only update files inside `skills/comparator/`. Never modify other skills' files.

---

## Run Log

<!-- Append new entries at the top of this section after each run -->

### 2026-03-18 — Northflank (IT-SC-05) — add-platform
- Matrix: `/tmp/it-sc05-matrix.xlsx` (test fixture, 4 existing platforms, 7 feature rows)
- Output: `/tmp/it-sc05-matrix-northflank.xlsx`
- Tick count: 6/7 (archetype: PaaS/IDP K8s-native — expected range 5–8 ✓)
- Features ticked: GitOps ✓, Blue/Green Deployments ✓, CLI Tool ✓, Preview Environments ✓, Kubernetes Support ✓, Multi-cloud ✓
- Features not ticked: Canary Deployments ✗ (no mention in any of 4 responding AI sources — inferred absent)
- New rows added: 0 (all 7 features matched existing rows)
- Orphans: 0
- Observations: `matrix_ops.py add-platform --out` flag required (not `--dst`); inference from CIR evidence for Canary was reliable — Grok explicitly covered deployment types without mentioning canary
- Changes made: none to matrix_ops.py or matrix_builder.py
