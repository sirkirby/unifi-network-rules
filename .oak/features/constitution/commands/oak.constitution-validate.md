---
description: Validate the engineering constitution for correctness, completeness, and quality.
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Purpose

Lead a comprehensive, agent-driven validation of the engineering constitution. Your job is to reason about the document's structure, quality, and enforceability, using CLI tools only to confirm your own analysis.

{% if is_high_reasoning %}
{% include 'includes/flow_control_high.md' %}

{% include 'includes/validate_workflow_high.md' %}
{% else %}
{% include 'includes/flow_control_basic.md' %}

{% include 'includes/validate_workflow_basic.md' %}
{% endif %}

---

## Step 1: Preflight

1. Load any provided user input from `$ARGUMENTS`.
2. Verify that `oak/constitution.md` exists. If missing, respond with:
   - "No constitution found. Please run `/oak.constitution-create` first." and stop.
3. Read the entire constitution so you can reference specific sections and lines.
4. If `.constitution.md` is available, review it for the canonical standards to compare against.

### Constitution Version Detection

**Detect if this is an "old-style" constitution that could benefit from modernization:**

Check for these indicators:
1. **Hardcoded Testing Requirements** (not decision-driven)
2. **Missing Decision Context Markers** (no testing strategy, no architectural pattern)
3. **Reality Misalignment Indicators** (over-prescriptive MUSTs)

**If OLD-STYLE detected**, present upgrade opportunity:
- Option 1: Continue with standard validation
- Option 2: Modernize constitution (extract decisions, regenerate)
- Option 3: Hybrid approach (validate now, suggest improvements)

Recommend Option 3 (Hybrid) for most cases.

---

## Step 2: Manual Constitution Review

Perform your own evaluation before invoking any CLI validation.

### Structural Checklist

- Confirm every required section appears exactly once
- Ensure section order aligns with project norms
- Flag any empty or placeholder sections

### Metadata Integrity

- Verify all metadata fields are present, non-empty, and meaningful
- Confirm semantic version format (`major.minor.patch`)
- Check ratification/amendment dates follow ISO `YYYY-MM-DD`

### Token & Language Scan

- Ensure no template tokens remain (e.g., `{{PROJECT_NAME}}`)
- Identify non-declarative language (e.g., "should", "could")
- Recommend replacements (`MUST`, `SHOULD`, `MAY`) with rationale

{% include 'includes/validate_quality_rubric.md' %}

### Opportunity Assessment

List high-impact improvements (missing metrics, vague policies, outdated roles). Separate mandatory fixes from recommendations.

---

## Step 3: Reality Alignment Check

After structural validation, check if requirements match project reality.

### Initial Project Analysis

```bash
oak constitution analyze --json
```

This returns structured data about test infrastructure, CI/CD workflows, agent instructions, project files, application code, and classification.

### Deeper Validation

Use targeted commands to verify specific constitution requirements:
- Compare constitution requirements with actual capabilities
- Flag realistic vs aspirational requirements
- Identify gaps between what's required and what exists

{% if is_high_reasoning %}
### Reality Check Areas

Verify alignment for: coverage targets, E2E infrastructure, CI/CD enforcement, TDD practices, code review policies.

Flag misalignments with options: adjust requirement, add implementation plan, or keep aspirational with timeline.
{% else %}
### Coverage Reality Check

If constitution requires specific coverage:
```bash
# Python: pytest with coverage
pytest --cov --cov-report=term 2>/dev/null | grep "TOTAL"

# JS/TS: Check coverage directory
cat coverage/lcov-report/index.html 2>/dev/null | grep -o ">[0-9]*\.[0-9]*%"
```

If constitution requires 80% but current is 45%, present options:
1. **Aspirational**: Add note with timeline
2. **Realistic**: Lower requirement to achievable target
3. **Phased**: New code must meet X%, existing exempt
4. **Commit**: Team commits to achieving target (provide plan)

### E2E Test Reality Check

If constitution requires E2E tests:
```bash
find . -name "*e2e*" -o -name "*integration*" 2>/dev/null | grep -i test | head -10
```

If no E2E infrastructure found but required, suggest changing MUST to SHOULD or adding timeline.

### CI/CD Reality Check

If constitution mandates CI/CD enforcement:
```bash
ls -la .github/workflows/ .gitlab-ci.yml .circleci/ azure-pipelines.yml 2>/dev/null
cat .github/workflows/*.yml 2>/dev/null | grep -E "test|coverage|lint" -A 2
```

Compare with requirements and flag gaps.

### Code Review Reality Check

If constitution has review requirements, check branch protection rules and recent PR patterns.
{% endif %}

---

## Step 4: Findings Summary

Prepare a structured summary including:
- Structural issues (missing/empty sections, metadata gaps, tokens)
- Language/style concerns with suggested declarative rewrites
- Rubric scores with reasoning
- Reality alignment issues (gaps between requirements and actual state)
- Outstanding risks or contradictions
- Questions requiring human clarification

---

## Step 5: Optional CLI Cross-Check

If you need supporting data, run:
```bash
oak constitution validate --json
```

Use the JSON output to corroborate or refine your findings. Never rely on it as the primary assessment.

---

## Step 6: Interactive Fix Mode

Work issue-by-issue from highest to lowest priority.

For each issue:
1. Present the problem with context (quote relevant text, cite section/line)
2. Explain the risk or impact
3. Propose at least two options
4. When user selects, describe exactly how you will modify and why
5. Apply the change, showing the updated snippet
6. Confirm the fix and note follow-up actions

Require explicit explanation-before-change for every modification.

---

{% if is_high_reasoning %}
## Step 7: Final Report

1. Re-run your manual checklist and rubric after fixes
2. Summarize: issues resolved, rubric score changes, remaining concerns
3. Provide status: **Valid** | **Conditionally Valid** | **Invalid**
4. If modernization opportunities identified, list them with next steps
5. Recommend follow-up actions
{% else %}
## Step 7: Re-Assessment & Final Report

1. After all fixes, re-run your manual checklist and rubric
2. Optionally re-run CLI validator to confirm alignment
3. Summarize improvements: issues resolved, rubric score changes, remaining concerns
4. Provide status recommendation:
   - **Valid**: ready for adoption
   - **Conditionally Valid**: acceptable with noted follow-ups
   - **Invalid**: critical issues remain
5. If modernization opportunities were identified, summarize them:
   - Architectural patterns not documented
   - Testing strategy not explicit
   - Reality alignment gaps
6. List next steps (stakeholder review, additional metrics, process rollouts)
7. Encourage user to review diff in version control
{% endif %}

---

{% include 'includes/validate_fix_guidelines.md' %}

---

## Response Expectations

- Lead with findings, then actions, then summary
- Reference sections and quotes directly for transparency
- Maintain declarative tone; avoid vague advice
- Always distinguish between your assessment and CLI output
- Keep a running log of decisions, scores, and remaining risks
