---
description: Review implementation artifacts for a plan and surface gaps.
handoffs:
  - label: Generate Tasks
    agent: oak.plan-tasks
    prompt: Generate implementation tasks from the validated plan.
  - label: Implement Plan
    agent: oak.plan-implement
    prompt: Implement the plan and its associated tasks.
---

## User Input

```text
$ARGUMENTS
```

Interpret the input as a request to validate a specific plan. The plan name can be provided explicitly or inferred from the current git branch. Ask for clarification if the plan name is ambiguous.

## Operating Constraints

**READ-ONLY ANALYSIS**: This command performs non-destructive analysis across plan artifacts (summary.md, plan.md, implementation). Do not modify any files during the analysis phase. Output a structured analysis report with findings.

**REMEDIATION IS OPTIONAL**: After analysis, offer to help fix issues interactively. User must explicitly approve before entering the fixing phase. Each fix requires individual user confirmation before being applied.

**Constitution Authority**: The project constitution (`oak/constitution.md`) is non-negotiable. Constitution conflicts are automatically CRITICAL and require adjustment of the plan or implementation—not dilution or reinterpretation of the principle.

## Prerequisites

Before executing this command, ensure these prerequisites are met **in order**:

1. **Constitution Exists** (REQUIRED): The project must have a constitution at `oak/constitution.md`.
   - If missing, **STOP** and instruct the user: "Please run `/oak.constitution-create` first to establish your project's engineering standards."
   - The constitution is foundational - validation checks compliance against it.
   - **This is checked first** by the CLI before any other prerequisites.

2. **Plan Exists** (REQUIRED): The user must have already created a plan using `/oak.plan-create`.
   - If no plan exists, **STOP** and instruct: "Please run `/oak.plan-create` first to create a plan before validating."

3. **Plan Name** (REQUIRED): You must know which plan to validate.
   - If the user hasn't provided one, check the current branch - plan branches follow the pattern `plan/<name>`
   - If inferrable from branch, proceed directly
   - Otherwise ask: "Which plan should I validate?"

## Mission

**Your job is to ensure we have the best possible plan given all available context:**

- **Issue details** - requirements, acceptance criteria, constraints from ADO/GitHub
- **Codebase context** - existing patterns, architecture, related code (explore using grep/find/read)
- **Constitution standards** - MUST/SHOULD rules, team conventions, quality bars
- **Implementation readiness** - tests, documentation, edge cases, risk mitigations

**Then use your intelligence to walk the user through prioritized fixes:**

1. **HIGH priority** (🔴 CRITICAL) - Plan is unimplementable without these fixes
2. **MEDIUM priority** (🟡 IMPORTANT) - Plan works but has gaps that will cause issues
3. **LOW priority** (🟢 MINOR) - Nice-to-have improvements for quality

**For each finding, provide options** the user can choose from to improve the plan. Your goal: help them achieve an implementation-ready, high-quality plan that sets them up for success.

## Responsibilities

1. Confirm plan name (from arguments or current branch).
2. Run validation to check artifacts, plan completeness, and constitution compliance.
3. Perform comprehensive content quality analysis (clarity, ambiguity, underspecification).
4. Verify all acceptance criteria are met and mapped to tasks (for issue-based plans).
5. Check code implementation against plan (if code exists).
6. Present findings with severity levels and multiple fix options.
7. Guide user through interactive improvements with their approval.

## Validation Strategy

{% if has_background_agents %}
### Parallel Validation with Background Agents (DEFAULT)

**You MUST use parallel validation with background agents when validating plans with code implementation.**

Parallel validation is the DEFAULT mode for this agent. All validation checks listed below are independent and MUST run in parallel:

**Parallelizable Validation Checks:**

| Check Type | Agent Focus | Independence |
|------------|-------------|--------------|
| **Artifact Validation** | Plan completeness, structure | Independent |
| **Code Quality** | Linting, formatting, types | Independent |
| **Test Execution** | Run test suite, coverage | Independent |
| **Constitution Compliance** | MUST/SHOULD rules | Independent |
| **Documentation** | README, API docs | Independent |

**Parallel Validation Workflow:**

```text
┌─────────────────────────────────────────────────────────┐
│ Validation Orchestrator                                  │
├─────────────────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐│
│  │ Artifact │  │   Code   │  │   Test   │  │  Const.  ││
│  │  Check   │  │  Quality │  │  Runner  │  │ Checker  ││
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘│
│       │              │             │             │      │
│       └──────────────┴─────────────┴─────────────┘      │
│                         │                               │
│              Consolidate Findings                       │
└─────────────────────────────────────────────────────────┘
```

#### Launching Background Agents

**HOW TO LAUNCH:** {{ background_agent_instructions }}

For each check, use this delegation prompt:

```markdown
# Validation Assignment: <Check Type>

## Context
- **Plan:** oak/plan/<plan-name>/plan.md
- **Constitution:** oak/constitution.md
- **Branch:** <current-branch>

## Your Validation Focus

**Check Type:** <artifact|code_quality|tests|constitution|docs>

**Scope:**
<Specific areas to validate>

## Validation Criteria

Apply these checks:
1. <Check 1>
2. <Check 2>
3. <Check 3>

## Output Format

Return findings as:
```yaml
findings:
  - id: "<check>-1"
    severity: "critical|important|minor"
    category: "<category>"
    location: "<file:line>"
    issue: "<description>"
    recommendation: "<fix>"
```

## Constraints

- READ-ONLY: Do not modify any files
- Report ALL findings, let orchestrator prioritize
```

**DECISION GATE: Before starting validation, you MUST:**

1. Confirm plan has code implementation to validate (if not, skip Code Quality and Test checks)
2. Create a validation manifest at `oak/plan/<plan-name>/validation-manifest.yml`
3. Launch all applicable checks in parallel
4. Monitor and consolidate findings

**MANDATORY OUTPUT before launching agents:**
```text
## Validation Mode Decision

Plan has code implementation: [Yes/No]
Checks to run in parallel: [list applicable checks]
Creating validation manifest...
Launching background agents...
```

{% else %}
### Sequential Validation (Fallback)

Perform validation checks one at a time when background agents are not available.
{% endif %}

{% if has_native_web %}
### Web-Assisted Validation

When validating external integrations or API usage:
- Verify API endpoints and documentation are current
- Check for deprecated patterns or security advisories
- Validate configuration against latest best practices
{% endif %}

