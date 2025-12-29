---
description: Implement a plan (research-based or issue-based) with progress tracking and verification.
---

## User Input

```text
$ARGUMENTS
```

**Interpret user intent:**

- **If user provides NO arguments** (just the command): Display context and ask if they want you to proceed with full implementation
- **If user provides ANY text** (e.g., "implement the plan", "complete all tasks", "focus on error handling"): Treat as implementation instruction and proceed automatically through all workflow steps
- **Default behavior**: When in doubt, proceed with implementation - the user invoked this command to implement, not just to view context

Treat any text provided after the command as extra implementation context (clarifications, recent discoveries, deployment constraints, etc.). The CLI will combine those notes with the stored plan.

## Interaction Guidelines

**Always ask when:**
- Multiple valid implementation approaches exist with different trade-offs
- Constitution has conflicting rules or ambiguous guidance
- Existing patterns don't fit the requirements well
- Breaking changes are necessary
- Test strategy is unclear
- User's additional notes are ambiguous

**Proceed without asking when:**
- Implementation matches existing patterns exactly
- Constitution provides explicit guidance
- Changes are purely additive
- Test patterns are obvious from similar code
- Plan.md clearly specifies the approach

**How to ask effectively:**
- Present 2-3 specific options with trade-offs
- Explain what you've found in codebase exploration
- Reference constitution rules that apply
- Suggest a recommendation with reasoning
- Show code examples when helpful

## Prerequisites

Before executing this command, ensure these prerequisites are met **in order**:

1. **Constitution Exists** (REQUIRED): The project must have a constitution at `oak/constitution.md`.
   - If missing, **STOP** and instruct the user: "Please run `/oak.constitution-create` first to establish your project's engineering standards."
   - The constitution is foundational - implementation must follow its standards.
   - **This is checked first** by the CLI before any other prerequisites.

2. **Plan Exists** (REQUIRED): The user must have already created a plan using `/oak.plan-create`.
   - If no plan exists, **STOP** and instruct: "Please run `/oak.plan-create` first to create a plan."

3. **Plan Name** (REQUIRED): You must know which plan to implement.
   - If the user hasn't provided one, infer from the current branch name (`plan/<name>` pattern)
   - If inferrable from branch, proceed directly
   - Otherwise ask: "Which plan should I implement?"

## Responsibilities

1. Confirm plan name (from arguments or current branch).
2. Load implementation context from plan artifacts (plan.md, summary.md if issue-based, research/ if research-based, validation.md if exists).
3. Explore the codebase to find patterns to follow.
4. Execute the implementation with tests.
5. Keep plan updated with any deviations or new findings.
6. Validate implementation meets definition of done.

## Task Execution Strategy

{% if has_background_agents %}
### Parallel Execution with Background Agents (DEFAULT)

**You MUST use parallel execution with background agents when the plan has 3+ independent tasks.**

Parallel execution is the DEFAULT mode for this agent. Only fall back to sequential execution when tasks have tight dependencies that prevent parallelization.

**REQUIRED for parallel execution (all must be true):**
- 3+ tasks with no shared dependencies
- Tasks modify different files/modules
- Clear separation of concerns (e.g., feature vs tests vs docs)

**Fall back to sequential ONLY when:**
- Tasks have hard dependencies on each other's output
- Multiple tasks modify the same files
- Complex integration requires step-by-step verification

**Orchestration Roles:**

| Agent Type | Responsibility | Best For |
|------------|----------------|----------|
| **Feature Agent** | Core implementation | Business logic, services, models |
| **Test Agent** | Test creation | Unit tests, integration tests |
| **Docs Agent** | Documentation | README updates, API docs, comments |
| **Refactor Agent** | Code cleanup | Restructuring, pattern alignment |

**Implementation Manifest (REQUIRED):**

You MUST create `oak/plan/<plan-name>/implementation-manifest.yml` BEFORE launching any background agents:

