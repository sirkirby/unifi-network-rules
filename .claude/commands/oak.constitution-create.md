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

## CLI Help & Command Discovery

When you need to discover available CLI commands or their options:

```bash
oak --help                          # List all OAK commands
oak constitution --help             # List constitution subcommands
oak constitution create --help      # Get help for specific command
oak constitution analyze --help     # Get help for analyze command
```

**Key commands for this workflow:**
- `oak constitution analyze --json` - Analyze project, get classification
- `oak constitution create --json` - **PRIMARY COMMAND** - Creates constitution AND agent files automatically
- `oak constitution validate --json` - Validate constitution (optional, included in create)
## Flow Control (High-Reasoning Mode)

**Operate autonomously.** Maintain conversation momentum without unnecessary pauses.

**Only pause when:**
- User input is genuinely ambiguous
- A critical decision requires explicit approval (marked with CHECKPOINT)
- The workflow is complete

**Never ask:** "Ready to continue?" / "Should I proceed?" / "Would you like me to..."

Just continue. Users will interrupt if needed.
## Workflow Overview

**Your job: Gather decisions through reasoning. The CLI handles everything else.**

1. **Analyze** - Run `oak constitution analyze --json`
2. **Confirm** - Verify classification with user, gather metadata
3. **Research** - Investigate technologies and patterns (use web if available)
4. **Assess** - Determine which decisions are relevant for this project type
5. **Decide** - Gather user decisions on RELEVANT areas only
6. **Generate** - Run `oak constitution create --json` (creates constitution + agent files + validates)
7. **Report** - Deliver summary and next steps

Focus your effort on reasoning and decision gathering. The CLI handles file creation, agent files, and validation automatically.
---

## Project Analysis (Before Any Questions)

**Run the OAK CLI to analyze the project before asking the user anything:**

```bash
oak constitution analyze --json
```

This single command performs comprehensive project analysis:
- Detects test infrastructure (tests/, spec/, __tests__, etc.)
- Detects CI/CD workflows (GitHub Actions, GitLab CI, Azure Pipelines, etc.)
- Detects agent instruction files WITH content analysis (filters out OAK-only content)
- Detects project type files (package.json, pyproject.toml, *.csproj, etc.)
- Detects application code directories (src/, lib/, app/, etc.)
- **Automatically excludes OAK-installed files** (.oak/, oak.* commands)
- Returns a `classification` field: `greenfield`, `brownfield-minimal`, or `brownfield-mature`

**Classification Criteria (handled by the CLI):**
- **Greenfield**: No tests, no CI workflows, no team-created agent instructions -> Full consultation needed
- **Brownfield-Minimal**: Some application code, minimal patterns -> Ask about aspirations vs reality
- **Brownfield-Mature**: Tests, CI workflows, existing team conventions -> Extract and validate existing standards

**Key distinction**: A project with ONLY `.oak/` and `oak.*` files is still **Greenfield** - OAK tooling is not project convention.

## Interactive Project Intake

1. Parse `$ARGUMENTS` and extract any project metadata already supplied.

2. **Present the CLI analysis results and ASK USER TO CONFIRM classification:**

   ```text
   I've analyzed your project:

   Project artifacts found:
   - Test directories: [from test_infrastructure.directories or "None found"]
   - CI/CD workflows: [from ci_cd.workflows or "None found"]
   - Team agent instructions: [from agent_instructions.files where oak_only=false, or "None found"]
   - Application code: [from application_code.directories or "None found"]
   - Project files: [from project_files.files]

   Classification: [from classification field - GREENFIELD/BROWNFIELD-MINIMAL/BROWNFIELD-MATURE]

   Is this classification correct? (yes / no / unsure)
   ```

3. **Wait for user confirmation before proceeding.** If user says "no" or "unsure", ask them to describe their project's current state.

4. Ask for missing essentials (only what you still need):
   - Project name
   - Author name (for attribution)
   - Tech stack (primary technologies/languages) - use `project_files` from analysis as hints
   - One-sentence project description

5. **For Brownfield projects ONLY**, summarize what you found:
   ```text
   Existing conventions detected:
   - [Summary of patterns found in agent instructions]
   - [CI/CD checks from ci_cd.workflows]
   - [Test patterns from test_infrastructure.directories]

   I'll incorporate these into the constitution and ask about gaps.
   ```

