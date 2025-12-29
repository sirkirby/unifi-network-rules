## Issue-Based Planning

You're planning from a tracked issue. This path leverages structured data from your issue tracker to create a more specific, actionable plan.

### Issue Provider Prerequisites

1. **Issue Provider Configuration** (REQUIRED): The user must have configured their issue provider.
   - If not configured, **STOP** and instruct the user: "Please run `oak config` to configure your issue provider (Azure DevOps or GitHub Issues) before creating a plan from an issue."
   - **NEVER run `oak config` on behalf of the user** - it requires interactive setup in the terminal.
   - To check configuration status: Read `.oak/config.yaml` directly (e.g., `cat .oak/config.yaml`) and look for `issue` section with provider details.
   - Alternatively, run `oak config issue-provider show` (non-interactive) to see formatted config output.

2. **Issue ID** (REQUIRED): You must have an issue identifier to fetch.
   - If the user hasn't provided one, **ask**: "What is the issue ID? (e.g., Azure DevOps work item #12345 or GitHub issue #42)"

### Issue Fetching Strategy

{% if has_background_agents %}
#### Parallel Issue Fetching with Background Agents

**For issues with many related items, parallelize the fetching process.**

When the focus issue has 3+ related items (parents, children, dependencies):

**Parallel Fetch Workflow:**

```text
┌─────────────────────────────────────────────────────┐
│ Issue Fetch Orchestrator                             │
├─────────────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌──────────┐          │
│  │  Focus   │  │  Parent  │  │  Child   │          │
│  │  Issue   │  │  Issues  │  │  Issues  │          │
│  └──────────┘  └──────────┘  └──────────┘          │
│       │              │             │                │
│       └──────────────┴─────────────┘                │
│                    │                                │
│          Merge Context Summaries                    │
└─────────────────────────────────────────────────────┘
```

**Benefits of parallel fetching:**
- Faster context gathering for complex issue hierarchies
- Reduced wait time for large epics with many children
- Parallel summary generation for related items

**Subagent Fetch Template:**

```markdown
# Related Issue Fetch Assignment

## Context
- **Focus Issue:** <provider> #<focus-id>
- **Output Directory:** oak/plan/<name>/issue/related/<id>/

## Your Assignment

Fetch and summarize related issue: **<provider> #<related-id>**

**Relationship:** <parent|child|dependency|sibling>

## Deliverables

1. Fetch issue details via CLI: `oak plan issue --fetch-only <id>`
2. Create summary.md with:
   - Title, description, acceptance criteria
   - Relationship context to focus issue
   - Relevant implementation hints

## Output

Return summary and any blockers encountered.
```

{% else %}
#### Sequential Issue Fetching

Fetch focus issue first, then related items in order of relevance (parents before children, dependencies before siblings).
{% endif %}

{% if has_native_web %}
#### Web-Enriched Issue Context

When issues reference external resources:
- Fetch linked documentation or specs
- Check for related discussions or decisions
- Validate external API or service references
{% endif %}

{% if has_mcp %}
#### MCP-Enhanced Fetching

Leverage MCP tools for richer context:
- **Issue provider tools**: Direct API access for detailed metadata
- **Document fetch**: Retrieve linked documents and attachments
- **Search tools**: Find related issues not explicitly linked
{% endif %}

### Understanding the Focus Issue

- The issue you pass is the **focus** of your implementation.
- It might be a Story with child Tasks, or a Task with a parent Story and Epic - the focus is what you're implementing.
- All hierarchical relationships (parents, children, siblings, dependencies) are fetched automatically as **context**.
- The directory structure is always based on the **focus issue**, with related items stored in `related/{id}/` subdirectories.
- The plan.md includes sections for Parent, Child, and Related Issues (Context) so you understand the full scope.
- Example: If you pass Task #456 (which has parent Story #123), the directory is `oak/plan/{name}/issue/` with the parent story context at `oak/plan/{name}/issue/related/123/summary.md`.

### Execute Issue Fetch

Once prerequisites are met, run:

```bash
oak plan issue <NAME> --id <ISSUE_ID> [--provider <key>]
```

The CLI will:
- Validate prerequisites (constitution, issue provider config)
- Fetch the issue from the provider
- Write artifacts to `oak/plan/{name}/issue/`:
  - `summary.md` - Agent-friendly summary with all issue details
  - `plan.md` - Implementation plan skeleton
- Create/switch to an implementation branch prefixed with the issue ID

### Verify Branch

After running the command, verify you're on the correct implementation branch:

```bash
git branch --show-current
```

The branch name is saved in the plan context and will be used consistently across all plan operations.

### Discover Artifacts

Use `oak plan show <NAME>` to discover:
- All artifact paths (context, plan, codebase)
- The saved branch name for this issue
- Related issues (parents, children, etc.)
- JSON output available with `--json` flag for parsing

**Generated Files:**

**`summary.md`**
- Issue title, description, acceptance criteria from the provider
- Labels/tags, assigned user, status, priority, effort
- Type-specific fields (test steps for Test Cases, repro steps for Bugs)
- Related issues with simplified relationship types
- Clean, agent-friendly markdown format optimized for LLM consumption
- Use this as your primary source for requirements understanding

**`plan.md`**
- Structured implementation plan skeleton with sections:
  - **Objectives**: What success looks like
  - **Approach**: Technical strategy and design decisions
  - **Tasks**: Step-by-step work breakdown
  - **Risks & Mitigations**: Known blockers and solutions
  - **Definition of Done**: Completion criteria and verification steps
- Fill in the details during codebase exploration and constitution review

**Related Items** (discovered via `oak plan show`)
- Run `oak plan show <NAME>` to see all related issues with their paths
- Context for parent issues (epics, stories above the focus)
- Context for child issues (tasks, sub-tasks below the focus)
- Context for other related items (dependencies, pull requests, etc.)
- Helps understand the bigger picture and downstream impacts
- All related items are for **context only** - the focus issue drives the implementation