```yaml
version: 1.0
plan_name: "<plan-name>"
execution_mode: "parallel"  # or "sequential"
started_at: "<timestamp>"

task_assignments:
  - task_id: "T1"
    agent_type: "feature"
    status: "in_progress"  # pending, in_progress, completed, failed
    files_modified: []
    started_at: "<timestamp>"

  - task_id: "T2"
    agent_type: "test"
    status: "pending"
    depends_on: ["T1"]
    files_modified: []
```

{% else %}
### Sequential Execution

Execute tasks one at a time in dependency order. This ensures:
- Earlier work informs later implementation
- No file conflicts between tasks
- Easier debugging if issues arise
{% endif %}

{% if has_native_web %}
### Web Research During Implementation

When encountering unfamiliar APIs or patterns during implementation:
- Search for official documentation and examples
- Look for common implementation patterns
- Check for known issues or gotchas
- Find recent best practices (2024-2025)
{% endif %}

{% if has_mcp %}
### MCP Tool Integration

Leverage available MCP tools during implementation:
- **Code quality tools**: Linters, formatters, type checkers
- **Testing tools**: Test runners, coverage analyzers
- **Documentation tools**: Doc generators, API spec validators
- **Search tools**: Code search, web fetch for docs
{% endif %}

**Understanding Plan Implementation:**

- This command implements a plan created with `/oak.plan-create`.
- For issue-based plans: Artifacts are under `oak/plan/{name}/issue/` (summary.md, plan.md, related items).
- For research-based plans: Artifacts are under `oak/plan/{name}/` (plan.md, research/, tasks.md).
- Review the plan sections to understand scope, goals, and context.
- The branch is named after the plan (`plan/<name>`), and all work should satisfy the plan's goals or acceptance criteria.

## Workflow

**IMPORTANT: Complete preparation steps 1-8 before implementation. Step 9 determines parallel vs sequential execution based on task analysis.**

1. **Check for Stale Context (For Issue-Based Plans)**

   If working with an issue-based plan and the issue was fetched more than 1 day ago, consider refreshing:

   ```bash
   oak plan refresh  # Refreshes current plan's issue data
   oak plan refresh <NAME>  # Refreshes specific plan
   ```

   This updates `summary.md` with latest data from the provider while preserving all your local work (plan.md, notes.md, etc.).

   **Refresh when:**
   - Issue description/requirements may have changed
   - New comments or acceptance criteria added
   - Multi-day implementation span
   - Team made updates you haven't seen

   **Skip refresh when:**
   - Just ran `plan issue` today
   - Working with research-based plan (no issue provider)
   - Confident issue hasn't changed
   - No network access to provider

2. **Prerequisite Check and CLI Execution**

   First, report what you're about to do and run the CLI command:

   ```text
   I'll implement plan {NAME} from plan.md.

   Running: oak plan implement [options]
   ```

   The CLI will output:
   ```text
   ✓ Plan exists: oak/plan/{name}/plan.md
   ✓ Context loaded (if issue-based): oak/plan/{name}/issue/summary.md
   Ready to implement!
   ```
   
   **After CLI runs:**
   - **If user provided arguments/instructions**: CONTINUE automatically to step 3 (they want you to implement)
   - **If user provided NO arguments**: Ask if they want you to proceed with full implementation or just review context
   - **Default**: When in doubt, continue - they invoked this command to implement, not just view context

