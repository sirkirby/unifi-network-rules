---
name: planning-workflow
description: Guide OAK strategic implementation planning with structured phases, constitution
  alignment, and the oak.plan-* command workflow. Use when creating plans, understanding
  OAK planning conventions, or structuring development work.
---

# OAK Strategic Planning Workflow

This skill provides domain expertise for OAK's planning system - creating implementation plans that align with project constitutions, follow OAK file conventions, and integrate with the oak.plan-* command workflow.

## OAK Planning System Overview

### Command Workflow

```
/oak.plan-create  →  /oak.plan-research  →  /oak.plan-tasks  →  /oak.plan-implement
        │                    │                     │                     │
        ↓                    ↓                     ↓                     ↓
   plan.md            research/*.md           tasks.md           Implementation
                                                   │
                                                   ↓
                                          /oak.plan-export
                                          (GitHub/ADO issues)
```

### File Structure

```
oak/
├── constitution.md          # Project standards (required first)
└── plan/
    └── <plan-name>/
        ├── plan.md          # Main plan document
        ├── .manifest.json   # Plan metadata and state
        ├── tasks.md         # Generated task breakdown
        ├── issue/           # Issue context (if issue-based)
        │   ├── summary.md
        │   └── related/
        └── research/        # Research findings
            ├── <topic>.md
            └── research-manifest.yml
```

## When to Use This Skill

Use when you need to:
- Create a new implementation plan (`/oak.plan-create`)
- Understand OAK's planning conventions and file formats
- Structure development work following OAK patterns
- Ensure plan alignment with project constitution
- Generate well-defined success criteria

## Planning Framework (OAK-Specific)

### Phase 1: Context Gathering

Before planning, OAK requires:

**Source Material**
- Issue tracking details (ADO #123, GitHub #42) - fetched automatically
- Stakeholder requirements via clarifying questions
- Related existing features in codebase

**Constitution Requirements** (from `oak/constitution.md`)
- Architecture patterns to follow
- Testing requirements (TDD, coverage %)
- Documentation standards
- Code style guidelines

**Technical Landscape**
- Existing patterns in codebase (explored via `/oak.plan-create`)
- Similar implementations to reference
- Integration points

### Phase 2: Scope Definition

OAK plans require clear boundaries in these sections:

**In Scope** (## Scope > ### In Scope)
- Core functionality required
- Must-have features
- Required integrations

**Out of Scope** (## Scope > ### Out of Scope)
- Future enhancements
- Nice-to-have features
- Separate concerns

**Assumptions** (document in ## Constraints)
- Technical assumptions
- Resource assumptions
- Dependencies on external factors

### Phase 3: Risk Assessment

OAK plans include risks in a structured format:

```markdown
## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Integration complexity | High | Prototype early, create fallback |
| Skill gaps | Medium | Pair programming, documentation |
| Dependencies | Medium | Buffer time, parallel workstreams |
```

### Phase 4: Research Topics

Identify unknowns for `/oak.plan-research`:

```markdown
## Research Topics

- **[Topic Name]**: [What we need to learn]
  - Questions: [Specific questions to answer]
  - Priority: High/Medium/Low
```

### Phase 5: Success Criteria

Define measurable outcomes:

```markdown
## Success Criteria

- [ ] [Functional criterion - feature works as specified]
- [ ] [Quality criterion - test coverage, performance]
- [ ] [Process criterion - documentation, review]
- [ ] [Constitution compliance - all MUST rules followed]
```

## OAK Plan Document Structure

This is the expected format for `oak/plan/<name>/plan.md`:

```markdown
# Plan: [Title]

## Overview
[1-2 paragraph summary of what will be built]

## Goals
- [Goal 1]
- [Goal 2]

## Success Criteria
- [ ] [Criterion 1]
- [ ] [Criterion 2]

## Scope

### In Scope
- [Item 1]

### Out of Scope
- [Item 1]

## Constraints
- [Constraint 1]

## Research Topics
- [Topic 1]: [Why needed]

## Risks & Mitigations
| Risk | Impact | Mitigation |
|------|--------|-----------|
| [Risk] | High/Med/Low | [Strategy] |

## Constitution Compliance
- Architecture: [How plan aligns]
- Testing: [Test strategy per constitution]
- Documentation: [Doc requirements]
```

## Best Practices for OAK Plans

1. **Start with the constitution** - Read `oak/constitution.md` first; let project standards guide the plan
2. **Use issue context** - If issue-driven, leverage fetched acceptance criteria and related issues
3. **Identify research topics** - Unknowns become research topics for `/oak.plan-research`
4. **Define done clearly** - Success criteria should be verifiable
5. **Consider testing early** - Note constitution's test requirements (TDD vs test-after)
6. **Plan for iteration** - OAK supports research → tasks → implement cycle

## Integration with OAK Commands

| Command | Purpose | When to Use |
|---------|---------|-------------|
| `/oak.plan-create` | Create initial plan | Starting new work |
| `/oak.plan-research` | Research unknowns | Topics identified in plan |
| `/oak.plan-tasks` | Generate task breakdown | After research complete |
| `/oak.plan-validate` | Validate plan quality | Before implementation |
| `/oak.plan-implement` | Execute tasks | Ready to code |
| `/oak.plan-export` | Export to issue tracker | Tasks ready for tracking |

## Quick Reference

- **Plan location**: `oak/plan/<name>/plan.md`
- **Constitution**: `oak/constitution.md` (always read first)
- **Branch naming**: `plan/<name>` or `<issue-id>/<name>`
- **Research output**: `oak/plan/<name>/research/<topic>.md`
- **Tasks output**: `oak/plan/<name>/tasks.md`
