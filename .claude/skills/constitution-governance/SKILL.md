---
name: constitution-governance
description: Guide OAK constitution maintenance with amendment workflows, validation
  frameworks, semantic versioning, and agent instruction synchronization.
---

# Constitution Governance Expertise

Guide the ongoing maintenance, amendment, and validation of engineering constitutions.

## OAK Constitution Governance Workflow

```
Validate Current State  →  Propose Amendment  →  Apply & Version  →  Sync Agent Files
```

### CLI Commands

| Command | Purpose |
|---------|---------|
| `oak constitution validate --json` | Validate structure and reality alignment |
| `oak constitution add-amendment` | Add versioned amendment |
| `oak constitution update-agent-files` | Sync agent instruction files |
| `oak constitution list-agent-files --json` | List synced agent files |
| `oak constitution analyze --json` | Analyze project for reality checks |

## Amendment Process

### When to Amend

Amend the constitution when:

- **Standards evolve**: Team adopts new practices (e.g., TDD adoption)
- **Reality changes**: Project capabilities change (e.g., E2E infrastructure added)
- **Gaps identified**: Validation reveals missing or incorrect requirements
- **Incidents occur**: Post-mortems identify process improvements
- **Team changes**: New team composition requires different standards

### Amendment Types (Semantic Versioning)

Constitution amendments follow semantic versioning:

| Type | Version Bump | When to Use | Examples |
|------|--------------|-------------|----------|
| **Major** | X.0.0 | Breaking changes that invalidate existing requirements | Changing from TDD to test-after, removing mandatory reviews |
| **Minor** | 0.X.0 | New requirements without breaking existing ones | Adding E2E requirements, new architectural section |
| **Patch** | 0.0.X | Clarifications that don't change meaning | Fixing typos, clarifying ambiguous language |

### Amendment Classification Guide

**Major (Breaking)**:
- Changing MUST to MAY for core requirements
- Removing entire sections
- Fundamentally changing architectural pattern
- Reducing coverage requirements significantly

**Minor (Additive)**:
- Adding new sections
- Adding new requirements (MUST/SHOULD)
- Documenting previously implicit practices
- Adding architectural pattern documentation

**Patch (Clarification)**:
- Fixing typos and grammar
- Rewording for clarity (same meaning)
- Updating dates and metadata
- Adding examples to existing requirements

### Amendment Workflow

```
1. Preflight Check
   └── Verify constitution exists
   └── Check current version
   └── Review recent amendments

2. Requirements Gathering
   └── Summary (< 80 chars)
   └── Detailed rationale
   └── Target section(s)
   └── Amendment type recommendation

3. Impact Analysis
   └── Quote affected sections
   └── Check against codebase reality
   └── Identify downstream effects

4. Apply Amendment
   └── oak constitution add-amendment
   └── Verify version bump
   └── Review diff

5. Sync Agent Files
   └── oak constitution update-agent-files --dry-run
   └── oak constitution update-agent-files
   └── Verify all files updated

6. Quality Review
   └── Run validation
   └── Check consistency
   └── Confirm next steps
```

## Validation Framework

### Quality Rubric (Score 1-5)

| Dimension | 1 | 3 | 5 |
|-----------|---|---|---|
| **Clarity & Enforceability** | Vague, untestable | Some clear, some ambiguous | All explicit and measurable |
| **Alignment with Standards** | Contradicts practices | Mostly aligned | Fully reflects team practices |
| **Completeness & Coverage** | Major gaps | Core areas covered | Comprehensive with rationale |
| **Consistency & Traceability** | Contradictions present | Minor inconsistencies | Fully coherent |
| **Operational Readiness** | Cannot act on it | Partially actionable | Teams can follow today |

### Structural Validation

**Required sections** (must exist):
- Metadata (version, author, date)
- Principles
- Architecture
- Code Standards
- Testing
- Documentation
- Governance

**Metadata validation**:
- Version follows semantic versioning (X.Y.Z)
- Dates follow ISO format (YYYY-MM-DD)
- Author is non-empty
- Status is valid (Draft, Ratified, Superseded)

**Token validation**:
- No template tokens remaining: `{{`, `}}`, `[TODO]`, `[PLACEHOLDER]`

### Language Validation

**Check for weak language** that should be strengthened:
- "should try to" → SHOULD
- "ideally" → SHOULD or remove
- "if possible" → MAY or be specific
- "best practice" → Specific requirement

**Check for missing RFC 2119 keywords**:
- Requirements without MUST/SHOULD/MAY are ambiguous
- Each requirement should have clear obligation level

