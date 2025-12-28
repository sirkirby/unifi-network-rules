---
description: Create a strategic implementation plan from an idea or tracked issue.
requires:
  - path: oak/constitution.md
    error: "Run /oak.constitution-create first to establish your project's engineering standards."
generates:
  # Always created
  - oak/plan/<plan-name>/plan.md
  - oak/plan/<plan-name>/.manifest.json
  - git branch: plan/<plan-name> or <issue-id>/<plan-name>
  # Issue-based planning (when starting from tracked issue)
  - oak/plan/<plan-name>/issue/summary.md
  - oak/plan/<plan-name>/issue/related/<id>/summary.md
  # Idea-based planning (when starting from scratch)
  - oak/plan/<plan-name>/research/
handoffs:
  - label: Research Topics
    agent: oak.plan-research
    prompt: Research the topics identified in the plan to gather insights and inform task generation.
  - label: Validate Plan
    agent: oak.plan-validate
    prompt: Validate the plan for accuracy and completeness.
---

## User Input

```text
$ARGUMENTS
```

Treat the text supplied after the command as context for the planning session. This may describe an idea, reference a tracked issue, or both.

## Interaction Guidelines

**Always ask when:**
- The planning source (issue vs idea) is ambiguous
- Scope or objectives are unclear
- There are multiple valid approaches to consider
- Key constraints or requirements are missing

**Proceed without asking when:**
- Issue ID is clearly provided (e.g., "ADO #123", "GitHub issue #42")
- Objectives are clearly stated for idea-based planning
- Context is complete and unambiguous

**How to ask effectively:**
- Present specific options when clarifying
- Explain what information is needed and why
- Suggest defaults based on available context

## Purpose

Lead the plan creation process end-to-end. Whether starting from a tracked issue or an idea, you will gather context, explore the codebase, align with the constitution, and produce a detailed implementation plan.

## Workflow Overview

1. **Determine planning source** - Issue or idea?
2. **Gather context** - Fetch issue data OR conduct clarifying questions
3. **Read the constitution** - Extract standards and testing requirements
4. **Explore the codebase** - Find patterns, similar implementations, test strategies
5. **Create detailed plan** - Structured tasks, constitution compliance, definition of done
6. **Report and handoff** - Summary and next steps

---

## Step 1: Planning Source Decision

{% include 'early_triage.md' %}

**Based on $ARGUMENTS, determine the path:**

- **Issue detected** (e.g., "#123", "ADO 12345", "GitHub issue #42") → Proceed to Issue-Based Planning
- **No issue detected** → Proceed to Idea-Based Planning
- **Ambiguous** → Ask the user to clarify

---

## Step 2A: Issue-Based Planning (if issue detected)

{% include 'issue_context.md' %}

**After fetching issue context, skip to Step 3.**

---

## Step 2B: Idea-Based Planning (if no issue)

{% include 'clarifying_questions.md' %}

**After gathering requirements, proceed to Step 3.**

---

## Step 3: Constitution Alignment

{% include 'constitution_compliance.md' %}

---

## Step 4: Systematic Codebase Exploration

{% include 'codebase_exploration.md' %}

---

## Step 5: Research Strategy

{% include 'research_strategy.md' %}

---

## Step 6: Create Detailed Implementation Plan

{% include 'plan_structure.md' %}

---

## Step 7: Stop and Report

{% include 'final_report.md' %}
