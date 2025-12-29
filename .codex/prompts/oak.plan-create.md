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

## Planning Source Decision

Before we begin, I need to understand what we're planning:

**Are you planning from:**

1. **A tracked issue** (Azure DevOps work item, GitHub issue, etc.)
   - You have an existing ticket/story/task to implement
   - Requirements are already documented in your issue tracker

2. **An idea or concept** (no existing issue)
   - You have an idea that needs scoping and planning
   - Requirements will be gathered through clarifying questions

**How to indicate your choice:**
- If you have an issue ID, mention it (e.g., "ADO #12345", "GitHub issue #42", or just "#123")
- If starting from an idea, describe what you want to plan

**Parse $ARGUMENTS to detect:**
- Issue ID patterns: `#\d+`, `ADO \d+`, `GitHub #\d+`, `issue \d+`
- If no issue pattern detected, assume idea-first planning
- If ambiguous, ask the user to clarify
**Based on $ARGUMENTS, determine the path:**

- **Issue detected** (e.g., "#123", "ADO 12345", "GitHub issue #42") → Proceed to Issue-Based Planning
- **No issue detected** → Proceed to Idea-Based Planning
- **Ambiguous** → Ask the user to clarify

---

## Step 2A: Issue-Based Planning (if issue detected)

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

#### Sequential Issue Fetching

Fetch focus issue first, then related items in order of relevance (parents before children, dependencies before siblings).



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
**After fetching issue context, skip to Step 3.**

---

## Step 2B: Idea-Based Planning (if no issue)

## Idea-Based Planning

You're planning from an idea or concept. This path gathers requirements through clarifying questions to build a comprehensive plan.

### Clarifying Questions Phase

Before creating the plan, gather essential context:

**Scope Questions:**
- What is the primary objective of this plan?
- What problem are we solving or opportunity are we pursuing?
- What is in scope? What is explicitly out of scope?
- What are the key constraints (technical, timeline, resources)?

**Research Questions:**
- What unknowns need investigation before implementation?
- Are there competing approaches to evaluate?
- What external resources, APIs, or tools might be involved?
- What existing codebase patterns should inform this work?

**Success Questions:**
- How will we know when this is complete?
- What are the acceptance criteria for success?
- Who are the stakeholders and what do they need?

**Present questions strategically:**
- Group related questions together
- Provide examples or defaults where helpful
- Prioritize questions that unlock other answers

### Create Plan Structure

Once you have sufficient context:

```bash
# Create the plan with a URL-safe name
oak plan create <plan-name> --display-name "Human Readable Name"

# Example:
oak plan create auth-redesign --display-name "Authentication System Redesign"
```

The CLI will:
- Create `oak/plan/<plan-name>/` directory
- Initialize `plan.md` with basic structure
- Create `.manifest.json` with metadata
- Create `research/` directory for findings
- Create a git branch `plan/<plan-name>`

### Populate Plan Content

Edit `oak/plan/<plan-name>/plan.md` to include:

**Overview Section:**
- Executive summary of what this plan achieves
- Problem statement or opportunity description
- High-level approach

**Goals Section:**
- 3-5 specific, measurable objectives
- Each goal should be testable/verifiable

**Success Criteria Section:**
- How success will be measured
- Specific outcomes or deliverables

**Scope Section:**
- What's in scope (features, components, etc.)
- What's explicitly out of scope
- Known boundaries and limitations

**Constraints Section:**
- Technical constraints (languages, frameworks, APIs)
- Resource constraints (time, team, budget)
- Organizational constraints (approvals, dependencies)

### Identify Research Topics

Based on the clarifying conversation, create research topics:

**Research Topic Structure:**
```markdown
### Topic Title
**Slug:** `url-safe-slug`
**Priority:** 1-5 (1 = highest)
**Status:** pending

Description of what to research and why.

**Questions to answer:**
- Specific question 1?
- Specific question 2?

**Sources to check:**
- Documentation links
- Similar projects
- Internal resources
```

**Good Research Topics:**
- Technology comparisons (e.g., "OAuth Providers")
- Architecture patterns (e.g., "Event Sourcing Patterns")
- Integration approaches (e.g., "Payment Gateway APIs")
- Codebase analysis (e.g., "Existing Auth Patterns")

**Research Depth:**
- `minimal`: Quick validation, 1-2 sources
- `standard`: Comprehensive overview, 3-5 sources (default)
- `comprehensive`: Deep dive, extensive sources, comparisons
**After gathering requirements, proceed to Step 3.**

---

## Step 3: Constitution Alignment

## Constitution Alignment

Read the project constitution and identify rules relevant to this work:

```bash
# Read the full constitution
cat oak/constitution.md

# Or search for specific guidance
rg "MUST" oak/constitution.md
rg "SHOULD" oak/constitution.md
rg "testing" oak/constitution.md -i
rg "documentation" oak/constitution.md -i
```

