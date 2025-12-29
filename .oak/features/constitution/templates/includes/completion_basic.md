## Review Generated Constitution

**The template handles most content based on your decisions!**

Review the generated constitution for:

1. **Accuracy Check**: Verify that conditional sections match user decisions:
   - Testing strategy sections reflect chosen approach
   - Coverage requirements match specified target
   - Code review policy matches selected option
   - Documentation level is appropriate
   - CI/CD enforcement is correct

2. **Customization** (only if needed):
   - Add project-specific architectural patterns discovered during analysis
   - Incorporate brownfield-specific conventions from existing agent instructions
   - Add any domain-specific requirements (e.g., security, compliance)
   - Refine rationale statements to be project-specific

3. **Quality Check**:
   - Ensure normative language is used appropriately (MUST, SHOULD, MAY)
   - Verify at least two actionable statements per section
   - Confirm rationale is provided for non-obvious requirements

**Key Principle**: The constitution should now be ~80% ready based on user decisions. You're refining, not rewriting.

## Verify Agent Files

**If you used `oak constitution create`, agent files were generated automatically!**

The combo command output includes an `agent_files` section showing:
- `updated`: Existing files that had constitution reference added
- `created`: New agent files created
- `skipped`: Files that already had constitution references

### Manual Verification (Optional)

```bash
oak constitution list-agent-files --json
```

### If You Used `create-file` Instead of `create`

**You MUST run agent file generation manually:**
```bash
oak constitution update-agent-files
```

Agent instruction files are what enable AI assistants to discover and follow the constitution. Without them, the constitution exists but agents won't know about it.

## Final Report

Provide a structured summary:
- Constitution location, version, status, and notable highlights
- Section-by-section synopsis referencing evidence
- Agent instruction file updates (including backups)
- Quality scores, outstanding issues, and recommended follow-up actions
- Reminder about validation status and suggested next steps (team review, commit to VCS, schedule amendments process)

## Completion Checklist

**Before ending the session, verify these are complete:**

| Step | Status | Requirement |
|------|--------|-------------|
| Project Analysis | [ ] | `oak constitution analyze --json` was run |
| Classification Confirmed | [ ] | User confirmed greenfield/brownfield classification |
| Relevance Assessment | [ ] | Determined which decisions apply to this project type |
| Decisions Gathered | [ ] | All RELEVANT decisions collected from user |
| Decision Summary Approved | [ ] | User said "yes" to the decision summary |
| **Combo Command Run** | [ ] | `oak constitution create --json` was run with decisions |
| Final Report Delivered | [ ] | Summary with next steps provided |

**With the combo command, agent files and validation are automatic!**

### Quick Verification

```bash
# Verify everything was created (already in combo command output)
oak constitution list-agent-files --json
```

If any step was skipped, note it in the final report.
