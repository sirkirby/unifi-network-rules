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

## Flow Control (High-Reasoning Mode)

**Operate autonomously.** Maintain conversation momentum without unnecessary pauses.

**Only pause when:**
- User input is genuinely ambiguous
- A critical decision requires explicit approval (marked with CHECKPOINT)
- The workflow is complete

**Never ask:** "Ready to continue?" / "Should I proceed?" / "Would you like me to..."

Just continue. Users will interrupt if needed.
## Workflow Overview

1. **Preflight** - Load constitution, detect version style
2. **Review** - Manual evaluation using structural checklist and quality rubric
3. **Synthesize** - Compile findings, gaps, and opportunities
4. **Cross-check** - Optional CLI validation to corroborate
5. **Fix** - Interactive fixes with justification
6. **Report** - Final health assessment and recommendations

Lead with your own analysis. The CLI validator supports but doesn't replace your judgment.
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

### Reality Check Areas

Verify alignment for: coverage targets, E2E infrastructure, CI/CD enforcement, TDD practices, code review policies.

Flag misalignments with options: adjust requirement, add implementation plan, or keep aspirational with timeline.

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

## Step 7: Final Report

1. Re-run your manual checklist and rubric after fixes
2. Summarize: issues resolved, rubric score changes, remaining concerns
3. Provide status: **Valid** | **Conditionally Valid** | **Invalid**
4. If modernization opportunities identified, list them with next steps
5. Recommend follow-up actions

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