3. **Review Plan Artifacts**

   Open and read the plan artifacts:

   **For Issue-Based Plans** (`oak/plan/{name}/issue/`):

   **`summary.md`** - Agent-friendly issue summary:
   - Clean, readable format optimized for LLM consumption
   - Type-specific fields extracted (test steps for Test Cases, repro steps for Bugs, etc.)
   - HTML cleaned from description
   - Simplified relation types
   - All issue details: title, description, acceptance criteria, tags, assignee, priority, effort
   - Related issues with clear relationship types
   - **Use this as your primary source** for all issue information

   **For Research-Based Plans** (`oak/plan/{name}/`):

   **`research/*.md`** - Research findings:
   - Topic-specific research results
   - Recommendations and trade-offs
   - Source references

   **`tasks.md`** - Generated tasks (if exists):
   - Structured task breakdown
   - Dependencies and priorities

   **`plan.md`** - Implementation plan (validated and ready):
   - Objectives and success criteria
   - Implementation approach and design
   - Task breakdown with specifics
   - Dependencies and risks
   - Definition of done
   - **This was improved by `/oak.issue-validate`** - tasks are clear and actionable

   **`notes.md`** (if exists) - Additional context:
   - Implementation notes from previous sessions
   - User-provided guidance or priorities

   **`validation.md`** (if exists) - Validation results:
   - Issues found and fixed during validation
   - Any skipped issues to be aware of
   - Quality checks performed

   **`issue/related/{id}/summary.md`** (if exists, for issue-based plans) - Related issues:
   - Parent items (stories, epics) for broader context
   - Child items (sub-tasks) if breaking down work
   - Dependencies or linked items

4. **Verify Branch and Read Constitution**

   **BEFORE making ANY code changes**, verify you're on the correct branch and read the constitution:

   ```bash
   # Check current branch
   git branch --show-current
   ```

   The branch name was saved during `issue plan` and is stored in the issue context.

   **If the CLI did not automatically checkout the branch (user provided explicit issue ID from different branch):**
   - Run `oak issue show <ISSUE_ID>` to see the saved branch name
   - Tell user: "You're on branch `<current>`, but the issue uses branch `<saved-branch>`. To implement this issue, I should be on its branch."

5. **Extract Constitution Rules**

   ```bash
   # Read relevant sections
   cat oak/constitution.md

   # Find applicable rules
   rg "MUST" oak/constitution.md
   rg "SHOULD" oak/constitution.md
   rg "testing" oak/constitution.md -i
   ```

   Identify and list out:
   - Code standards that apply to your changes (naming, structure, quality requirements)
   - Testing requirements (coverage, patterns, organization, test-first vs test-last)
   - Documentation requirements (inline comments, API docs, README updates)
   - Review/approval protocols

6. **Reasoning Checkpoints - STOP Before Writing Code**

   **DO NOT START IMPLEMENTATION until you confirm:**
   - [ ] Read the constitution and identified applicable rules
   - [ ] Explored 2-3 similar implementations in this codebase
   - [ ] Understood the testing patterns used here
   - [ ] Know where your code will live (which module/package/files)
   - [ ] Have a clear definition of done from plan.md
   - [ ] Understand edge cases and error handling requirements
   - [ ] Know what documentation needs updating

7. **Systematic Codebase Exploration (REQUIRED)**

   **Before implementing, explore the codebase to find patterns.**

   **Find Similar Implementations:**

   ```bash
   # Search for related functionality
   rg "keyword_from_issue" src/

   # Find similar classes/components
   rg "class.*Service" src/           # Example: If implementing a service
   rg "interface.*Provider" src/      # Example: If implementing an interface

   # Check recent changes to similar code
   git log -p --since="2 weeks ago" src/path/to/similar/
   ```

   **Identify Patterns to Follow:**
   - How do similar features handle errors? (exception handling, error types, error propagation)
   - What logging is used? (logger setup, log levels, message format)
   - How are inputs validated? (validation approach, models, custom validators)
   - How are types/contracts expressed? (type annotations, interfaces, contracts)
   - How are dependencies managed? (constructors, dependency injection, factories)

   **Understand Test Patterns:**
   ```bash
   # Find test files for similar features
   find tests/ -name "*similar_feature*"

   # Examine how similar code is tested
   rg "test.*similar_pattern" tests/

   # Check test setup and mocking approaches
   cat tests/test_similar_feature.*
   ```

   **Document Your Findings:**
   - Which files provide good examples?
   - What patterns will you reuse?
   - Where will tests go?
   - What test helpers/utilities are available?