{% if has_mcp %}
### MCP-Powered Validation

Leverage available MCP tools for automated checks:
- **Linting**: Run project linters via MCP tools
- **Type checking**: Execute type checkers (mypy, tsc)
- **Security scanning**: Run security analysis tools
- **Coverage**: Generate coverage reports
{% endif %}

**Understanding Plan Validation:**

- This command validates a plan created with `/oak.plan-create`.
- For issue-based plans: Artifacts are under `oak/plan/{name}/issue/` (summary.md, plan.md).
- For research-based plans: Artifacts are under `oak/plan/{name}/` (plan.md, research/, tasks.md).
- Related items (for issue-based plans) in `related/{id}/summary.md` provide context but are not directly validated.
- Validation checks that the plan's goals or acceptance criteria are met and the plan is complete.

## Workflow

1. **Prerequisite Check**
   - Check `$ARGUMENTS` for explicit issue ID (only needed if validating a different issue than current branch).
   - **Issue Auto-Detection**: If already on an issue's branch, **just run the command** without arguments:
     - The CLI automatically infers from the current branch name
     - Just use: `oak issue validate` (no ID needed!)
     - The CLI will display which issue it detected
   - **When to confirm with user**:
     - ✅ **Proceed directly** if current branch name clearly matches an issue (e.g., `123456-*`)
     - ❌ **Ask for confirmation** only if the branch name is ambiguous or doesn't follow issue patterns
   - **Example - When branch is clear**:
     - Current branch: `123456-new-azure-keyvault-workflow`
     - Agent response: "Running validation for ADO issue #123456..." (then execute immediately)
     - Don't ask: "Should I run validation for #123456?" (the branch makes it obvious!)
   - **If unable to detect issue from current branch**:
     - Current branch doesn't follow issue patterns (e.g., `main`, `feature/refactor`, etc.)
     - Agent should ask: "I couldn't detect an issue from branch `<current-branch>`. You can either:"
       - **Option 1**: "Tell me the issue ID and I'll validate it explicitly (e.g., 'validate ADO 123456')"
       - **Option 2**: "Checkout the issue's branch first, then ask me again and I'll auto-detect it"
     - If user chooses Option 2, show: `git checkout <branch-name>` or `oak issue show <ISSUE_ID>` to find the branch
   - If no plan exists for this issue, **instruct the user**: "No plan found for this issue. Please run `/oak.issue-plan <ISSUE_ID>` first."
   - **Optional**: Run `oak constitution check` to verify the constitution exists before attempting validation.

2. **Execute CLI Validation**
   - Run `oak plan validate` via the shell (plan auto-detected from branch).
   - **Or** explicitly specify: `oak plan validate <NAME>`
   - The CLI will check:
     - Prerequisites (constitution exists)
     - Artifacts exist (plan.md, and for issue-based: `summary.md`)
     - Plan sections are complete (no PENDING placeholders)
     - Acceptance criteria are captured (for issue-based plans)
     - Implementation branch exists
     - Basic constitution rule coverage in plan
   - **The CLI creates initial** `oak/plan/<name>/validation.md` with raw validation results
     - This is just the starting point - you will enhance it with your analysis and fixes

3. **Verify Branch**

   After running `oak issue validate`, **verify you're on the correct branch before reviewing changes**:

   ```bash
   # Check current branch
   git branch --show-current
   ```

   The branch name was saved during `issue plan` and is stored in the issue context. The validate command uses this branch for checking implementation status.

   **If current branch doesn't match the issue's branch:**
   - Run `oak issue show <ISSUE_ID>` to see the saved branch name
   - Tell user: "You're on branch `<current>`, but the issue uses branch `<saved-branch>`. I can validate the artifacts, but to review the code changes I should be on the issue's branch."
   - **Ask user**: "Would you like me to checkout the issue's branch (`<saved-branch>`) now?"
     - **Option A (default)**: Proceed with validation on current branch (artifact checks only, limited code review)
     - **Option B**: Checkout the issue's branch first (enables full code review with `git diff`)
   - If user chooses Option B, run: `git checkout <saved-branch>` then continue with full validation

4. **Discover Artifacts**
   - Run `oak issue show <ISSUE_ID>` to see all artifact paths and related items
   - Use `--json` flag if you need to parse the output programmatically
   - The show command reveals:
     - Artifact paths (context-summary.md, plan.md, validation.md)
     - The saved branch name for this issue
     - Related issues with their context paths
     - Issue directory structure

5. **Understand the Artifacts**

   **`oak/issue/<provider>/<issue>/context-summary.md`**
   - Focus issue details from the provider in agent-friendly format
   - Acceptance criteria that must be met
   - Issue metadata (state, priority, assigned user, effort)
   - Type-specific fields (test steps for Test Cases, repro steps for Bugs)

   **`oak/issue/<provider>/<issue>/related/{id}/context-summary.md`** (if applicable)
   - Context for parent issues (epics, stories above the focus)
   - Context for child issues (tasks, sub-tasks below the focus)
   - Context for other related items (dependencies, links)
   - Used to understand scope and relationships but not validated directly

   **`oak/issue/<provider>/<issue>/plan.md`**
   - Implementation plan with approach, tasks, risks
   - Should reference related items for context
   - Validated for completeness (no PENDING sections)

   **`oak/constitution.md`** - Project constitution
   - Always read this file directly for project standards
   - Contains architecture patterns, code standards, testing requirements
   - Used during validation to check plan compliance with MUST/SHOULD rules

6. **Review Validation Output**

   Review the generated files to understand what was planned:

   **`oak/issue/<provider>/<issue>/context-summary.md`**
   - Original issue from provider in agent-friendly format
   - Acceptance criteria that must be satisfied
   - Labels, priority, status, effort, type-specific fields

   **`oak/issue/<provider>/<issue>/plan.md`**
   - Implementation approach taken
   - Task breakdown
   - Testing strategy
   - Definition of done

