---
description: Generate structured tasks with acceptance criteria from plan and research findings.
requires:
  - path: oak/plan/<plan-name>/plan.md
    error: "Run /oak.plan first to create a plan."
  - path: oak/plan/<plan-name>/research/
    error: "Run /oak.plan-research first to complete research (or skip if no topics defined)."
  - path: oak/constitution.md
    error: "Constitution required for standards compliance."
generates:
  - oak/plan/<plan-name>/tasks.md
  - Updates to oak/plan/<plan-name>/.manifest.json
handoffs:
  - label: Implement Tasks
    agent: oak.plan-implement
    prompt: Begin implementation of the generated tasks with progress tracking and verification.
  - label: Export to Issues
    agent: oak.plan-export
    prompt: Export the generated tasks to your configured issue provider (GitHub Issues or Azure DevOps).
---

## User Input

```text
$ARGUMENTS
```

This should be a plan name or can be inferred from the current git branch.

## Interaction Guidelines

**Always ask when:**
- Task granularity needs adjustment (too coarse/fine)
- Priority assignment is unclear
- Dependencies between tasks are ambiguous
- Scope of tasks seems to exceed plan goals

**Proceed without asking when:**
- Plan has clear goals and research findings
- Standard task breakdown applies
- Tasks map naturally to plan structure

## Responsibilities

1. Load the plan and all research findings.
2. Generate structured tasks with clear acceptance criteria.
3. Organize tasks by type (epic, story, task, subtask).
4. Identify dependencies between tasks.
5. Create `tasks.md` with the complete task list.
6. Summarize and prepare for issue export.

## Task Generation Strategy

{% if has_background_agents %}
### Parallel Task Generation with Background Agents (DEFAULT)

**You MUST use parallel task generation when the plan contains 3+ distinct areas.**

Parallel task generation is the DEFAULT mode for this agent. Only fall back to sequential when areas have tight dependencies requiring sequential context.

**REQUIRED for parallel generation (all must be true):**
- 3+ distinct areas (epics, features, or research topics)
- Areas can be broken into tasks independently
- No area's tasks require knowing another area's task structure first

**Parallel Generation Approach:**

```text
┌─────────────────────────────────────────────────────┐
│ Task Generation Orchestrator                         │
├─────────────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌──────────┐          │
│  │ Epic 1   │  │ Epic 2   │  │ Epic 3   │          │
│  │ Tasks    │  │ Tasks    │  │ Tasks    │          │
│  └──────────┘  └──────────┘  └──────────┘          │
│       │              │             │                │
│       └──────────────┴─────────────┘                │
│                    │                                │
│        Merge & Resolve Dependencies                 │
└─────────────────────────────────────────────────────┘
```

#### Launching Background Agents

**HOW TO LAUNCH:** {{ background_agent_instructions }}

For each area, use this delegation prompt:

```markdown
# Task Generation Assignment: <Epic/Area>

## Context
- **Plan:** oak/plan/<plan-name>/plan.md
- **Constitution:** oak/constitution.md
- **Research:** oak/plan/<plan-name>/research/<topic>.md

## Your Focus Area

**Epic/Feature:** <Epic Title>
**Research Topics:** <Relevant topic slugs>

## Generate Tasks For

<Scope description from plan>

## Task Requirements

Each task MUST include:
- ID (use prefix: <E1.T1, E1.T2, etc.>)
- Title, Description, Type, Priority
- Acceptance Criteria (testable)
- Dependencies (within your scope)
- Research References

## Output Format

Return tasks in YAML:
```yaml
tasks:
  - id: "E1.T1"
    title: "<title>"
    type: "task"
    priority: "high"
    acceptance_criteria:
      - "<criterion 1>"
    dependencies: []
    research_refs: ["<topic-slug>"]
```
```

**After parallel generation:**
1. Merge task lists from all agents
2. Resolve cross-epic dependencies
3. Validate no duplicate IDs
4. Order by priority and dependencies

**DECISION GATE: Before generating tasks, you MUST:**

1. Count distinct areas (epics, features, research topics) in the plan
2. Determine if areas can be processed independently
3. Choose execution mode based on criteria above

**MANDATORY OUTPUT before proceeding:**
```text
## Task Generation Mode Decision

Distinct areas found: [X]
Areas can be processed independently: [Yes/No]
Areas with dependencies: [list or "none"]

**Decision: [PARALLEL / SEQUENTIAL]**
**Reason:** [Brief explanation]
```