8. **Parse Implementation Tasks**

   Extract tasks from `plan.md` in the **Tasks** or **Implementation Plan** section:

   ```bash
   # View task list
   cat oak/issue/<provider>/<issue>/plan.md | grep -A 50 "## Tasks"
   ```

   **Task organization** (common phases, adjust based on plan.md):
   - **Phase 1: Setup** - Dependencies, configuration, project structure
   - **Phase 2: Core Implementation** - Main functionality, business logic
   - **Phase 3: Testing** - Unit tests, integration tests (timing per constitution)
   - **Phase 4: Integration** - Connect with existing systems
   - **Phase 5: Polish** - Documentation, error handling, edge cases

   **Task format in plan.md:**
   ```markdown
   ## Tasks
   - [ ] Task 1: Setup dependencies and project structure
   - [ ] Task 2: Implement core service logic
   - [ ] Task 3: Add tests for service functionality
   - [ ] Task 4: Update documentation
   ```

   **Execution rules:**
   - Respect dependencies between tasks (setup before implementation, etc.)
   - Follow constitution's guidance on test-first vs test-after approach
   - Mark tasks complete in plan.md as you finish them
   - Execution mode (parallel vs sequential) is determined in Step 9

{% if has_background_agents %}
9. **DECISION GATE: Execution Mode Selection (REQUIRED)**

   **STOP and analyze tasks before proceeding. You MUST explicitly choose an execution mode.**

   **Analysis Steps:**
   1. List all tasks from plan.md
   2. Identify dependencies between tasks (which tasks require output from others?)
   3. Count tasks that can run independently (no dependencies on each other)
   4. Check if independent tasks modify different files

   **Decision Rule:**
   - **IF** 3+ tasks have no dependencies on each other **AND** they modify different files:
     → **USE PARALLEL EXECUTION** (proceed to Step 10a)
   - **OTHERWISE**:
     → **USE SEQUENTIAL EXECUTION** (proceed to Step 10e)

   **MANDATORY OUTPUT - Document your decision:**
   ```text
   ## Execution Mode Decision

   Total tasks: [X]
   Independent tasks (no dependencies): [Y]
   Tasks modifying same files: [list or "none"]

   **Decision: [PARALLEL / SEQUENTIAL]**
   **Reason:** [Brief explanation based on analysis above]
   ```

   **IF PARALLEL SELECTED:** Create the implementation manifest NOW before continuing:

   ```bash
   # Create manifest file
   cat > oak/plan/<plan-name>/implementation-manifest.yml << 'EOF'
   version: 1.0
   plan_name: "<plan-name>"
   execution_mode: "parallel"
   started_at: "<timestamp>"

   task_assignments:
     # Fill in based on your task analysis
   EOF
   ```

   **Verify manifest exists before proceeding to Step 10.**