7. **Comprehensive Validation Checklist**

   Go beyond the CLI's basic checks. Validate thoroughly:

   **Artifact Completeness:**
   - [ ] `context-summary.md` has all issue details
   - [ ] `plan.md` has no PENDING sections
   - [ ] All acceptance criteria have clear verification steps
   - [ ] Testing strategy is defined in plan
   - [ ] Definition of done is specific and measurable

   **Code Quality - Pattern Adherence:**
   ```bash
   # Find the files that changed
   git diff --name-only main...HEAD

   # Check each changed file
   # - Does it follow existing file naming conventions?
   # - Does it match the structure of similar files?
   # - Are imports organized consistently?
   ```
   - [ ] New code follows patterns found in codebase
   - [ ] File and class naming matches project conventions
   - [ ] Import organization follows project style
   - [ ] Error handling matches established patterns

   **Code Quality - Standards Compliance:**
   - [ ] Type hints on all new functions and methods
   - [ ] Docstrings match project style (Google/NumPy/etc.)
   - [ ] Function/variable names are descriptive
   - [ ] Error messages are clear and actionable
   - [ ] Constants used instead of magic strings/numbers
   - [ ] No commented-out code or debug prints

   **Testing - Existence:**
   ```bash
   # Find test files for changed code
   git diff --name-only main...HEAD | grep "^src/"
   # For each, check corresponding test file exists

   # Check test coverage
   pytest tests/ -v
   # Or project-specific test command
   ```
   - [ ] Tests exist for new functionality
   - [ ] Test files follow naming convention (test_*.py or *_test.py)
   - [ ] Tests are in correct location (unit/ vs integration/ vs project structure)

   **Testing - Quality:**
   - [ ] Test names clearly describe what they test
   - [ ] Tests cover happy path
   - [ ] Tests cover error cases
   - [ ] Tests use appropriate fixtures/mocks
   - [ ] Tests are independent (can run in any order)
   - [ ] All tests passing

   **Documentation:**
   ```bash
   # Check if user-facing changes exist
   git diff main...HEAD -- src/

   # Check what docs might need updates
   ls README.md CHANGELOG.md docs/
   ```
   - [ ] README updated if user-facing changes exist
   - [ ] Inline comments added for complex logic
   - [ ] CHANGELOG entry added (if project requires)
   - [ ] API docs updated (if applicable)

   **Constitution Compliance:**
   ```bash
   # Read the constitution
   cat oak/constitution.md

   # Check for must-follow rules
   rg "MUST" oak/constitution.md
   rg "SHOULD" oak/constitution.md
   ```
   - [ ] All MUST rules are satisfied
   - [ ] All SHOULD rules are followed (or deviation documented)
   - [ ] Code standards followed (check linters if project uses them)
   - [ ] Testing requirements met (coverage, organization)
   - [ ] Documentation requirements satisfied

   **Git Hygiene:**
   ```bash
   # Check branch name
   git branch --show-current

   # Check commit messages
   git log --oneline main..HEAD

   # Check what's staged/unstaged
   git status
   ```
   - [ ] Branch named correctly (matches issue pattern)
   - [ ] Commits are atomic (one logical change each)
   - [ ] Commit messages are clear and descriptive
   - [ ] No unintended files included (check .gitignore)
   - [ ] No merge conflicts
   - [ ] Branch is up to date with base branch (if required)

8. **Cross-Reference Implementation with Plan**

   Open `plan.md` and verify:
   - [ ] All tasks marked complete are actually implemented
   - [ ] All acceptance criteria have corresponding code/tests
   - [ ] Approach described in plan matches actual implementation
   - [ ] Any deviations from plan are documented

