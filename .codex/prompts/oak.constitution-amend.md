---
description: Add a versioned amendment to the engineering constitution.
handoffs:
  - label: Validate Constitution
    agent: oak.constitution-validate
    prompt: Validate the constitution and its amendments for correctness, completeness, and quality.
---

## User Input

```text
$ARGUMENTS
```

You **MUST** incorporate any provided context before prompting the user.

## Purpose

Shepherd the amendment process from intent to execution. You are responsible for understanding the requested change, assessing impact, selecting the correct amendment type, updating the constitution, and keeping all agent instruction files in sync without harming existing guidance.

## Flow Control (High-Reasoning Mode)

**Operate autonomously.** Maintain conversation momentum without unnecessary pauses.

**Only pause when:**
- User input is genuinely ambiguous
- A critical decision requires explicit approval (marked with CHECKPOINT)
- The workflow is complete

**Never ask:** "Ready to continue?" / "Should I proceed?" / "Would you like me to..."

Just continue. Users will interrupt if needed.
## Workflow Overview

1. **Preflight** - Verify constitution exists, capture current state
2. **Gather** - Collect amendment details, clarify intent
3. **Research** - Investigate patterns if needed (capability-aware)
4. **Analyze** - Assess impact on existing constitution
5. **Decide** - Determine amendment type and version bump
6. **Apply** - Run CLI, verify results
7. **Sync** - Update agent instruction files
8. **Report** - Quality review and final summary

Focus on impact analysis and decision-making. The CLI handles file operations.
---

## Step 1: Preflight & Context Check

1. Ensure `oak/constitution.md` exists. If missing, inform the user and stop.
2. Read the constitution to capture:
   - Current version
   - Metadata (author, last amendment date)
   - Recent amendments (especially if they relate to the same section)
   - Constitution generation approach (check for decision context markers)
3. Parse `$ARGUMENTS` for amendment details already supplied.
4. Share what you found with the user and highlight any inconsistencies or prerequisites.

**Decision Context Check**:
- If the constitution documents architectural patterns, testing philosophy, and error handling patterns, it's modern.
- If it's old-style (prescriptive without documented decisions), flag a modernization opportunity.

---

## Step 2: Collaborative Requirements Gathering

Engage the user to collect or confirm:
- Summary (concise, under 80 characters)
- Detailed rationale (why now, what problem it solves)
- Amendment type candidates (major/minor/patch) with preliminary reasoning
- Target section(s) and stakeholders/impacts
- Author attribution (if different from user)

Validate user intent by restating the amendment in your own words and asking for confirmation before proceeding.

---

## Research Phase for Pattern-Based Amendments (Capability-Aware)

**If the amendment introduces new patterns, technologies, or architectural changes, conduct research before proceeding.**

### When to Trigger Research

Scan the amendment summary and rationale for research-worthy topics.

**Reference:** `features/constitution/templates/decision_points.yaml` section `research_triggers` contains comprehensive patterns for detecting when research is valuable (architecture, frameworks, language versions, compliance).


### Limited Research Mode

When the amendment introduces patterns you're uncertain about:

1. Flag the uncertainty and ask the user for resources/docs they're following
2. Confirm the specific requirements they want to codify
3. Note any knowledge limitations in the final report


### Skip Research When

- Amendment is clarifying existing language (patch)
- Amendment adjusts thresholds (e.g., coverage 70% -> 75%)
- Amendment removes outdated requirements
- User explicitly states they don't need research
---

## Step 3: Impact Analysis

Investigate how the amendment interacts with the current constitution:
- Locate the relevant section(s) and quote the existing language
- Identify supporting artifacts (tests, configs, agent instructions) that justify or conflict with the change
- If the amendment introduces new standards, verify they align with actual codebase practices
- Summarize findings: current state -> desired state -> evidence

**Special Considerations for Architectural/Pattern Amendments**:

If the amendment affects architectural sections:
1. Check if the section exists - adding to old-style constitution is a minor amendment
2. Suggest documenting the full decision context (pattern, error handling, rationale)
3. Reality check - does the codebase actually follow this pattern?

---

## Step 4: Decide Amendment Type & Version Bump

Compare the planned change against semantic versioning rules:
- **Major**: breaks existing requirements or core principles
- **Minor**: introduces new requirements without breaking existing ones
- **Patch**: clarifies or corrects wording only

Present your recommendation with evidence and confirm with the user before applying.

---

## Step 5: Apply Amendment via CLI

Once all fields are ready, run:
```bash
oak constitution add-amendment \
  --summary "{SUMMARY}" \
  --rationale "{RATIONALE}" \
  --type "{TYPE}" \
  --author "{AUTHOR}" \
  {OPTIONAL_ARGS}
```

After execution:
- Re-open `oak/constitution.md` and verify the amendment was applied correctly
- Check metadata version and last amendment date were updated
- Document any discrepancies and fix manually if needed

---

## Step 6: Agent Instruction File Alignment

1. Detect current agent instruction files:
   ```bash
   oak constitution list-agent-files --json
   ```

2. For each existing file, assess how the new amendment affects it

3. Present a synchronization plan to the user:
   - Files to update
   - Exact changes (version bump, date, additional guidance)
   - Backups will be created automatically

4. Only after approval:
   ```bash
   oak constitution update-agent-files --dry-run  # Preview
   oak constitution update-agent-files            # Apply
   ```

---

## Step 7: Quality Review & Final Report

Perform self-check:
- Amendment type and version bump alignment
- Consistency between constitution metadata and amendment entries
- Agent instruction files reference latest version

Provide rubric scores (1-5) for:
- Clarity & Enforceability
- Alignment with existing practices
- Completeness of downstream updates
- Risk level

Offer to run validation: `oak constitution validate --json`

Summarize: old version -> new version, amendment type, files updated, next steps.

---

## Response Expectations

- Maintain collaborative tone; pause for user confirmation at critical junctures
- Reference commands executed and explain conclusions drawn
- Protect existing instructions - never overwrite without explicit user agreement
- Ensure all steps are traceable and actionable