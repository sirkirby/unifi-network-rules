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