9. **Analyze Plan Content Quality (READ-ONLY)**

   **🚫 DO NOT MODIFY ANY FILES during this phase.**

   **The CLI output from Step 2 provides structural checks** (missing files, PENDING sections, branch exists). That's just basic verification.

   **Your job is deeper analysis** - reason about plan quality, clarity, and implementability.

   **Read plan.md carefully and check for:**

   **a) Task Structure & Organization**
   
   **Check if plan uses structured 5-phase task breakdown:**
   - **Phase 1: Setup & Investigation** - Dependencies, affected modules, branch setup
   - **Phase 2: Core Implementation** - Acceptance criteria mapped to implementation tasks
   - **Phase 3: Testing** - Constitution-driven test tasks, issue test cases
   - **Phase 4: Integration** - Child issue support, system integration
   - **Phase 5: Polish & Documentation** - Docs, quality checks, constitution compliance
   
   **Validate task quality:**
   - Are tasks specific with file paths and function/class names?
   - Example GOOD: "Implement AC1: User validation in src/services/auth_service.py:validate_user()"
   - Example BAD: "Add user validation"
   - Do tasks reference patterns found in codebase exploration?
   - Are phase dependencies respected? (Setup before Implementation, Tests per constitution timing)

   **b) Acceptance Criteria Mapping (Phase 2)**

   **Critical check - every AC must have implementation task(s):**
   ```bash
   # Read acceptance criteria from context-summary.md
   cat oak/issue/<provider>/<issue>/context-summary.md | grep -A 20 "Acceptance Criteria"

   # Check Phase 2 tasks in plan.md
   cat oak/issue/<provider>/<issue>/plan.md | grep -A 50 "Phase 2"
   ```

   **For each acceptance criterion from context-summary.md:**
   - [ ] Has at least one Phase 2 implementation task referencing it
   - [ ] Task specifies which files/functions implement it
   - [ ] Task references patterns from codebase exploration
   
   **Common issues:**
   - 🔴 CRITICAL: AC has no corresponding implementation task
   - 🟡 IMPORTANT: AC mapped to vague task ("implement feature" without specifics)
   - 🟢 MINOR: Task could reference AC number more clearly

   **c) Test Strategy Validation (Phase 3)**
   
   **Constitution-driven testing check:**
   ```bash
   # Extract test strategy from plan.md
   cat oak/issue/<provider>/<issue>/plan.md | grep -A 30 "Test Strategy"

   # Check constitution test requirements
   cat oak/constitution.md | grep -i "test\|TDD\|coverage"
   ```
   
   **Validate test strategy section exists and documents:**
   - [ ] Constitution test requirements (TDD vs test-after, coverage %, required/optional)
   - [ ] Test timing extracted from constitution
   - [ ] Issue test cases counted and planned
   - [ ] Unit/integration test requirements per constitution
   - [ ] Expected coverage aligned with constitution
   
   **Validate Phase 3 tasks follow constitution:**
   - If constitution requires TDD: Phase 3 should come before Phase 2 in plan
   - If constitution requires high coverage: All test scenarios should be explicit tasks
   - If constitution is flexible: Tests marked as optional but still encouraged
   - **Always**: Issue test cases should be converted to test tasks
   
   **Check test case conversion:**
   ```bash
   # Count test cases from issue
   cat oak/issue/<provider>/<issue>/context-summary.md | grep -c "Test Steps"

   # Count test tasks in Phase 3
   cat oak/issue/<provider>/<issue>/plan.md | grep -A 50 "Phase 3" | grep -c "Test:"
   ```

   **Common issues:**
   - 🔴 CRITICAL: No Test Strategy section when constitution requires testing
   - 🔴 CRITICAL: Test phase order wrong (Phase 3 before Phase 2 when constitution requires TDD)
   - 🟡 IMPORTANT: Issue test cases not converted to tasks
   - 🟡 IMPORTANT: Test tasks don't specify test file paths or function names
   - 🟡 IMPORTANT: Constitution test requirements not extracted or documented
   - 🟢 MINOR: Could add more edge case tests beyond constitution requirements

   **d) Parent/Child Context Utilization**

   **Check if related issues were leveraged:**
   ```bash
   # Check for related items
   ls oak/issue/<provider>/<issue>/related/

   # Check if plan references them
   cat oak/issue/<provider>/<issue>/plan.md | grep -i "parent\|child\|related"
   ```

   **If parent issues exist:**
   - [ ] Phase 1 includes task to review parent context
   - [ ] Plan references parent goals/objectives
   - [ ] Implementation aligns with parent's broader scope

   **If child issues exist:**
   - [ ] Phase 4 includes integration tasks for child items
   - [ ] Plan considers downstream impacts
   - [ ] Implementation supports child item requirements

   **Common issues:**
   - 🟡 IMPORTANT: Parent issues exist but not referenced in plan
   - 🟡 IMPORTANT: Child issues exist but no integration tasks in Phase 4
   - 🟢 MINOR: Could add more context from related items

   **e) Task Specificity & Actionability**
   
   **Every task should answer: WHERE, WHAT, HOW, WHY**
   - **WHERE**: Specific file paths (src/services/issue_service.py:L150)
   - **WHAT**: Specific functions/classes (IssueService.validate_provider())
   - **HOW**: Pattern reference (following Repository pattern from constitution)
   - **WHY**: Links to acceptance criteria or constitution requirement
   
   **Check for vague terms without specifics:**
   - 🔴 CRITICAL: "refactor", "improve", "enhance" without details
   - 🟡 IMPORTANT: "add tests" without test file names or scenarios
   - 🟡 IMPORTANT: "update service" without specifying which service/methods
   
   **Common issues:**
   - Missing WHERE: "Add validation" → Which file? Which function?
   - Missing WHAT: "Update database" → Which tables? What changes?
   - Missing HOW: "Integrate with API" → Which SDK? Auth method?
   - Missing WHY: "Change logic" → Which AC does this satisfy?

   **f) Constitution Compliance Documentation**
   
   **Check Constitution Compliance section in plan.md:**
   ```bash
   cat oak/issue/<provider>/<issue>/plan.md | grep -A 30 "Constitution Compliance"
   ```
   
   **Should document:**
   - [ ] Test Strategy extracted from constitution (timing, coverage, organization)
   - [ ] MUST rules identified and addressed
   - [ ] SHOULD rules identified and considered
   - [ ] Any violations with justification
   
   **Common issues:**
   - 🔴 CRITICAL: Constitution Compliance section missing when required
   - 🔴 CRITICAL: Test strategy not extracted from constitution
   - 🟡 IMPORTANT: MUST rules not explicitly addressed in tasks
   - 🟡 IMPORTANT: Test requirements don't match constitution guidance

   **g) Clarity & Actionability (General)**
   - Are objectives specific and measurable? (Not: "improve performance", But: "reduce API latency from 500ms to <100ms")
   - Are tasks clear enough to implement? Can someone execute them without asking questions?
   - Are acceptance criteria testable? (Not: "works well", But: "all tests pass", "coverage >85%")
   - Is the approach understandable? Does it explain *how* not just *what*?

   **h) Ambiguity Detection**
   - Check for vague terms: "refactor", "improve", "enhance", "optimize", "clean up", "fix issues"
   - Flag incomplete references: "update the service" (which service? which methods?)
   - Identify missing details: "add tests" (what kind? unit/integration? which scenarios?)
   - Look for assumptions: "should be straightforward", "probably won't take long"

   **i) Completeness**
   - Are all dependencies identified? (packages, services, external APIs)
   - Are edge cases considered? (error handling, boundary conditions, null/empty inputs)
   - Is there enough context for implementation? (existing patterns, related code, file locations)
   - Are risks and mitigations documented for all HIGH/CRITICAL risks?
   - Is rollback/recovery addressed for risky changes?

   **j) Cognitive Complexity**
   - Is the plan trying to do too much at once? (Should it be split into phases?)
   - Are there circular dependencies in tasks? (Task A needs Task B, Task B needs Task A)
   - Is scope creep evident? (Tasks not related to acceptance criteria)
   - Are there too many unknowns/NEEDS CLARIFICATION items unresolved?

