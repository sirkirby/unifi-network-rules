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