**If PARALLEL selected, create task-generation manifest and launch background agents.**

{% else %}
### Sequential Task Generation (Fallback)

Generate tasks for each epic/area one at a time when background agents are not available.
{% endif %}

{% if has_native_web %}
### Web-Informed Task Generation

When generating tasks for unfamiliar domains:
- Search for industry-standard task breakdowns
- Reference similar project implementations
- Check for common pitfalls and edge cases to address
{% endif %}

{% if has_mcp %}
### MCP-Enhanced Generation

Leverage MCP tools for task enrichment:
- **Estimation tools**: Get effort estimates from historical data
- **Dependency analysis**: Automated dependency detection
- **Pattern matching**: Find similar tasks in other projects
{% endif %}

## Task Structure

Each task MUST include:

| Field | Description | Example |
|-------|-------------|---------|
| **ID** | Unique identifier | T1, T2, T2.1 (subtasks use parent prefix) |
| **Title** | Clear, actionable title | "Implement OAuth2 token refresh" |
| **Description** | What and why | "Add automatic token refresh to prevent session expiration..." |
| **Type** | Task hierarchy level | epic, story, task, subtask |
| **Priority** | Importance level | critical, high, medium, low |
| **Acceptance Criteria** | Specific, testable conditions | "✓ Tokens refresh 5 min before expiry" |
| **Dependencies** | Task IDs that must complete first | T1, T2.1 |
| **Effort** | Estimate (optional) | "2 hours", "1 day", "3 story points" |
| **Tags** | Categorization labels | backend, security, breaking-change |
| **Research References** | Topic slugs that informed this task | oauth-patterns, token-management |

## Workflow

### 1. Load Plan and Research

```bash
# View plan status
oak plan show <plan-name>

# View research findings
oak plan research <plan-name>
```

Read all artifacts:
- `oak/plan/<plan-name>/plan.md` - Goals, scope, constraints
- `oak/plan/<plan-name>/research/*.md` - All research findings

### 2. Understand the Context

Before generating tasks, ensure you understand:

**From the Plan:**
- Primary objectives and success criteria
- Scope boundaries (in/out of scope)
- Known constraints and limitations
- Constitution requirements that apply

**From Research:**
- Recommended approaches per topic
- Key trade-offs and decisions made
- Dependencies on external systems/APIs
- Identified risks or challenges

### 3. Generate Task Hierarchy

Structure tasks in a logical hierarchy:

**Epic Level (Optional):**
- Major workstreams or phases
- Used when plan spans multiple features
- Example: "E1: Authentication Overhaul"

**Story Level:**
- User-facing capabilities or features
- Maps to plan goals
- Example: "S1: As a user, I can log in with SSO"

**Task Level:**
- Implementation work units
- 1-4 hours of focused work (ideal)
- Example: "T1.1: Implement SAML assertion parsing"

**Subtask Level (Optional):**
- Fine-grained work items
- Used for complex tasks
- Example: "T1.1.1: Add XML signature validation"

### 4. Write Acceptance Criteria

Each task needs testable acceptance criteria:

**Good Acceptance Criteria:**
```markdown
- [ ] OAuth tokens refresh automatically 5 minutes before expiry
- [ ] Failed refresh attempts trigger re-authentication prompt
- [ ] Token refresh works in background without UI interruption
- [ ] Refresh events are logged for debugging
```

**Avoid:**
```markdown
- [ ] It works correctly  (too vague)
- [ ] Good performance    (not measurable)
- [ ] User is happy       (not testable)
```

### 5. Identify Dependencies

Map dependencies between tasks:

```markdown
### T3: Implement token refresh
**Dependencies:** T1, T2

Must complete T1 (token storage) and T2 (refresh endpoint)
before implementing the refresh logic.
```

**Dependency Types:**
- **Hard**: Cannot start without completion
- **Soft**: Can start but cannot complete without
- **External**: Depends on external team/system

### 6. Apply Constitution Requirements

Check constitution for task-specific requirements:

```bash
rg "testing|coverage|documentation" oak/constitution.md -i
```

Add tasks for constitution compliance:
- Testing tasks if coverage is required
- Documentation tasks if docs are mandated
- Review tasks if approvals are needed

### 7. Create Tasks File

Write tasks to `oak/plan/<plan-name>/tasks.md`:

