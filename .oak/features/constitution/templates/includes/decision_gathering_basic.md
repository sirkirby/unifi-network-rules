## Interactive Decision Gathering

**NEVER generate a constitution without explicit user decisions on the RELEVANT areas identified above.**

**Reference:** `features/constitution/templates/decision_points.yaml` is your source of truth for:
- All options for each decision category
- Characteristics and "best for" guidance per option
- Follow-up questions triggered by specific choices
- Presentation templates (`confirmation_template`)

Read the YAML and use it to structure your conversation. Present options clearly, collect the user's selection, then ask the relevant follow-up questions.

### Decision Categories

Work through each RELEVANT category from the YAML:

1. **testing_strategy** - Testing approach, coverage, TDD, E2E
2. **code_review** - Review policy, approvals, hotfix handling
3. **documentation** - Documentation level, ADRs, docstrings
4. **ci_cd** - CI/CD enforcement, required checks, platform
5. **architectural_patterns** - Architecture pattern, error handling, DI (if applicable)

### Presentation Pattern

For each decision point, follow this pattern:

```text
=== [Category Name] Decision ===

[Question from YAML]

1  [Option Name]
   - [Key characteristics from YAML]
   Best for: [best_for from YAML]

2  [Option Name]
   - [Key characteristics]
   Best for: [best_for]

[Continue for all options...]

Which option fits your project? (1-N)
```

**After user selects**, ask the follow-up questions specified in the YAML for that selection.

### Greenfield vs Brownfield

- **Greenfield**: Present all options, let user choose
- **Brownfield**: Present current state FIRST (from project analysis), then ask if they want to keep, elevate, or relax standards

### Decision Confirmation Checkpoint

**After gathering all RELEVANT decisions, present summary using the `confirmation_template` from the YAML:**

```text
==============================================
CONSTITUTION DECISION SUMMARY
==============================================

Project Type: [from relevance assessment]

Based on our conversation, here's what will be codified:

## Testing Strategy: [Selected Option]
- [Key details and follow-up answers]
- Rationale: [user's rationale]

## Code Review: [Selected Option]
- [Key details]

## Documentation: [Selected Option]
- [Key details]

## CI/CD: [Selected Option]
- [Key details]

## Architecture: [Selected Pattern OR N/A]
- [If applicable: details]
- [If N/A: reason why skipped]

==============================================

CHECKPOINT

Do these decisions accurately reflect your project needs?

- "yes" -> Proceed with constitution generation
- "no" -> Cancel and restart decision process
- "revise [topic]" -> Modify specific decision

Your response: ___
```

**Wait for user confirmation before proceeding to constitution generation.**

If user says "revise [topic]", go back to that specific decision point and re-ask.
