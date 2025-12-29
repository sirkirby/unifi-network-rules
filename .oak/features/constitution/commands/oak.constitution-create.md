---
description: Create an engineering constitution for the project by analyzing the codebase and gathering project information.
handoffs:
  - label: Validate Constitution
    agent: oak.constitution-validate
    prompt: Validate the constitution for correctness, completeness, and quality.
---

## User Input

```text
$ARGUMENTS
```

You **MUST** incorporate any provided context before prompting the user.

## Purpose

Lead the constitution creation process end-to-end. Gather facts, form judgments, and use CLI tools only to support or record your reasoning. You remain accountable for the structure, enforceability, and clarity of the final constitution.

{% include 'includes/cli_discovery.md' %}

{% if is_high_reasoning %}
{% include 'includes/flow_control_high.md' %}

{% include 'includes/workflow_overview_high.md' %}
{% else %}
{% include 'includes/flow_control_basic.md' %}

{% include 'includes/workflow_overview_basic.md' %}
{% endif %}

---

{% include 'includes/project_analysis.md' %}

---

## Discovery Strategy (Agent-Led)

Plan your investigation before running commands:
- Identify directories to inspect (`src/`, `tests/`, `.github/workflows/`, `docs/`, etc.)
- List questions you need answered (e.g., "How are services structured?", "What is the testing coverage goal?")
- Share the plan with the user; invite clarifications or additional areas of interest.

## Evidence Collection

Use CLI tools to gather evidence. Prefer targeted commands over broad scans:
- `ls`, `tree`, `find` for structure reconnaissance
- `rg`/`grep` for spotting conventions (coverage thresholds, lint configs, ADR mentions)
- `cat`, `python` scripts, or `jq/yq` to summarize config values

For each discovery session:
- Capture the command, a concise output summary, and the implication
- When an agent instruction file already exists, read its content, summarize key rules, and tag each with the constitution section it should influence
- Flag conflicting or missing information for user review

---

{% include 'includes/research_phase.md' %}

---

## Synthesis

Compile your findings into a working outline before generating content:
- Create a table mapping evidence -> source -> constitution section -> proposed requirement
- Note which areas need clarification or additional assumptions
- Highlight any legacy-agent guidance you plan to reconcile or supersede
- Review with the user; pause if major decisions require approval

---

{% include 'includes/relevance_assessment.md' %}

---

{% if is_high_reasoning %}
{% include 'includes/decision_gathering_high.md' %}
{% else %}
{% include 'includes/decision_gathering_basic.md' %}
{% endif %}

---

{% include 'includes/generation_phase.md' %}

---

{% if is_high_reasoning %}
{% include 'includes/completion_high.md' %}
{% else %}
{% include 'includes/completion_basic.md' %}
{% endif %}

---

## Response Expectations

- Maintain interactive tone; pause for user input at key decision points
- Cite commands run and the conclusions drawn from them
- Keep the user informed of assumptions, especially when evidence is missing
- Ensure all instructions you provide to the user are actionable and grounded in discovered facts

## Critical Rules: No Defaults Without Asking

**NEVER assume or apply defaults for:**
- Testing requirements (coverage targets, TDD vs test-after, E2E)
- Code review processes (strict vs flexible)
- Documentation standards (extensive vs minimal)
- CI/CD enforcement (blocking vs advisory)

**ALWAYS ask explicitly when:**
- The user hasn't provided specific requirements
- Brownfield analysis reveals gaps in existing standards
- Multiple reasonable options exist

**The goal is user-driven decisions, not AI-assumed defaults.**
