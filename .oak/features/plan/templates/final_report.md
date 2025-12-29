## Stop and Report

After creating the plan, provide a comprehensive summary:

```text
## Plan Created

**Plan:** <plan-name>
**Display Name:** <Human Readable Name>
**Branch:** <branch_name>
**Location:** oak/plan/<name>/plan.md
**Source:** <Issue #ID | Idea>

### Overview
<Brief summary of the plan>

### Requirements Source
{% raw %}
{# For issue-based plans #}
- **Issue**: {provider} #{id} - {title}
- **Acceptance Criteria**: {count} criteria mapped to tasks
- **Test Cases**: {count} test cases from issue
- **Parent Context**: {parent issue info if exists}
- **Related Items**: {count} items analyzed for context

{# For idea-based plans #}
- **Goals Defined**: {count} goals
- **Research Topics**: {count} topics identified
- **Scope**: {in-scope summary}
{% endraw %}

### Task Breakdown
- **Phase 1 (Setup)**: {count} tasks
- **Phase 2 (Implementation)**: {count} tasks
- **Phase 3 (Testing)**: {count} tasks
- **Phase 4 (Integration)**: {count} tasks
- **Phase 5 (Polish)**: {count} tasks
- **Total**: {total count} specific, actionable tasks

### Key Findings
- **Patterns Identified**: {list key patterns found}
- **Test Strategy (from constitution)**: {TDD/test-after, coverage %, required/optional}
- **Constitution Rules**: {count} MUST rules, {count} SHOULD rules documented
- **Unknowns Resolved**: {count} NEEDS CLARIFICATION items addressed

### Constitution Compliance
- ✅ All MUST rules satisfied
- ⚠️ {count} SHOULD rules require consideration (documented in plan)
- ℹ️ Test strategy: {constitution test requirements summary}

### Next Steps
1. Review plan.md to confirm approach and tasks
2. {% raw %}{# For idea-based #}{% endraw %}Begin research: /oak.plan-research <plan-name>
3. Validate plan: /oak.plan-validate
4. Once validated, implement: /oak.plan-implement
```

**Command ends here.** The user should review the plan before proceeding.

## Notes

- **CLI is scaffolding only**: Commands are deterministic utilities for data gathering and artifact creation. All reasoning about code design, patterns, and implementation strategy is your responsibility.
- **You drive exploration**: Use your full toolset (grep, find, git, read files, etc.) to understand the codebase.
- **Constitution is authoritative**: The project's `oak/constitution.md` always overrides general guidance. Read it thoroughly and apply its rules.
- **Testing strategy**: Always identify test patterns and extract test requirements from the constitution. Plan test creation according to constitution requirements (may be mandatory, recommended, or optional).
- **Git errors**: If git operations fail (e.g., dirty worktree, merge conflicts), explain the error clearly and wait for the user to resolve it before proceeding.
- **Plan is a living document**: The plan.md file should be updated as you learn more during exploration and implementation.
- **Issue-based plans**: Leverage structured data from issue providers (acceptance criteria, test cases, parent/child relationships) to create specific, actionable tasks.
- **Constitution-driven testing**: Extract test requirements from `oak/constitution.md` and apply them when creating testing tasks.