10. **Execute Implementation with Progress Tracking**

   **NOW you can begin implementation based on your decision in Step 9.**

   **Parallel Execution Mode (Step 10a-10d):**

   **Step 10a: Group Tasks into Execution Waves**

   Based on your analysis in Step 9, group tasks into waves:

   ```text
   Wave 1 (parallel): T1, T2, T3  [no dependencies]
   Wave 2 (parallel): T4, T5      [depend on Wave 1]
   Wave 3 (sequential): T6        [depends on T4 + T5, needs integration]
   ```

   **Step 10b: Launch Background Agents**

   **HOW TO LAUNCH:** {{ background_agent_instructions }}

   For each task in the current wave, use this delegation prompt:

   ```markdown
   # Implementation Assignment: <Task Title>

   ## Context
   - **Plan:** oak/plan/<plan-name>/plan.md
   - **Constitution:** oak/constitution.md
   - **Branch:** <current-branch>

   ## Your Task

   **ID:** <Task ID>
   **Title:** <Task Title>
   **Type:** <feature|test|docs|refactor>

   **Description:**
   <Full task description from plan.md>

   **Acceptance Criteria:**
   - [ ] <Criterion 1>
   - [ ] <Criterion 2>

   **Files to Modify:**
   - <file-path-1>
   - <file-path-2>

   ## Patterns to Follow

   Reference these existing implementations:
   - <similar-file-1>: <why it's relevant>
   - <similar-file-2>: <pattern to copy>

   ## Constitution Requirements

   Apply these rules from constitution:
   - <Relevant rule 1>
   - <Relevant rule 2>

   ## Deliverables

   1. Implement the task following patterns above
   2. Write tests per constitution requirements
   3. Run linters and fix any issues
   4. Report: files modified, tests added, any blockers

   ## Constraints

   - Do NOT modify files outside your assignment
   - Do NOT commit changes (orchestrator handles this)
   - If blocked, report and wait for guidance
   ```

   **Step 10c: Monitor Progress**

   Track agent progress and update manifest:

   ```text
   Parallel Implementation Status:

   ┌─────────────────────────────────────────────────────┐
   │ Wave 1: Independent Tasks                           │
   ├─────────────────────────────────────────────────────┤
   │  🔄 Agent 1: T1 - Implement UserService.validate()  │
   │  🔄 Agent 2: T2 - Add unit tests for validation     │
   │  🔄 Agent 3: T3 - Update API documentation          │
   └─────────────────────────────────────────────────────┘

   Monitoring progress...
   ```

   **Step 10d: Consolidate Results**

   As each wave completes:
   1. Review modified files for conflicts
   2. Run full test suite to catch integration issues
   3. Merge changes and update manifest
   4. Proceed to next wave when all agents complete

   ```yaml
   # Update implementation-manifest.yml
   task_assignments:
     - task_id: "T1"
       status: "completed"
       files_modified:
         - src/services/user_service.py
         - tests/test_user_service.py
       completed_at: "<timestamp>"
   ```

{% else %}
9. **Execute Implementation with Progress Tracking**

{% endif %}
   **Sequential Execution Mode (Step 10e):**

   For each task in plan.md:

    **a) Report starting the task:**
    ```text
    Starting: Task 3 - Implement IssueService.validate_provider()
    ```

    **b) Execute the work:**
    - Follow patterns found in codebase exploration
    - Apply constitution rules
    - Write code and tests
    - Run local validation (linters, tests)

    **c) Mark task complete in plan.md:**
    ```markdown
    - [X] Task 3: Implement IssueService.validate_provider()
    ```

    **d) Report completion:**
    ```text
    ✓ Completed: Task 3 - Implement IssueService.validate_provider()
    Files modified: src/services/issue_service.py, tests/test_issue_service.py
    ```

    **e) Handle errors:**
    - If task fails: Stop and report error with context
    - Suggest next steps for user to resolve
    - Don't continue to dependent tasks

    **Implementation principles:**
    - **Match existing patterns**: File naming, class structure, function organization
    - **Apply constitution rules**: Follow all code standards defined in constitution
    - **Write tests per constitution**: Follow the project's test strategy (test-first or test-after)
    - **Keep plan.md updated**: Mark tasks [X] as you complete them

11. **Reasoning Checkpoints - While Implementing**

   Continuously verify:
   - [ ] Am I following patterns I found in the codebase?
   - [ ] Am I adhering to constitution standards?
   - [ ] Am I writing tests per constitution guidance?
   - [ ] Are my type annotations/contracts complete (if applicable)?
   - [ ] Is my code documentation clear and helpful?
   - [ ] Am I handling errors appropriately?
   - [ ] Am I updating docs as needed?

