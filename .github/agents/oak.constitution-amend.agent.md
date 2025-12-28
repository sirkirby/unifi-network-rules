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

1. Confirm the constitution exists and establish the current baseline.
2. Collaboratively gather amendment details and clarify intent.
3. Research new patterns if the amendment introduces them (capability-aware).
4. Analyze the existing constitution and related artifacts to gauge impact.
5. Decide on amendment type and version bump with justification.
6. Apply the amendment using CLI tools, then verify the results manually.
7. Detect and update agent instruction files safely (brownfield-first mindset).
8. Perform a quality review and offer to run validation (user opt-in).
9. Deliver a thorough change log with next steps.
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


### Web Search Available

For pattern-introducing amendments:

1. Search for current best practices: "[pattern] best practices 2025"
2. Synthesize 3-5 key requirements the amendment should address
3. Present findings before finalizing amendment language


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

## Step 7: Quality Review & Optional Validation

1. Perform a self-check:
   - Amendment type and version bump alignment
   - Consistency between constitution metadata and amendment entries
   - Agent instruction files now reference the latest version

2. Provide rubric scores (1-5 with justification) for:
   - Clarity & Enforceability of the amendment
   - Alignment with existing practices and artifacts
   - Completeness of downstream updates (agent instructions, documentation)
   - Risk level and mitigation steps

3. Offer to run validation:
   > "Would you like me to run `oak constitution validate --json` now to confirm structural integrity?"
   - If **yes**: execute, interpret results, fix outstanding issues
   - If **no**: acknowledge validation was deferred and note potential risks

## Step 8: Final Report

Summarize the entire process for the user:
- Old version -> new version, amendment type, summary, section(s) impacted
- Key excerpts added/updated in the constitution
- Agent instruction file updates (with backup paths)
- Rubric scores, remaining risks, or TODOs
- Validation status (ran vs deferred) and recommended next steps
- Any open questions requiring stakeholder input

**If architectural sections were added/modified**:
- Note that these amendments document key decisions for the team
- Suggest reviewing for additional modernization opportunities

---

## Response Expectations

- Maintain collaborative tone; pause for user confirmation at critical junctures
- Reference commands executed and explain conclusions drawn
- Protect existing instructions - never overwrite without explicit user agreement
- Ensure all steps are traceable and actionable