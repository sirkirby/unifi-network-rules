---
description: Export plan tasks to your configured issue provider (GitHub Issues or Azure DevOps).
requires:
  - path: oak/plan/<plan-name>/tasks.md
    error: "Run /oak.plan-tasks first to generate tasks."
  - path: .oak/config.yaml
    error: "Run oak config to set up your issue provider (GitHub or Azure DevOps)."
generates:
  - Issues in configured provider (GitHub/ADO)
  - Updates to oak/plan/<plan-name>/tasks.md (issue links)
  - Updates to oak/plan/<plan-name>/.manifest.json (export status)
handoffs:
  - label: Begin Implementation
    agent: oak.plan-implement
    prompt: Start implementing the plan with progress tracking and verification.
---

## User Input

```text
$ARGUMENTS
```

This should be a plan name or can be inferred from the current git branch. May optionally include export mode preference (hierarchical or flat).

## Interaction Guidelines

**Always ask when:**
- Export mode (hierarchical vs flat) is not specified
- Issue provider is not configured
- Tasks may create many issues (confirm count)
- Parent issue/epic selection is needed for hierarchical export

**Proceed without asking when:**
- Export mode is clearly specified
- Issue provider is configured and validated
- Task count is reasonable (<20 issues)

## Responsibilities

1. Load the plan and generated tasks.
2. Prompt for export mode: hierarchical or flat.
3. Validate issue provider configuration.
4. Create issues in the configured provider.
5. Update tasks.md with issue links.
6. Mark plan as exported.

## Export Strategy

{% if has_background_agents %}
### Parallel Export with Background Agents (DEFAULT)

**You MUST use parallel export when exporting 10+ tasks.**

Parallel export is the DEFAULT mode for this agent when task count warrants it. Only fall back to sequential for small exports (<10 tasks).

**REQUIRED for parallel export:**
- 10+ tasks to export
- Issue provider is configured and accessible

**Parallel Export Workflow:**

```text
┌─────────────────────────────────────────────────────┐
│ Export Orchestrator                                  │
├─────────────────────────────────────────────────────┤
│  1. Create parent issues (epics/stories) first      │
│                                                     │
│  2. Parallel child issue creation:                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐          │
│  │ Agent 1  │  │ Agent 2  │  │ Agent 3  │          │
│  │ T1-T5    │  │ T6-T10   │  │ T11-T15  │          │
│  └──────────┘  └──────────┘  └──────────┘          │
│       │              │             │                │
│       └──────────────┴─────────────┘                │
│                    │                                │
│      3. Update tasks.md with issue links            │
└─────────────────────────────────────────────────────┘
```

#### Launching Background Agents

**HOW TO LAUNCH:** {{ background_agent_instructions }}

Note: Create parent issues (epics) FIRST sequentially, then parallelize child issue creation.

For each batch, use this delegation prompt:

```markdown
# Issue Export Assignment

## Context
- **Plan:** oak/plan/<plan-name>/plan.md
- **Provider:** <github|azure_devops>
- **Parent Issue:** <parent-issue-id> (if hierarchical)

## Your Assignment

Export these tasks as issues:
- T1: <title>
- T2: <title>
- T3: <title>

## Export Requirements

For each task:
1. Create issue with title, description, acceptance criteria
2. Link to parent issue (if hierarchical mode)
3. Add labels/tags per task tags
4. Set priority if supported

## Output

Return mapping:
```yaml
exports:
  - task_id: "T1"
    issue_id: "<provider-issue-id>"
    url: "<issue-url>"
```

**Orchestration rules:**
- Create parent issues (epics) sequentially first
- Then parallelize child issue creation
- Update tasks.md with all links after completion

**DECISION GATE: Before exporting, you MUST:**

1. Count total tasks to export
2. Verify issue provider is configured
3. Choose execution mode based on task count

**MANDATORY OUTPUT before proceeding:**
```text
## Export Mode Decision