**Extract and apply:**
- **Code Standards**: Type hints, docstrings, naming conventions, formatting rules
- **Testing Requirements**: Coverage expectations, test patterns, test organization
- **Documentation Standards**: What requires docs, format guidelines, examples
- **Review Protocols**: Approval requirements, validation steps, merge criteria

**Update plan.md** to explicitly reference applicable constitution rules in your approach section.

### Constitution Compliance Check & Test Strategy Extraction

Create a Constitution Check section in your plan analysis:

**Load constitution rules:**
```bash
# Extract MUST rules
rg "MUST" oak/constitution.md

# Extract SHOULD rules
rg "SHOULD" oak/constitution.md

# Find relevant sections
rg "testing|documentation|code standards" oak/constitution.md -i

# Extract test strategy specifically
rg "test.*first|TDD|coverage|unit.*test|integration.*test" oak/constitution.md -i
```

**Extract test strategy from constitution:**
- **Test timing**: Does constitution require test-first (TDD) or allow test-after?
- **Coverage requirements**: What coverage % is required? Are there exemptions?
- **Test organization**: Where do tests live? What naming conventions?
- **Test types**: Are unit tests required? Integration tests? E2E tests?
- **Flexibility**: Is testing strictly required or recommended/optional?

**Check compliance:**
- ✅ **PASS**: Implementation approach follows all MUST rules
- ⚠️ **NEEDS ATTENTION**: SHOULD rule requires consideration
- ❌ **VIOLATION**: MUST rule cannot be met (requires justification)

**Document in plan.md:**
```markdown
## Constitution Compliance

### Test Strategy (from constitution)
- **Timing**: Test-after allowed (not strict TDD)
- **Coverage**: 80% minimum required for new code
- **Required**: Unit tests for all public functions
- **Optional**: Integration tests recommended for workflows
- **Organization**: Tests mirror src/ structure in tests/

### MUST Rules
- ✅ All public functions have type hints (constitution Section 4.1)
- ✅ Tests required for new functionality (constitution Section 7.1)
- ✅ No magic strings - use constants (constitution Section 4.4)

### SHOULD Rules
- ⚠️ Consider extracting helper to shared utilities (constitution Section 4.2)
  - Approach: Will add to existing utils module per constitution pattern

### Violations (if any)
- ❌ None - all MUST rules satisfied
```

**Use test strategy for task planning**: Apply the constitution's test requirements when creating testing tasks. If constitution is strict, make all tests explicit. If flexible, suggest optional tests.
---

## Step 4: Systematic Codebase Exploration

## Systematic Codebase Exploration

**Step 1: Find Similar Features**

```bash
# Search for related functionality
rg "keyword_from_plan" src/
rg "class.*Service" src/           # If implementing a service
rg "class.*Command" src/commands/  # If implementing a command
rg "def test_" tests/               # Find test patterns
```

**Step 2: Identify Patterns**
- Look at 2-3 similar implementations
- Note common patterns: error handling, logging, validation, type hints
- Check how they're tested (unit tests, integration tests, fixtures)
- Review recent changes: `git log -p --since="1 month ago" path/to/relevant/`
- Check imports and dependencies used by similar code

**Step 3: Understand Testing Strategy**

```bash
# Find test files for similar features
find tests/ -name "*similar_feature*"

# See how services are tested
rg "class Test.*Service" tests/

# Check test fixtures and mocking patterns
rg "@pytest.fixture" tests/
rg "Mock" tests/
```

**Step 4: Document Findings**
- Update `plan.md` with patterns you found
- Note file/module naming conventions
- Document test strategy (where tests go, what patterns to follow)
- Reference specific files/functions as examples

### Identify Unknowns and Questions

Before creating the detailed plan, identify what you don't know yet:

- **Technical unknowns**: Libraries, APIs, or technologies you need to research
- **Integration questions**: How does this connect with existing systems?
- **Pattern questions**: Which approach best fits the codebase?
- **Constitution gaps**: Are there constitution rules that need clarification?

**For each unknown:**
- Mark it as **NEEDS CLARIFICATION** in your notes
- Ask the user directly if it's something they can answer
- Document what research is needed if it requires investigation

**Examples:**
```text
NEEDS CLARIFICATION: Which authentication library is used for API calls?
→ Ask user or search codebase: rg "auth" src/

NEEDS CLARIFICATION: Should validation use Pydantic or custom validators?
→ Check existing patterns: rg "BaseModel" src/

NEEDS CLARIFICATION: Where do shared utilities live?
→ Constitution says "centralized utilities" - check constitution for path
```

**Resolve before proceeding**: Don't write the full plan until all NEEDS CLARIFICATION items are resolved.
---

## Step 5: Research Strategy

## Research Strategy (Capability-Aware)

### Limited Research Mode

This agent may not have native web search capabilities. During research, focus on:
- Codebase exploration for existing patterns
- General knowledge for established best practices