12. **Completion Validation**

   After implementing all tasks, verify the work is complete:

    **a) Check all tasks completed:**
    ```bash
    # Count completed vs total tasks
    grep -c "\- \[X\]" oak/issue/<provider>/<issue>/plan.md
    grep -c "\- \[ \]" oak/issue/<provider>/<issue>/plan.md
    ```

    Display task summary:
    ```text
    ## Task Completion
    ✓ Completed: 8/8 tasks
    - [X] Setup dependencies
    - [X] Create tests
    - [X] Implement core logic
    - [X] Add error handling
    - [X] Write documentation
    - [X] Update constitution references
    - [X] Run linters
    - [X] Verify all acceptance criteria
    ```

    **b) Verify acceptance criteria met:**
    - Read acceptance criteria from `context-summary.md`
    - For each criterion, verify it's addressed in the implementation
    - Document how each criterion is satisfied

    **c) Run tests:**
    ```bash
    # Run test suite using project's test framework
    # Examples (check constitution for actual commands):
    # - Python: pytest tests/
    # - .NET: dotnet test
    # - Node: npm test
    # - Java: mvn test
    ```

    Report test results:
    ```text
    ## Test Results
    ✓ All tests passing (X tests, 0 failures)
    ✓ Coverage: X% (meets constitution requirements)
    ```

    **d) Verify constitution compliance:**
    ```bash
    # Run code quality tools specified in constitution
    # Examples (check constitution for actual commands):
    # - Linters (ruff, eslint, dotnet format --verify-no-changes, etc.)
    # - Type checkers (mypy, tsc, etc.)
    # - Formatters (black, prettier, dotnet format, etc.)
    ```

    **e) Check git status:**
    ```bash
    git status
    git diff --stat
    ```

    Ensure:
    - No unintended files modified
    - No secrets or sensitive data
    - Changes are on the correct branch

13. **Stop and Report**

   After implementation is complete, provide comprehensive summary:

    ```text
    ## Implementation Complete

    **Issue**: {provider} #{id} - {title}
    **Branch**: {branch_name}
    **Commits**: {count} commits

    ### Tasks Completed
    - ✓ 8/8 tasks complete (100%)
    - See plan.md for full task list

    ### Acceptance Criteria
    - ✓ All 4 criteria satisfied
    - Details documented in implementation

    ### Tests
    - ✓ X tests passing
    - ✓ Coverage: X%
    - New test files: [list files]

    ### Constitution Compliance
    - ✓ All MUST rules followed
    - ✓ Code quality standards met
    - ✓ Documentation added
    - ✓ Best practices applied

    ### Files Modified
    - [list modified files]

    ### Next Steps
    1. Review changes: git diff
    2. Validate implementation: /oak.issue-validate
    3. Create pull request when ready
    ```

    **Command ends here**. User should review implementation before validation.

## Notes

- **CLI is scaffolding only**: Commands are deterministic utilities for loading context and checking out branches. All reasoning about implementation, patterns, and testing is your responsibility.
- **You drive the implementation**: Use your full toolset to read files, search code, run tests, and make changes. The CLI just sets up the workspace.
- **Constitution is authoritative**: Always follow the rules in `oak/constitution.md`. Read it thoroughly before starting implementation. The constitution defines all code standards, testing approaches, and quality requirements for the project.
- **Follow project test strategy**: Test timing (test-first vs test-after), coverage requirements, and test organization are defined in the constitution. Don't assume TDD or any specific approach - follow what the project uses.
- **Patterns over invention**: Reuse existing patterns found in the codebase. Only deviate when absolutely necessary and document why.
- **Keep artifacts updated**: Update plan.md with implementation notes, deviations, and learnings as you go.
- **Missing artifacts**: If the CLI reports missing context or plan files, run `/oak.issue-plan` first to create them.
- **Stack-agnostic**: This template works across languages and frameworks. The constitution provides stack-specific guidance (Python, C#, Java, Node, etc.).