10. **Build Structured Analysis Report (READ-ONLY)**

   **🚫 DO NOT MODIFY ANY FILES during this phase.**

   Now combine all findings into a structured report.

   **Sources of findings:**
   1. **CLI output** (from Step 2) - structural issues: missing files, PENDING sections, branch status
   2. **Your content analysis** (from Step 9) - quality issues: clarity, ambiguity, underspecification
   3. **Code review** (from Steps 4-8) - implementation issues: constitution violations, test coverage, patterns
   4. **Git hygiene** (from Step 7) - version control issues: branch naming, commit quality

   **Severity Assignment:**
   - **🔴 CRITICAL**:
     - Violates constitution MUST rule
     - Missing core acceptance criteria mapping
     - Test phase order wrong (TDD required but tests after implementation)
     - Issue test cases not converted to tasks
     - No Test Strategy when constitution requires testing
     - Broken functionality or security issues
     - Plan is unimplementable without clarification
   - **🟡 IMPORTANT**:
     - Missing documentation
     - Incomplete constitution SHOULD rule
     - Pattern violations
     - Poor test coverage
     - Missing type hints
     - Ambiguous tasks without file paths/function names
     - Underspecified approach
     - Parent/child issues not leveraged
     - Constitution test requirements not extracted
     - Missing edge cases
   - **🟢 MINOR**:
     - Naming improvements
     - Additional edge case tests beyond requirements
     - Comment clarity
     - Style preferences
     - Could add more detail but implementable as-is

   **For each finding, document:**
   - **ID**: Unique identifier (e.g., `C1`, `I1`, `M1` for Critical/Important/Minor)
   - **Category**: Task Structure, AC Mapping, Test Strategy, Parent/Child Context, Task Specificity, Constitution, Coverage, Testing, Documentation, Clarity, Completeness, Ambiguity, Underspecification
   - **Severity**: 🔴 CRITICAL / 🟡 IMPORTANT / 🟢 MINOR
   - **Location**: File path and line numbers (e.g., `plan.md "Phase 2" section`, `plan.md "Test Strategy"`, `src/services/issue_service.py:L150-160`)
   - **Issue**: Clear description of what's wrong
   - **Root Cause**: Why this happened (not just symptoms)
   - **Recommendation**: Specific fix with effort estimate
   - **Options** (if multiple approaches): 2-3 concrete alternatives with pros/cons

   **Output Analysis Report:**

   Present findings to the user in this format:

   ```markdown
   ## Validation Analysis Report

   **Issue**: {provider} #{id}
   **Validated**: {timestamp}
   **Branch**: {branch_name}

   ### Summary
   - Total Findings: {count}
   - 🔴 Critical: {count}
   - 🟡 Important: {count}
   - 🟢 Minor: {count}

   ### Task Structure Analysis
   - Phase 1 (Setup): {count} tasks
   - Phase 2 (Implementation): {count} tasks
   - Phase 3 (Testing): {count} tasks
   - Phase 4 (Integration): {count} tasks
   - Phase 5 (Polish): {count} tasks
   - Task specificity: {good/needs improvement}

   ### Acceptance Criteria Mapping
   - Total ACs: {count}
   - ACs with implementation tasks: {count}/{total} ({percentage}%)
   - Unmapped ACs: {list if any}

   ### Test Strategy Analysis
   - Constitution requirements: {TDD/test-after, coverage %, required/optional}
   - Test Strategy section: {present/missing}
   - Issue test cases: {count} ({count converted to tasks})
   - Phase order: {correct/needs adjustment for TDD}

   ### Parent/Child Context
   - Parent issues: {count} ({referenced/not referenced})
   - Child issues: {count} ({integration planned/missing})
   
   ### Findings
   
   | ID | Category | Severity | Location | Issue | Recommendation |
   |----|----------|----------|----------|-------|----------------|
   | C1 | AC Mapping | 🔴 CRITICAL | plan.md Phase 2 | AC3 "All data encrypted" has no implementation task | Add task: "Implement encryption for sensitive fields in UserService.save() using AES-256" (45 min) |
   | C2 | Test Strategy | 🔴 CRITICAL | plan.md | No Test Strategy section, constitution requires 80% coverage | Add Test Strategy section documenting constitution requirements and test approach (15 min) |
   | I1 | Test Strategy | 🟡 IMPORTANT | plan.md Phase 3 | Issue has 5 test cases but only 2 converted to tasks | Convert remaining 3 test cases to Phase 3 test tasks with test file paths (20 min) |
   | I2 | Task Specificity | 🟡 IMPORTANT | plan.md Phase 2, Task 3 | Task "Add validation" is too vague | Specify: "Add email format validation to UserService.validate_email() using regex per constitution" (10 min) |
   | I3 | Parent/Child Context | 🟡 IMPORTANT | plan.md Phase 1 | Parent story #12345 exists but not reviewed | Add Phase 1 task: "Review parent story context from related/12345/context-summary.md" (5 min) |
   | M1 | Style | 🟢 MINOR | plan.md Phase 3 | Could add edge case tests beyond requirements | Optional: Add test for null input handling (15 min) |
   
   ### Constitution Alignment
   - ✅ Code structure follows project patterns
   - ❌ Test Strategy not extracted from constitution (CRITICAL)
   - ❌ Constitution requires TDD but plan has tests in Phase 3 after implementation (CRITICAL)
   - ✅ MUST rules addressed
   - ⚠️ 2 SHOULD rules need consideration
   
   ### Coverage Analysis
   - Acceptance criteria with tasks: 3/4 (75%) - AC3 missing
   - Tasks with test tasks: 4/7 (57%)
   - Issue test cases converted: 2/5 (40%)
   - Parent/child context used: 0/2 (0%)
   ```

   **Limit findings to 50 items**. If more than 50, summarize overflow: "Plus 12 additional minor issues (see validation.md for full list)"

10. **Provide Next Actions with Context**

    Based on findings severity, guide the user on what to do next:
    
    **If CRITICAL issues exist (🔴):**
    ```
    ⚠️  Found {count} critical issues that make this plan unimplementable.

    These must be fixed to proceed:
    - {brief description of critical issues}

    I can help you fix these interactively with multiple options for each fix.
    Would you like to work through them now? (yes/no)

    Or you can:
    - Fix them manually using the recommendations above
    - Re-run validation after fixes: /oak.issue-validate
    - Once cleared, proceed to implementation: /oak.issue-implement
    ```
    
    **If only IMPORTANT issues (🟡):**
    ```
    ✅ No critical blockers! Plan is implementable.
    
    However, found {count} important issues that could cause problems during implementation:
    - {brief description of important issues}
    
    You have options:
    
    Option A: Fix them now (recommended for quality)
    - I can help you interactively with multiple solutions per issue
    - Estimated time: {X minutes based on recommendations}
    - Benefit: Smoother implementation, fewer surprises
    
    Option B: Proceed and address during implementation
    - Risk: May need to pause coding to clarify these issues
    - When stuck, return here: /oak.issue-validate
    
    Option C: Mix approach
    - Fix HIGH importance issues now
    - Address others during implementation
    
    What would you prefer?
    ```
    
    **If only MINOR issues (🟢):**
    ```
    ✅ Plan is solid and ready to implement!
    
    Found {count} minor suggestions for polish:
    - {brief description of minor issues}
    
    These are optional - plan will work fine without them.
    
    You can:
    1. Address minor issues for extra polish (I can help interactively)
    2. Skip and implement now: /oak.issue-implement
    3. Come back to these during code review
    
    What sounds best?
    ```
    
    **If validation passes completely:**
    ```
    ✅ Excellent! This plan is implementation-ready.
    
    Summary:
    - All acceptance criteria mapped to tasks ✓
    - Constitution alignment verified ✓
    - Implementation context complete ✓
    - Risks identified with mitigations ✓
    - No ambiguity or underspecification detected ✓
    
    Ready to implement: /oak.issue-implement
    ```

