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

## Flow Control & Conversation Continuity

**This workflow should be a continuous, proactive conversation.** Do NOT stop and wait after each question unless there is genuine ambiguity requiring clarification.

### Flow Control Rules

1. **Batch related questions together** - When gathering project metadata (name, author, tech stack, description), ask ALL in one message, not sequentially with pauses.

2. **Continue automatically when context is clear** - If the user has provided enough information to proceed, move forward without asking "should I continue?"

3. **Decision points are checkpoints, not stop signs** - Present options, wait for the user's selection, then IMMEDIATELY continue to the next step. Don't stop and ask "ready to continue?"

4. **Maintain momentum** - After each user response, acknowledge it briefly and move to the next logical step in the same message.

### Handling Pauses

Only pause and explicitly wait for user input when:
- You need a specific decision the user hasn't provided
- There's genuine ambiguity about requirements
- You're at a CRITICAL CHECKPOINT (marked with CHECKPOINT)
- You've completed the entire workflow and need final approval

**Anti-pattern:** "Would you like me to continue?" / "Ready for the next step?" / "Shall I proceed?"
**Better:** Just continue. If the user wants to pause, they'll tell you.
## Workflow Overview

1. Preflight: locate and load the constitution.
2. Manual constitution review using the structural checklist and quality rubric.
3. Synthesize findings, gaps, and improvement opportunities.
4. (Optional) Run `oak constitution validate --json` to cross-check your conclusions.
5. Facilitate interactive fixes, justifying every change.
6. Re-assess and deliver a final health report with next steps.
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

- Ensure no template tokens remain (e.g., ``)
- Identify non-declarative language (e.g., "should", "could")
- Recommend replacements (`MUST`, `SHOULD`, `MAY`) with rationale

### Quality Rubric (Score 1-5 each)

1. **Clarity & Enforceability**: Are requirements explicit, testable, and free of ambiguity?
2. **Alignment with Standards**: Does the document reflect organizational practices?
3. **Completeness & Coverage**: Are policies thorough, with rationale and edge cases addressed?
4. **Consistency & Traceability**: Do sections avoid contradictions? Are versioning and amendments coherent?
5. **Operational Readiness**: Can teams act on the policies today?

For each dimension, cite evidence (section references, quotes, observed gaps) and record a score with explanation.
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

---

## Guidelines for Fixing

### Empty Sections
**Generate based on codebase analysis:**
- Scan for relevant files and patterns
- Create realistic, enforceable requirements
- Use declarative language (MUST, SHALL)
- Include rationale for each requirement

### Non-declarative Language
**Replacement strategy:**
- "should" -> "MUST" (for requirements) or "SHOULD" (for recommendations)
- "could" -> "MAY" (for options) or remove if not a requirement
- "might" -> Rephrase to be definitive
- "maybe" -> Remove or make specific

### Date Formats
**Always use ISO 8601:**
- Convert MM/DD/YYYY -> YYYY-MM-DD
- Convert DD/MM/YYYY -> YYYY-MM-DD

### Template Tokens
**Replace with actual values:**
- `` -> Get from config or repo name
- `` -> Get from codebase analysis
- `` -> Get from git config or ask user
- Never leave tokens unreplaced

## Important Notes

- **Interactive mode is default** - Always ask before applying fixes
- **Explain changes** - Tell user what was changed and why
- **Preserve content** - Never delete sections, only add or modify
- **Use CLI tools** - Don't manually parse/write files, use CLI commands
- **Validate after fixes** - Always re-run validation to confirm
---

## Response Expectations

- Lead with findings, then actions, then summary
- Reference sections and quotes directly for transparency
- Maintain declarative tone; avoid vague advice
- Always distinguish between your assessment and CLI output
- Keep a running log of decisions, scores, and remaining risks