6. Confirm the collected data back to the user and note any ambiguities or assumptions.
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

## Research Phase (Capability-Aware)

**Before presenting decision options, conduct research on technologies and patterns mentioned by the user.**

This step ensures the constitution reflects current best practices rather than outdated or generic patterns.

### Research Trigger Detection

Scan user input (project description, tech stack, $ARGUMENTS) for research-worthy topics.

**Reference:** `features/constitution/templates/decision_points.yaml` section `research_triggers` contains comprehensive regex patterns for:
- Language/runtime versions (Python, TypeScript, Node, Java, Go, Rust, C#, .NET)
- Frameworks (FastAPI, Django, Next.js, Spring Boot, ASP.NET Core, etc.)
- CLI frameworks (Ink, Commander, Click/Typer, Cobra)
- Architecture patterns (vertical slice, hexagonal, clean, DDD, CQRS, microservices)
- Testing frameworks (pytest, Jest, Vitest, Playwright, xUnit, NUnit)
- Industry/compliance (fintech, healthcare, GDPR)

Use your judgment to identify which triggers are relevant for this project.


### Web Search Available

You have built-in web search capabilities. For each research topic:

1. Search for current best practices: "[technology] best practices 2025"
2. Synthesize findings into 3-5 actionable patterns per topic
3. Present findings to user BEFORE relevant decision points
4. Document sources for traceability


### Research Presentation

Present research findings BEFORE each relevant decision point:

```text
RESEARCH FINDINGS: [Topic]

Based on current best practices:

1. **[Pattern Name]**: [Description, when to use]
2. **[Pattern Name]**: [Description, when to use]
3. **[Pattern Name]**: [Description, when to use]

How this affects your decisions:
- Testing: [implication]
- Architecture: [implication]
```
---

## Synthesis

Compile your findings into a working outline before generating content:
- Create a table mapping evidence -> source -> constitution section -> proposed requirement
- Note which areas need clarification or additional assumptions
- Highlight any legacy-agent guidance you plan to reconcile or supersede
- Review with the user; pause if major decisions require approval

---

## Pre-Decision Relevance Assessment

**Before presenting any decision options, assess which decisions are RELEVANT to this project type.**

The decision framework is comprehensive, but NOT all decisions apply to all projects.

### Project Type Classification

| Project Type | Example Tech | Relevant Decisions | Skip or Adapt |
|--------------|--------------|-------------------|---------------|
| **Web Application** | React, Next.js, Django, FastAPI | All 5 decisions | None |
| **Backend Service/API** | FastAPI, Express, Spring Boot | All 5 decisions | None |
| **CLI Tool** | Click, Typer, Commander | Testing, Review, Docs, CI/CD | Architecture may not apply |
| **Automation/Scripts** | GitHub Actions, Bash, Make | Testing (adapted), Review, Docs, CI/CD | Architecture typically N/A |
| **Infrastructure/IaC** | Terraform, Pulumi | Testing (adapted), Review, Docs | Standard architecture N/A |
| **Library/Package** | PyPI, npm package | All decisions | Architecture may be simpler |
| **Data Pipeline** | Airflow, Dagster, dbt | Testing, Review, Docs, CI/CD | Architecture adapted |

### Decision Applicability Rules

**For Automation/Scripts repos:**
- **Testing**: ASK, but adapt to "workflow testing," "smoke tests," "dry-run validation"
- **Architecture**: SKIP - traditional patterns don't apply

**For CLI tools:**
- **Architecture**: Offer "Pragmatic/Adaptive" or "Custom" - don't push enterprise patterns

**For Infrastructure/IaC:**
- **Testing**: Adapt to "plan validation," "policy-as-code testing"
- **Architecture**: SKIP - IaC has its own patterns (modules, environments, workspaces)

### How to Handle Non-Applicable Decisions

**DO NOT:** Present all options and let user say "doesn't apply"
**DO:** Skip the decision and note it, or adapt the question to the project context

### Assessment Template

Before presenting decisions, determine:

```text
Project Type: [Web App / CLI / Automation / Infrastructure / etc.]

Decision Applicability:
- Testing: [RELEVANT / ADAPT to: _____]
- Code Review: [RELEVANT - always]
- Documentation: [RELEVANT - always]
- CI/CD: [RELEVANT / N/A - reason]
- Architecture: [RELEVANT / SKIP - reason / ADAPT to: _____]
```

**Proceed to gather ONLY the relevant decisions.**
---

## Interactive Decision Gathering

**Gather explicit user decisions on RELEVANT areas. Never assume defaults.**

**Reference:** `features/constitution/templates/decision_points.yaml` contains the complete decision framework with:
- All options for each category with characteristics and "best for" guidance
- Follow-up questions triggered by specific choices
- Presentation templates

Use the YAML as your source of truth for options and follow-ups. Apply your judgment to:
- Skip or adapt decisions based on project type (per relevance assessment)
- Present options conversationally rather than as rigid menus
- Probe deeper when user responses are ambiguous

### Decision Categories

1. **Testing Strategy** - testing_strategy section
2. **Code Review Policy** - code_review section
3. **Documentation Level** - documentation section
4. **CI/CD Enforcement** - ci_cd section
5. **Architecture** (if applicable) - architectural_patterns section

### Decision Summary Checkpoint

After gathering all relevant decisions, present a summary:

```text
CONSTITUTION DECISION SUMMARY

Project Type: [type]

Testing: [option] - [key details]
Code Review: [option] - [key details]
Documentation: [option] - [key details]
CI/CD: [option] - [key details]
Architecture: [option or N/A] - [key details]

CHECKPOINT: Do these decisions accurately reflect your project needs?
- "yes" -> Proceed
- "no" -> Cancel
- "revise [topic]" -> Modify specific decision
```

Wait for user confirmation before generating the constitution.
---

## Generate Constitution with Combo Command

**Use the combo command that handles EVERYTHING automatically:**

1. **Create a decision context JSON file** with all gathered decisions:

   ```bash
   cat > /tmp/decisions.json <<'EOF'
   {
     "testing_strategy": "balanced",
     "coverage_target": 70,
     "coverage_strict": false,
     "has_e2e_infrastructure": false,
     "e2e_planned": true,
     "critical_integration_points": ["authentication", "payment processing"],
     "tdd_required": false,
     "testing_rationale": "Balanced approach for production application",
     "code_review_policy": "standard",
     "num_reviewers": 1,
     "hotfix_definition": "Production-critical bugs affecting users",
     "documentation_level": "standard",
     "adr_required": true,
     "docstring_style": "google",
     "ci_enforcement": "standard",
     "required_checks": ["tests", "linting", "coverage"],
     "ci_platform": "GitHub Actions"
   }
   EOF
   ```

   **Replace values with actual user decisions.**

2. **Run the combo command**:
   ```bash
   oak constitution create \
     --project-name "{PROJECT_NAME}" \
     --author "{AUTHOR}" \
     --tech-stack "{TECH_STACK}" \
     --description "{PROJECT_DESCRIPTION}" \
     --context-file /tmp/decisions.json \
     --json
   ```

   **This single command:**
   - Creates the constitution file
   - Generates/updates ALL agent instruction files
   - Runs validation automatically
   - Returns a JSON summary

3. **Parse the JSON output** to confirm success:
   - `constitution_path`: Where the constitution was created
   - `agent_files`: Which agent files were created/updated
   - `validation`: Whether validation passed
   - `errors`: Any issues encountered

**Note:** If you use `create-file` instead of `create`, you MUST manually run `update-agent-files`.
---

## Completion

### Quality Review

Review the generated constitution for:
- Accuracy: Conditional sections match user decisions
- Customization: Incorporate brownfield-specific conventions if needed
- Quality: Normative language used appropriately (MUST, SHOULD, MAY)

### Final Report

Provide a structured summary:
- Constitution location and status
- Agent files created/updated
- Outstanding issues or recommendations
- Suggested next steps (team review, commit, amendments process)

### Verification Checklist

Before ending, verify:
- [ ] Project analyzed with `oak constitution analyze --json`
- [ ] User confirmed classification
- [ ] Relevant decisions gathered (not all decisions apply to all projects)
- [ ] Decision summary approved by user
- [ ] Combo command `oak constitution create --json` executed
- [ ] Final report delivered
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