11. **Offer Interactive Remediation**

    After presenting the analysis report:
    
    **Ask the user explicitly:**
    
    ```
    I found {count} issues ({critical} critical, {important} important, {minor} minor).
    
    Would you like me to help fix these issues interactively?
    
    If yes, I'll work through them one at a time and ask for your approval before making each change.
    If no, you can address them manually using the recommendations above.
    ```
    
    **⏸️ WAIT FOR USER RESPONSE**
    
    - If **NO** or user doesn't respond: Stop here. Analysis is complete.
    - If **YES**: Proceed to Section 12 (Interactive Fixing)

12. **Interactive Fixing Loop** (Only if User Approved)

   **This section only runs if the user explicitly said "yes" to interactive remediation.**

   Work through issues one at a time, starting with CRITICAL, then IMPORTANT, then MINOR:

   **For each issue:**

   a) **Present the issue with context:**
      ```
      🔴 Issue {ID}: {Brief description}
      
      **Problem**: {What's wrong}
      **Location**: {File path and line numbers}
      **Why it matters**: {Impact explanation}
      **Current state**: {Show the problematic code/content}
      ```

   b) **Propose specific fix with options:**

      **Always present multiple options when possible** (at least 2-3 for IMPORTANT/CRITICAL issues):

      **For AC mapping issues** (acceptance criteria without implementation tasks):
      ```text
      I can fix this in a few ways:
      
      Option A: Add specific implementation task mapped to AC
      - Add to Phase 2 in plan.md:
        "- [ ] Implement AC3: All data encrypted at rest
           - File: src/services/user_service.py:save_user()
           - Encrypt sensitive fields (email, phone) using AES-256
           - Use encryption_utils.encrypt() from constitution pattern
           - Store encryption keys in Azure KeyVault per security guidelines"
      - Pros: Very specific, clear implementation path, directly traceable to AC
      - Cons: Prescriptive about encryption method
      
      Option B: Add implementation task with research phase
      - Add to Phase 2:
        "- [ ] Research encryption approach for AC3 (5 min)
           - Review constitution security requirements
           - Check existing encryption patterns via code search (rg/grep)
           - Document encryption method choice in plan
         - [ ] Implement AC3: Encrypt sensitive data per research findings (30 min)
           - File: src/services/user_service.py"
      - Pros: Ensures we pick right approach for context
      - Cons: Adds research overhead
      
      Option C: Reference existing pattern
      - Add to Phase 2:
        "- [ ] Implement AC3: Encrypt sensitive user data
           - Follow encryption pattern in src/services/payment_service.py
           - Apply to email, phone fields in UserService.save_user()
           - Use same KeyVault configuration"
      - Pros: Consistent with existing code
      - Cons: Assumes payment service pattern is appropriate
      
      Which level of detail works for this AC?
      ```

      **For test strategy issues** (missing constitution test requirements):
      ```text
      I can fix the missing Test Strategy section:

      Option A: Extract full test strategy from constitution
      - Add Test Strategy section to plan.md:
        "**Test Strategy (from constitution):**
         - **Timing**: Test-after allowed (constitution does not require TDD)
         - **Coverage**: 80% minimum required for new code
         - **Required**: Unit tests for all public methods
         - **Optional**: Integration tests recommended for critical workflows
         - **Organization**: Tests mirror src/ structure in tests/
         - **Issue test cases**: 5 test cases to convert to tasks

         **Test Tasks (Phase 3):**
         - [ ] Test: User validation rejects invalid email (from issue test case 1)
           - Test file: tests/test_user_service.py:test_validate_email_invalid()
         - [ ] Test: User validation accepts valid email (from issue test case 2)
           - Test file: tests/test_user_service.py:test_validate_email_valid()
         [+ 3 more from issue test cases]
         - [ ] Test: Unit tests for UserService.save_user() (per constitution)
         - [ ] Test: Edge case - null email input"
      - Pros: Complete test strategy, all issue test cases converted
      - Cons: Detailed, takes time to write

      Option B: Document requirements, detail during implementation
      - Add Test Strategy section:
        "Constitution requires 80% coverage, test-after approach acceptable.
         5 test cases from issue must be implemented.
         Unit tests required for all public methods."
      - Add Phase 3 tasks:
        "- [ ] Convert 5 issue test cases to unit tests (60 min)
         - [ ] Add unit tests for new UserService methods (45 min)
         - [ ] Achieve 80% coverage minimum (verify with pytest --cov)"
      - Pros: Documents requirements without overspecifying
      - Cons: Developer needs to determine exact test structure
      
      Option C: Add constitution check task to Phase 1
      - Add to Phase 1:
        "- [ ] Review constitution test requirements (10 min)
           - Extract test strategy (TDD vs test-after, coverage %)
           - Document findings in Test Strategy section
           - Plan test tasks based on constitution + issue test cases"
      - Pros: Ensures planning continues properly
      - Cons: Defers test planning, might miss in rush

      Which approach ensures best test coverage?
      ```

      **For content clarity issues** (ambiguous tasks, underspecified criteria):
      ```text
      I can fix this in a few ways:

      Option A: Add specific technical details with file paths
      - Update plan.md task from "Refactor validation" to:
        "- [ ] Extract IssueProvider.validate() to ValidationService class
           - File: src/services/validation_service.py (new file)
           - Move _validate_issue() and _validate_against_constitution()
           - Follow Repository pattern from constitution
           - Update tests: tests/test_validation_service.py
           - Reference: Similar extraction in src/services/template_service.py"
      - Pros: Very specific, clear what to implement, includes pattern reference
      - Cons: More prescriptive, less room for implementation choices
      
      Option B: Add clarifying questions for user to answer
      - Add NEEDS CLARIFICATION section to plan.md:
        "CLARIFY: Validation refactor scope
         - Which validation methods should move?
         - Should we keep backward compatibility?
         - What's the target class structure?"
      - Then pause and ask user to clarify before implementing
      - Pros: Ensures we understand intent before committing
      - Cons: Requires another round of planning
      
      Option C: Add guided investigation steps
      - Update task to: "Review existing validation patterns via code search (rg/grep),
        identify duplication in _validate_* methods, propose consolidation
        approach following Repository pattern from constitution"
      - Pros: Encourages research phase, discovers actual needs
      - Cons: Implementation takes longer
      
      Which approach fits best for your team's workflow?
      ```

      **For constitution violations** (missing tests, type hints, docstrings):
      ```text
      I can address the missing tests in these ways:
      
      Option A: Add comprehensive test suite now
      - Add tests/test_issue_service.py covering:
        * test_validate_provider_with_valid_config()
        * test_validate_provider_with_missing_config()
        * test_validate_provider_with_invalid_credentials()
      - Update plan.md task: "Write unit tests for validate_provider (30 min)"
      - Pros: Tests planned upfront, clear coverage
      - Cons: Might discover we need integration tests too
      
      Option B: Document test requirements, implement during coding
      - Add to plan.md "Testing" section:
        "Unit tests required per constitution:
         - All public methods in IssueService
         - Error cases for invalid provider configs
         - Edge cases for branch name generation
         Target: 85% coverage minimum"
      - Pros: Documents requirement without overspecifying
      - Cons: Developer needs to determine exact test cases
      
      Option C: Defer to implementation phase with test-first approach
      - Add to plan.md: "Follow TDD: write failing test for each method
        before implementation. Start with test_validate_provider()."
      - Pros: Ensures we understand behavior before coding
      - Cons: Might slow down if requirements aren't clear
      
      Which testing approach do you prefer?
      ```

      **For underspecification** (missing details, unclear approach):
      ```text
      I can make this more specific:
      
      Option A: Add detailed implementation steps
      - Expand "Integrate with Azure KeyVault" task to:
        1. Install Azure.Security.KeyVault.Secrets SDK
        2. Add DefaultAzureCredential authentication
        3. Create KeyVaultService wrapper class
        4. Implement get_secret() with retry logic (3 attempts, exponential backoff)
        5. Add error handling for SecretNotFound, AuthenticationFailed
        6. Update tests with mock KeyVault responses
      - Pros: Very clear, easy to implement
      - Cons: Assumes specific SDK and patterns
      
      Option B: Reference existing patterns in codebase
      - Update task to: "Integrate Azure KeyVault following the pattern
        in src/services/azure_storage_service.py (credential setup,
        error handling, retry logic). Use KeyVault.Secrets SDK."
      - Pros: Consistent with existing code
      - Cons: Requires reading reference code first
      
      Option C: Add decision log and research task
      - Add "Research Azure KeyVault integration options" task:
        * Compare Azure.Security.KeyVault vs Azure.KeyVault.Keys SDKs
        * Review authentication methods (DefaultAzureCredential vs ManagedIdentity)
        * Document decision in plan.md with rationale
      - Then: "Implement KeyVault integration per decision log"
      - Pros: Ensures we pick right approach for our context
      - Cons: Adds research overhead
      
      Which level of detail works for this project?
      ```

      **If only one obvious fix** (style issues, simple additions):
      - Still explain what you'll do and why
      - Ask: "Should I proceed with this fix?"
      - Example: "I'll add the missing docstring using Google style format per constitution. Proceed?"

   c) **⏸️ WAIT FOR USER APPROVAL**
      - Do not apply ANY changes until user explicitly approves
      - User must say "yes", "proceed", "option A", etc.
      - If user says "no" or "skip": Move to next issue without fixing
      - If user suggests alternative: Discuss and incorporate their feedback

   d) **Apply the approved fix:**
      - **Update `plan.md`** - This is the source of truth for `/oak.issue-implement`
        - Add missing sections, clarify approaches, document decisions
        - Ensure all constitution rules are addressed
        - Fill in any PENDING placeholders
      - Confirm what you did: "✓ Updated plan.md: Added testing strategy section per constitution requirement"

   e) **Verify the fix:**
      - Re-read the modified files
      - Confirm the issue is resolved
      - Show user the result: "✓ Verified: Testing section now includes unit, integration, and E2E test plans"

   f) **Move to next issue:**
      - "Issue {ID} complete. Moving to next issue..."
      - Repeat steps a-f for each remaining issue

   **After all fixes (or skips):**
   ```
   Summary of changes:
   - Fixed: {count} issues
   - Skipped: {count} issues
   - Files modified: {list}
   
   Would you like to re-run validation to confirm everything passes?
   ```
   
   **⏸️ WAIT FOR USER CONFIRMATION** before re-running validation

   **Example Interactive Flow:**

   ```text
   Agent: 
   "## Validation Analysis Report
   
   I found 6 issues (1 critical, 3 important, 2 minor).
   
   | ID | Category | Severity | Issue | Recommendation |
   |----|----------|----------|-------|----------------|
   | C1 | Clarity | 🔴 CRITICAL | Task "Refactor validation logic" is too vague | Specify which methods, what pattern, why needed |
   | I1 | Underspecification | � IMPORTANT | "Add tests" doesn't specify what kind | Clarify: unit vs integration, scenarios, coverage target |
   | I2 | Ambiguity | 🟡 IMPORTANT | "Integrate with Azure KeyVault" missing implementation details | Add SDK choice, auth method, error handling approach |
   | I3 | Constitution | 🟡 IMPORTANT | Missing type hints on 3 new functions in plan | Add type hints task to implementation section |
   | M1 | Style | 🟢 MINOR | Variable naming could be clearer | Rename `res` to `result` in service methods |
   | M2 | Documentation | 🟢 MINOR | Could add more context about why this approach | Optional: expand rationale section |
   
   Would you like me to help fix these issues interactively?"
   
   User: "yes"
   
   Agent:
   "Great! Let's work through them one at a time, starting with critical issues.

   🔴 Issue C1: Task "Refactor validation logic" is too vague

   **Problem**: plan.md has task "Refactor validation logic" without specifics
   **Location**: plan.md "Implementation Tasks" section, item 3
   **Why it matters**: Too ambiguous to implement - which validation? what's wrong? what pattern?
   **Current state**: "- [ ] Refactor validation logic"

   I can fix this in a few ways:

   Option A: Add specific technical details based on codebase exploration
   - Replace with: "Extract IssueProvider.validate() to ValidationService class
     following Repository pattern. Move _validate_issue(), _validate_against_constitution()
     helpers to new service. Update tests in test_issue_service.py accordingly."
   - Pros: Very specific, clear implementation path
   - Cons: Prescriptive, less flexibility during implementation
   
   Option B: Add clarifying questions for you to answer first
   - Replace with: "Refactor validation logic (NEEDS CLARIFICATION:
     Which validation methods? Should we extract to separate service or keep in provider?
     What's driving this refactor - code reuse, testability, or separation of concerns?)"
   - Then pause plan until you clarify
   - Pros: Ensures we understand your intent
   - Cons: Requires another planning round
   
   Option C: Make it investigation-driven
   - Replace with: "Review validation patterns via code search, identify duplication in
     _validate_* methods, propose consolidation following constitution patterns, then
     implement extraction to ValidationService if warranted"
   - Pros: Discovers actual needs through investigation
   - Cons: Implementation takes longer, might not need refactor
   
   Which approach fits your workflow? Or would you like a different direction?"
   
   User: "option A, but make it less prescriptive - just say extract to service class"

   Agent: [updates plan.md]
   "✓ Updated plan.md task to: 'Extract validation logic to ValidationService class
   following Repository pattern from constitution. Move _validate_issue() and
   _validate_against_constitution() helpers. Update corresponding tests.'

   ✓ Verified: Task is now specific but leaves implementation details flexible
   
   Issue C1 complete. Moving to next issue...
   
   🟡 Issue I1: Plan doesn't address constitution utilities rule

   **Problem**: Constitution requires shared utilities in functions/ directory
   **Location**: oak/issue/ado/169029/plan.md - Implementation Approach section
   **Why it matters**: Constitution compliance is mandatory for implementation
   
   **Current plan mentions** creating keyvault_helper.py but doesn't specify location.
   
   I can fix this in a few ways:
   
   Option A: Add to plan.md: 'New KeyVault helpers will go in functions/utils/keyvault_helper.py'
   - Pros: New dedicated file, clear separation
   - Cons: Adds another file to maintain
   
   Option B: Add to plan.md: 'KeyVault helpers will be added to existing functions/auth_utils.py'
   - Pros: Leverages existing auth utilities, keeps related code together
   - Cons: Makes auth_utils.py larger
   
   Which would you prefer?"
   
   User: "B"
   
   Agent: [updates plan.md]
   "✓ Updated plan.md - Implementation Approach section
   ✓ Added: 'KeyVault helper functions will be added to existing functions/auth_utils.py
            to maintain centralized utility pattern per constitution guidelines.'
   ✓ Verified: Plan now addresses constitution utilities requirement
   
   Issue I1 complete. Moving to next issue...
   
   (continues for remaining issues...)
   
   ---
   
   Summary of changes:
   - Fixed: 5 issues
   - Files modified: plan.md

   Would you like to re-run validation to confirm everything passes?"
   ```

   **Key Principles:**
   - **Wait for approval**: Never apply changes without explicit user confirmation
   - **One issue at a time**: Focus, fix, confirm, move on
   - **Show actual content**: Display real code/text, not descriptions
   - **Offer choices**: Present 2-3 concrete options when multiple approaches exist
   - **Confirm results**: Always verify and report what was changed
   - **Ask before proceeding**: Don't assume user wants to continue