### Reality Alignment Validation

Compare requirements against project reality:

| Requirement Area | Validation Approach |
|-----------------|---------------------|
| Coverage targets | Run coverage tool, compare to target |
| E2E tests | Search for e2e/integration test files |
| CI/CD | Check .github/workflows, gitlab-ci, etc. |
| Code review | Check branch protection, recent PR history |
| Documentation | Check README, docs/, API docs existence |

**Alignment classifications**:
- **Aligned**: Requirement matches reality
- **Aspirational with plan**: Gap exists but timeline documented
- **Aspirational without plan**: Gap exists, no timeline (flag as issue)
- **Contradictory**: Requirement contradicts reality (flag as critical)

### Validation Severity Levels

**Critical** (must fix before adoption):
- Missing required sections
- Template tokens remaining
- Contradictions with adopted standards
- Reality contradictions without timeline

**Major** (should fix soon):
- Aspirational requirements without timelines
- Weak language in core requirements
- Missing rationale for MUST requirements
- Incomplete metadata

**Minor** (nice-to-have):
- Stylistic inconsistencies
- Missing examples
- Could use more detail
- Minor formatting issues

## Agent Instruction Synchronization

### What Gets Synced

Agent instruction files (e.g., `CLAUDE.md`) are derived from the constitution and contain:
- Project-specific coding standards
- Testing requirements
- Documentation standards
- Architecture patterns
- Code review expectations

### When to Sync

Sync agent instruction files:
- After any constitution amendment
- After adding new agents to the project
- When validation identifies drift

### Sync Workflow

```bash
# Preview changes
oak constitution update-agent-files --dry-run

# Review the diff output

# Apply changes (creates backups automatically)
oak constitution update-agent-files

# Verify updates
oak constitution list-agent-files --json
```

### Handling Sync Conflicts

When agent files have local modifications:

1. **Backup existing**: Always create backup before sync
2. **Diff review**: Compare constitution-derived vs. local content
3. **Merge decision**:
   - If local changes are obsolete: Allow sync to overwrite
   - If local changes are valuable: Amend constitution first, then sync
   - If both needed: Manual merge required

## Governance Best Practices

### Review Cadence

| Trigger | Review Type | Scope |
|---------|-------------|-------|
| **Quarterly** | Scheduled | Full constitution review |
| **Post-incident** | Reactive | Affected sections |
| **Team change** | Adaptive | Governance, onboarding sections |
| **Major release** | Milestone | All sections |

### Change Log Maintenance

Track amendments in constitution:

```markdown
## Amendment Log

| Version | Date | Type | Summary | Author |
|---------|------|------|---------|--------|
| 1.2.0 | 2025-01-15 | Minor | Added E2E testing requirements | @dev |
| 1.1.1 | 2025-01-10 | Patch | Clarified coverage enforcement | @lead |
| 1.1.0 | 2025-01-05 | Minor | Added Result Pattern for error handling | @dev |
```

### Compliance Monitoring

Track constitution compliance:

1. **Automated checks**: CI/CD validates measurable requirements
2. **Manual audits**: Quarterly review of non-automatable requirements
3. **Incident tagging**: Link incidents to constitution requirements
4. **Trend analysis**: Track compliance over time

## Common Governance Issues

| Issue | Symptom | Solution |
|-------|---------|----------|
| **Drift** | Agent files don't match constitution | Run sync workflow |
| **Staleness** | Requirements outdated | Quarterly review + amendments |
| **Over-prescription** | Too many MUSTs, team ignores | Downgrade to SHOULD, focus on critical |
| **Under-prescription** | Inconsistent practices | Add specific requirements |
| **Reality gap** | Requirements vs. actual practice | Add timelines or adjust requirements |
| **Version confusion** | Unclear which version is current | Update metadata, sync agent files |

## Modernization Assessment

### Old-Style Constitution Indicators

Detect constitutions that could benefit from modernization:

- **No decision context**: Requirements without "why"
- **Hardcoded values**: Fixed numbers without rationale
- **Missing architecture**: No architectural pattern documentation
- **Template defaults**: Generic requirements not customized
- **Reality misalignment**: Many aspirational MUSTs

### Modernization Approaches

| Approach | When to Use | Effort |
|----------|-------------|--------|
| **Validate only** | Constitution mostly good, minor fixes | Low |
| **Incremental** | Good structure, needs updates | Medium |
| **Regenerate** | Significant gaps, easier to restart | High |

**Recommended**: Start with validation, then decide based on findings.