Total tasks to export: [X]
Issue provider: [GitHub/Azure DevOps]
Provider configured: [Yes/No]

**Decision: [PARALLEL / SEQUENTIAL]**
**Reason:** [Task count >= 10 requires parallel / Task count < 10 allows sequential]
```

**If PARALLEL selected, create export manifest and launch background agents after creating parent issues.**

{% else %}
### Sequential Export (Fallback)

Export tasks one at a time when background agents are not available. Respects hierarchy (parents before children).
{% endif %}

{% if has_mcp %}
### MCP-Enhanced Export

Leverage MCP tools for direct provider integration:
- **GitHub MCP**: Direct issue creation via GitHub API
- **Azure DevOps MCP**: Work item creation with full metadata
- **Batch operations**: Create multiple issues in single API calls
{% endif %}

## Export Modes

### Hierarchical Export

Creates parent-child relationships in the issue provider:

**Azure DevOps:**
- Epics → Features → User Stories → Tasks
- Native parent-child work item links
- Full hierarchy preserved

**GitHub Issues:**
- Pseudo-hierarchy using labels and task lists
- Parent issues contain task list checkboxes
- Labels indicate hierarchy level (epic, story, task)

**Best for:**
- Large plans with clear structure
- Teams using agile methodologies
- Work that spans multiple sprints

### Flat Export

Creates all issues at the same level:

- All tasks as individual issues
- Dependencies noted in description
- Labels/tags for categorization

**Best for:**
- Smaller plans
- Teams preferring kanban-style boards
- Simple work tracking needs

## Prerequisites

1. **Issue Provider Configured** (REQUIRED): The user must have configured their issue provider.
   - Check with: `cat .oak/config.yaml` or `oak config issue-provider show`
   - If not configured: "Please run `oak config` to configure your issue provider."

2. **Tasks Generated** (REQUIRED): Plan must have tasks in tasks.md.
   - Check with: `oak plan tasks <plan-name>`
   - If missing: "Please run `/oak.plan-tasks` first to generate tasks."

## Workflow

### 1. Load Plan and Tasks

```bash
# View plan and tasks
oak plan show <plan-name>
oak plan tasks <plan-name>
```

Count and categorize tasks:
- Total issue count
- Breakdown by type (epic, story, task, subtask)

### 2. Prompt for Export Mode

Present options clearly:

```text
## Export Mode Selection

You have <count> tasks ready for export:
- Epics: <n>
- Stories: <n>
- Tasks: <n>
- Subtasks: <n>

**Hierarchical Export:**
- Creates parent-child relationships
- Epics contain stories, stories contain tasks
- Best for structured work tracking
- Provider support: ✅ Azure DevOps (native) / ⚠️ GitHub (labels + task lists)

**Flat Export:**
- All tasks as independent issues
- Dependencies noted in descriptions
- Simpler to manage
- Provider support: ✅ All providers

Which export mode would you like to use?
```

### 3. Validate Provider

Check issue provider configuration:

```bash
# Read config directly
cat .oak/config.yaml

# Or use CLI
oak config issue-provider show
```

Verify:
- Provider is set (ado or github)
- Required credentials are configured
- Provider-specific settings are complete

If validation fails, instruct user to run `oak config`.

### 4. Confirm Export

Before creating issues, confirm:

```text
## Export Confirmation

**Plan:** <plan-name>
**Provider:** <Azure DevOps | GitHub Issues>
**Mode:** <Hierarchical | Flat>
**Issues to Create:** <count>

**Destination:**
- Organization: <org>
- Project/Repo: <project>
- Area Path: <path> (ADO only)

This will create <count> issues in <provider>. Proceed?
```

### 5. Create Issues

For each task, create an issue:

**Issue Content:**
```markdown
# <Task Title>

## Description
<Task description>

## Acceptance Criteria
- [ ] <Criterion 1>
- [ ] <Criterion 2>
- [ ] <Criterion 3>

