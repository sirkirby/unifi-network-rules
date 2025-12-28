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