13. **Update validation.md with Analysis Report**

    **After analysis** (Section 9), save the structured analysis report to `oak/issue/<provider>/<issue>/validation.md`:

    ```markdown
    # Validation Analysis Report

    **Issue**: {provider} #{id}
    **Validated**: {timestamp}
    **Branch**: {branch_name}

    ## Summary
    - Total Findings: {count}
    - 🔴 Critical: {count}
    - 🟡 Important: {count}
    - 🟢 Minor: {count}

    ## Findings

    | ID | Category | Severity | Location | Issue | Recommendation |
    |----|----------|----------|----------|-------|----------------|
    [findings table from analysis]

    ## Constitution Alignment
    [constitution check results]

    ## Coverage Analysis
    [coverage statistics]

    ## Next Actions
    [recommendations from Section 10]
    ```
    
    **After each fix** (if user opted in to Section 12), append to validation.md:
    
    ```markdown
    ---
    
    ## Interactive Remediation Session
    
    ### Issue {ID}: {Brief description}
    **Priority:** 🔴 Critical / 🟡 Important / 🟢 Minor
    **Status:** Fixed / Skipped
    **Root Cause:** [Why it happened]
    **Fix Applied:** [What you changed]
    **Files Modified:**
    - `path/to/file.py` - [what changed]
    **Verified:** ✓ [How you confirmed the fix works]
    **User Decision:** [What user chose - Option A, skipped, etc.]
    
    [Repeat for each issue addressed]
    
    ---
    
    ## Final Summary
    **Issues Fixed:** X
    **Issues Skipped:** X
    **Files Modified:** [list]
    **Outcome:** ✅ Ready for implementation / ⚠ Issues remain
    **Next Steps:** [recommendations]
    **Session Completed:** {timestamp}
    ```
    
    This creates a **complete narrative** of the validation and remediation work.