## Dependencies
Blocked by: <linked issues or task IDs>

## Context
- Plan: <plan-name>
- Research: <topic references>
- Priority: <priority>
- Effort: <estimate>

---
*Generated by open-agent-kit from plan: <plan-name>*
```

**For Hierarchical Export:**
1. Create epics first
2. Create stories linked to epics
3. Create tasks linked to stories
4. Create subtasks linked to parent tasks

**For Flat Export:**
1. Create all issues in priority order
2. Add labels for type (epic, story, task)
3. Note dependencies in descriptions

### 6. Handle Provider Responses

For each created issue, capture:
- Issue ID (work item ID or issue number)
- Issue URL
- Any errors or warnings

### 7. Update Tasks File

Update `tasks.md` with issue links:

```markdown
### T1: Implement OAuth2 token refresh [HIGH]

**Type:** task
**Priority:** high
**Issue:** [#123](https://github.com/org/repo/issues/123) ✅

...
```

### 8. Mark Plan Exported

```bash
oak plan status <plan-name> exported
```

### 9. Stop and Report

After export, provide a summary:

```text
## Export Complete

**Plan:** <plan-name>
**Provider:** <Azure DevOps | GitHub Issues>
**Mode:** <Hierarchical | Flat>

### Issues Created

| Task ID | Title | Issue | Status |
|---------|-------|-------|--------|
| T1 | <Title> | [#123](url) | ✅ |
| T2 | <Title> | [#124](url) | ✅ |
| T3 | <Title> | [#125](url) | ⚠️ Partial |
| ... | ... | ... | ... |

### Summary

- **Total Created:** <count>
- **Successful:** <count>
- **Failed:** <count>
- **Warnings:** <count>

### Hierarchy (if hierarchical)

Epic #<id>: <Title>
├── Story #<id>: <Title>
│   ├── Task #<id>: <Title>
│   └── Task #<id>: <Title>
└── Story #<id>: <Title>
    └── Task #<id>: <Title>

### Provider Links

- Project Board: <link to board/backlog>
- Query/Filter: <link to filtered view>

### Artifacts Updated

- tasks.md: Updated with issue links
- .manifest.json: Status set to "exported"

### Next Steps

1. Review created issues in <provider>
2. Assign team members to issues
3. Set sprint/iteration assignments
4. Begin implementation
```

**Command ends here.** The plan workflow is complete.

## Error Handling

**Authentication Errors:**
```text
❌ Authentication failed with <provider>.
Please verify your credentials:
- Run `oak config` to update configuration
- Check that PAT/token has required permissions
```

**Rate Limiting:**
```text
⚠️ Rate limit reached. Pausing for <seconds> seconds.
Completed: <count>/<total>
Remaining: <count>
```

**Partial Failure:**
```text
⚠️ Some issues failed to create:

| Task | Error |
|------|-------|
| T5 | "Field validation failed: Priority" |
| T8 | "Parent work item not found" |

Successfully created: <count>/<total>
```

## Provider-Specific Notes

### Azure DevOps

- Supports native work item hierarchy
- Work item types: Epic, Feature, User Story, Task, Bug
- Parent-child links are first-class
- Area path and iteration path can be set
- Custom fields may require mapping

### GitHub Issues

- No native hierarchy (flat issue model)
- Hierarchy simulated via:
  - Labels: `type:epic`, `type:story`, `type:task`
  - Task lists in parent issues
  - Issue references in descriptions
- Milestones can group related issues
- Projects (v2) provide board views

## Notes

- **Idempotency**: If export fails midway, re-running will create duplicates. Check for existing issues first.
- **Rate Limits**: Both providers have API rate limits. Large exports may need pacing.
- **Permissions**: Ensure API credentials have permission to create issues.
- **Customization**: Provider-specific fields (area path, custom fields) may need manual adjustment.
- **Issue Links**: Tasks.md is updated with links for reference. Keep this as the source of truth.