**When you encounter unfamiliar patterns:**
- Search the codebase for similar implementations
- Ask the user for guidance or documentation
- Note gaps in your notes for follow-up



---

## Step 6: Create Detailed Implementation Plan

## Create Detailed Implementation Plan

Open and edit `oak/plan/<name>/plan.md` to fill in the details:

### A. Plan Sections (Standard)

- **Objectives**: Refined based on requirements (acceptance criteria if from issue, clarifying answers if from idea)
- **Constitution Check**: Document compliance with MUST/SHOULD rules
- **Technical Context**:
  - Technologies/libraries to use
  - Integration points
  - **All NEEDS CLARIFICATION resolved**
- **Approach**:
  - Which patterns you'll follow (reference specific files)
  - Where new code will live (module, class, function names)
  - How you'll handle edge cases
  - Constitution rules you're applying

### B. Task Breakdown (Structured Phases)

Use this phased structure (adjust based on constitution's test strategy):

**Phase 1: Setup & Investigation**
```markdown
- [ ] Setup: Review context (parent issue, related items, or clarifying answers)
- [ ] Setup: Identify affected modules/files from codebase exploration
- [ ] Setup: Install/configure any new dependencies per constitution
- [ ] Setup: Create feature branch (already done by CLI)
```

**Phase 2: Core Implementation**
```markdown
# Map to acceptance criteria (from issue) or goals (from idea)
- [ ] Implement: [Requirement 1]
  - File: [specific file path]
  - Function/Class: [specific names]
  - Pattern: [reference to similar implementation]
- [ ] Implement: [Requirement 2]
  - File: [specific file path]
  - Function/Class: [specific names]
  - Pattern: [reference to similar implementation]
# Continue for all requirements
```

**Phase 3: Testing** (constitution-driven)
```markdown
# Test phase structure depends on constitution guidance:
# - If constitution requires test-first (TDD): Phase 3 becomes Phase 2
# - If constitution requires high coverage: Create explicit tasks for each test scenario
# - If constitution is flexible: Make testing optional but recommended

# If issue includes test cases, convert them to tasks:
- [ ] Test: [Test case title]
  - Test file: [specific test file path per constitution structure]
  - Test function: test_[specific_name]
  - Covers: [requirement reference]

# If constitution requires comprehensive testing, add:
- [ ] Test: Unit tests for [component] (per constitution coverage requirements)
- [ ] Test: Integration tests for [workflow] (if required by constitution)
- [ ] Test: Edge case handling for [scenario]

# If constitution is flexible on testing, make it optional:
- [ ] (Optional) Test: Consider adding tests for [critical paths]
```

**Phase 4: Integration**
```markdown
# Consider integration with related systems/issues
- [ ] Integration: Connect with [related component]
- [ ] Integration: Verify compatibility with [system component]
- [ ] Integration: Test end-to-end workflow
```

**Phase 5: Polish & Documentation**
```markdown
- [ ] Documentation: Update [specific files per constitution]
- [ ] Documentation: Add inline code comments for complex logic
- [ ] Documentation: Update API docs (if applicable)
- [ ] Quality: Run linters and formatters per constitution
- [ ] Quality: Verify constitution compliance (all MUST rules)
- [ ] Quality: Review against definition of done
```

### Task Guidelines

- **Be specific**: "Add user_id validation to IssueService.validate_provider()" not "Add validation"
- **Reference files**: Always include actual file paths and function/class names
- **Map to requirements**: Each requirement should have at least one implementation task
- **Leverage test cases**: If issue includes test cases, create corresponding test tasks
- **Constitution-driven testing**:
  - Read constitution's test strategy (TDD vs test-after, coverage requirements, test organization)
  - Adjust phase order if constitution requires test-first approach
  - Make testing explicit if constitution has strict requirements, optional if flexible
- **Constitution alignment**: Reference specific constitution rules in relevant tasks

### C. Additional Plan Sections

- **Testing Strategy** (constitution-driven):
  - **Constitution requirements**: Document what the constitution mandates (TDD, coverage %, test organization)
  - **Test timing**: Test-first (TDD) or test-after (per constitution guidance)
  - **Unit tests**: Specific test files and functions to write (if required/recommended)
  - **Integration tests**: Specific scenarios to test (if required/recommended)
  - **Test fixtures**: Reference existing patterns found in codebase exploration
  - **Expected coverage**: Per constitution requirements (or recommend % if flexible)
  - **Optional tests**: If constitution is flexible, suggest additional valuable tests
- **Risks & Mitigations**: Technical blockers and solutions
- **Definition of Done**:
  - ✅ All requirements met
  - ✅ Tests written and passing (per constitution coverage)
  - ✅ Documentation updated (per constitution standards)
  - ✅ Constitution standards followed (all MUST rules)
  - ✅ Code reviewed (if required by constitution)
---

## Step 7: Stop and Report

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
2. {# For idea-based #}Begin research: /oak.plan-research <plan-name>
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