```markdown
# Tasks: <Plan Display Name>

## Overview

Generated from plan and research findings.
- **Total Tasks:** <count>
- **Epics:** <count>
- **Stories:** <count>
- **Tasks:** <count>
- **Subtasks:** <count>

---

## Epics

### E1: <Epic Title> [HIGH]

**Type:** epic
**Priority:** high

<Description of this major workstream>

**Success Criteria:**
- [ ] <High-level criterion 1>
- [ ] <High-level criterion 2>

**Tags:** `<tag1>`, `<tag2>`

---

## Stories

### S1: <Story Title> [MEDIUM]

**Type:** story
**Priority:** medium
**Dependencies:** E1

<User-facing capability description>

**Acceptance Criteria:**
- [ ] <Specific criterion 1>
- [ ] <Specific criterion 2>

**Research References:** `<topic-slug>`
**Tags:** `<tag1>`

---

## Tasks

### T1: <Task Title> [HIGH]

**Type:** task
**Priority:** high
**Dependencies:** S1
**Effort:** 2 hours

<Implementation details>

**Acceptance Criteria:**
- [ ] <Testable criterion 1>
- [ ] <Testable criterion 2>
- [ ] <Testable criterion 3>

**Research References:** `<topic-slug>`
**Tags:** `<tag1>`, `<tag2>`

---

### T2: <Task Title> [MEDIUM]

**Type:** task
**Priority:** medium
**Dependencies:** T1
**Effort:** 4 hours

<Implementation details>

**Acceptance Criteria:**
- [ ] <Testable criterion 1>
- [ ] <Testable criterion 2>

---

## Subtasks

### T2.1: <Subtask Title> [MEDIUM]

**Type:** subtask
**Priority:** medium
**Parent:** T2
**Effort:** 1 hour

<Detailed work item>

**Acceptance Criteria:**
- [ ] <Specific criterion>

---

## Dependency Graph

T1 → T2 → T2.1
     ↘
      T3 → T4
```

### 8. Update Plan Status

```bash
oak plan status <plan-name> ready
```

### 9. Stop and Report

After generating tasks, provide a summary:

```text
## Tasks Generated

**Plan:** <plan-name>
**Total Tasks:** <count>

### Task Summary

| Type | Count | Priority Breakdown |
|------|-------|-------------------|
| Epics | <n> | - |
| Stories | <n> | <high>H / <med>M / <low>L |
| Tasks | <n> | <high>H / <med>M / <low>L |
| Subtasks | <n> | - |

### Critical Path

Tasks that block the most work:
1. **<Task ID>**: <Title> → Blocks <count> tasks
2. **<Task ID>**: <Title> → Blocks <count> tasks

### Research Coverage

| Research Topic | Tasks Referencing |
|----------------|-------------------|
| <topic-1> | T1, T3, T4 |
| <topic-2> | T2, T5 |

### Constitution Compliance

- ✅ Testing tasks included per constitution requirements
- ✅ Documentation tasks added as required
- ✅ Review/approval tasks included if mandated

### Effort Estimate (if provided)

- **Total Effort:** <sum of estimates>
- **Critical Path Duration:** <sum of critical path>

### Artifacts

- Tasks: oak/plan/<plan-name>/tasks.md
- Updated: plan.md with task summary

### Next Steps

1. Review generated tasks
2. Adjust priorities or granularity if needed
3. Export to issues: /oak.plan-export <plan-name>
```

**Command ends here.** The user should review tasks before exporting.

## Task Generation Guidelines

**Right-sized Tasks:**
- Too small: Creates overhead, loses context
- Too large: Hard to track, estimate, or parallelize
- Ideal: 1-4 hours of focused work (for tasks)
- Stories: 1-3 days of work (containing multiple tasks)

**Priority Assignment:**
- **Critical**: Blocks all other work, must be done first
- **High**: Important for success, should be prioritized
- **Medium**: Standard work, done in normal priority
- **Low**: Nice to have, can be deferred

**From Research to Tasks:**
- Each research recommendation should map to tasks
- Trade-offs should inform priority and approach
- Identified risks should have mitigation tasks

## Notes

- **Completeness**: Every plan goal should map to at least one task
- **Testability**: Every task should have testable acceptance criteria
- **Dependencies**: Make dependencies explicit to enable parallelization
- **Estimates**: Optional but helpful for planning
- **Tags**: Use consistently for filtering and organization
- **Constitution**: Include tasks for any required processes (testing, docs, review)
