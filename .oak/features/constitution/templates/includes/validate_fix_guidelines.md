## Guidelines for Fixing

### Empty Sections
**Generate based on codebase analysis:**
- Scan for relevant files and patterns
- Create realistic, enforceable requirements
- Use declarative language (MUST, SHALL)
- Include rationale for each requirement

### Non-declarative Language
**Replacement strategy:**
- "should" -> "MUST" (for requirements) or "SHOULD" (for recommendations)
- "could" -> "MAY" (for options) or remove if not a requirement
- "might" -> Rephrase to be definitive
- "maybe" -> Remove or make specific

### Date Formats
**Always use ISO 8601:**
- Convert MM/DD/YYYY -> YYYY-MM-DD
- Convert DD/MM/YYYY -> YYYY-MM-DD

### Template Tokens
**Replace with actual values:**
- `{{PROJECT_NAME}}` -> Get from config or repo name
- `{{TECH_STACK}}` -> Get from codebase analysis
- `{{AUTHOR}}` -> Get from git config or ask user
- Never leave tokens unreplaced

## Important Notes

- **Interactive mode is default** - Always ask before applying fixes
- **Explain changes** - Tell user what was changed and why
- **Preserve content** - Never delete sections, only add or modify
- **Use CLI tools** - Don't manually parse/write files, use CLI commands
- **Validate after fixes** - Always re-run validation to confirm