14. **Completion**

    Once validation is complete (with or without fixes):

    - Ensure validation.md is saved with complete analysis
    - Provide clear next steps based on findings
    - If critical issues remain: Block implementation until resolved
    - If validation passes: Clear path to `/oak.issue-implement`

## Operating Principles

### Analysis Phase (Always Required)

- **READ-ONLY**: Do not modify any files during analysis (Sections 1-10)
- **Comprehensive validation**: CLI checks basics, you check code quality, tests, patterns, documentation
- **Structured output**: Produce findings table with severity, location, recommendations
- **Progressive disclosure**: Load minimal context needed, don't dump entire files
- **Token efficiency**: Limit findings to 50 items, summarize overflow
- **Constitution is authority**: Constitution violations are always CRITICAL

### Remediation Phase (Opt-In Only)

- **User approval required**: Never start fixing without explicit user consent (Section 11)
- **Each fix needs approval**: Present issue → Propose fix → Wait for approval → Apply fix
- **One at a time**: Focus on single issue, fix it completely, verify, move to next
- **Show actual content**: Display real code/text that will change, not placeholders
- **Offer options**: When multiple approaches exist, present 2-3 concrete choices
- **Document everything**: Update validation.md after each fix with details
- **Confirm results**: Always verify fix worked and show user the result

### Quality Standards

- **Constitution compliance**: All validation against `oak/constitution.md` rules
- **Testing is mandatory**: Code without tests is CRITICAL issue
- **Pattern adherence**: New code must match existing codebase patterns
- **Actionable findings**: Every issue has specific fix with effort estimate
- **Prioritize impact**: Focus on issues that matter, not trivial style preferences
- **No assumptions**: If problems exist, they must be addressed or explicitly deferred
