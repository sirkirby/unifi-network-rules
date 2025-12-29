---
name: task-decomposition
description: Break down OAK plans into structured tasks using oak.plan-tasks conventions.
  Use when generating tasks.md, structuring work for export to GitHub/ADO, or organizing
  implementation phases.
---

# OAK Task Decomposition

This skill provides expertise in breaking down OAK implementation plans into actionable, well-structured tasks suitable for the `tasks.md` format and export to issue trackers.

## OAK Task System Overview

### Tasks in the OAK Workflow

```
/oak.plan-create    /oak.plan-research    /oak.plan-tasks      /oak.plan-export
      │                    │                    │                     │
      ↓                    ↓                    ↓                     ↓
  plan.md           research/*.md          tasks.md    ────►   GitHub Issues
                                                               or ADO Work Items
                                               │
                                               ↓
                                       /oak.plan-implement
                                         (execute tasks)
```

### File Structure

```
oak/plan/<plan-name>/
├── plan.md              # Goals, scope, research topics
├── research/            # Research findings
├── tasks.md             # Generated task breakdown (THIS FILE)
└── .manifest.json       # Tracks task completion state
```

## When to Use This Skill

Use when you need to:
- Generate `tasks.md` from plan and research (`/oak.plan-tasks`)
- Structure work for sprint planning
- Define task dependencies and ordering
- Create acceptance criteria aligned with plan goals
- Prepare tasks for export to GitHub/ADO

## OAK Task Hierarchy

### Level 1: Epic
- Theme-level grouping (maps to plan Goals)
- Multiple sprints of work
- Business objective alignment

### Level 2: Story
- User-visible functionality
- Single sprint deliverable
- Clear acceptance criteria

### Level 3: Task
- Technical implementation unit
- Hours to a few days of work
- Independently testable

### Level 4: Subtask
- Granular work item
- Single session of work
- Part of larger task

## OAK tasks.md Format

This is the expected format for `oak/plan/<name>/tasks.md`:

```markdown
# Tasks: [Plan Name]

## Summary
[Brief overview of task breakdown approach]

## Epic 1: [Epic Title - from plan Goal]

### Story 1.1: [Story Title]
**Priority**: High/Medium/Low
**Estimate**: S/M/L or points
**Depends on**: [Story IDs if any]

#### Acceptance Criteria
- [ ] [Criterion 1 - verifiable]
- [ ] [Criterion 2 - from plan success criteria]
- [ ] Tests pass per constitution requirements

#### Tasks
- [ ] **Task 1.1.1**: [Action verb] [specific what] (S)
  - File: `path/to/file.py`
  - Details: [Implementation notes from research]

- [ ] **Task 1.1.2**: [Action verb] [specific what] (M)
  - Depends on: 1.1.1
  - File: `path/to/file.py`
  - Pattern: [Reference similar implementation]

### Story 1.2: [Story Title]
**Priority**: Medium
**Estimate**: M

#### Acceptance Criteria
- [ ] [Criterion]

#### Tasks
- [ ] **Task 1.2.1**: [Task description] (S)

## Epic 2: [Epic Title]
...

## Dependencies Graph

```
1.1.1 → 1.1.2 → 1.2.1
         ↓
       1.1.3 → 2.1.1
```

## Testing Tasks (Constitution-Driven)

Per constitution testing requirements:
- [ ] Unit tests for [component] - coverage target: [%]
- [ ] Integration tests for [workflow]
- [ ] [TDD note if constitution requires test-first]

## Documentation Tasks

Per constitution documentation requirements:
- [ ] Update [specific docs]
- [ ] Add inline comments for complex logic
- [ ] Update API docs (if applicable)

## Notes
- [Important consideration from research]
- [Risk mitigation approach]
```

## Task Generation from Plan + Research

### Step 1: Map Goals to Epics

```markdown
# From plan.md:
## Goals
- Implement user authentication       → Epic 1: Authentication
- Add API rate limiting               → Epic 2: Rate Limiting
- Create admin dashboard              → Epic 3: Admin Dashboard
```

### Step 2: Derive Stories from Scope

```markdown
# From plan.md:
## Scope
### In Scope
- OAuth2 integration                  → Story 1.1: OAuth2 Setup
- Session management                  → Story 1.2: Session Handling
- JWT token refresh                   → Story 1.3: Token Management
```

### Step 3: Inform Tasks from Research

```markdown
# From research/auth-patterns.md:
## Recommendation
Use existing AuthService pattern at src/services/auth.py

# Becomes:
- [ ] **Task 1.1.1**: Extend AuthService with OAuth2 provider (M)
  - File: `src/services/auth.py`
  - Pattern: Follow existing provider pattern (lines 45-80)
```

### Step 4: Apply Constitution Requirements

```markdown
# From oak/constitution.md:
## Testing
- MUST have 80% coverage for new code
- SHOULD use TDD for complex logic

# Add to tasks:
## Testing Tasks (Constitution-Driven)
- [ ] Write tests BEFORE implementation (TDD per constitution)
- [ ] Achieve 80% coverage for auth module
```

## OAK Phased Task Structure

Standard OAK phases (adjust based on constitution):

**Phase 1: Setup & Investigation**
```markdown
- [ ] Setup: Review plan context and research findings
- [ ] Setup: Identify affected modules from codebase exploration
- [ ] Setup: Configure dependencies per constitution
```

**Phase 2: Core Implementation** (or Phase 3 if TDD)
```markdown
- [ ] Implement: [Requirement 1]
  - File: [path]
  - Function: [name]
  - Pattern: [reference]
```

**Phase 3: Testing** (or Phase 2 if TDD)
```markdown
- [ ] Test: [Component] unit tests
  - File: `tests/unit/test_[component].py`
  - Coverage: [target %]
```

**Phase 4: Integration**
```markdown
- [ ] Integration: Connect with [related system]
- [ ] Integration: End-to-end workflow verification
```

**Phase 5: Polish & Documentation**
```markdown
- [ ] Documentation: Update [files per constitution]
- [ ] Quality: Run linters per constitution
- [ ] Quality: Final constitution compliance check
```

## Task Quality Checklist

Every task should have:
- [ ] **Clear title** - Action verb + specific what
- [ ] **File reference** - Where work happens
- [ ] **Size estimate** - S/M/L or points
- [ ] **Dependencies** - What must come first
- [ ] **Acceptance criteria** at story level

## Estimation Guidelines (OAK Convention)

### T-Shirt Sizing
| Size | Complexity | Example |
|------|-----------|---------|
| XS | Trivial | Config change |
| S | Low | Simple function |
| M | Medium | New feature |
| L | High | Complex integration |
| XL | Very High | Should decompose further |

### Story Points (Alternative)
| Points | Description |
|--------|-------------|
| 1 | Trivial, well-understood |
| 3 | Moderate, some unknowns |
| 5 | Complex, needs investigation |
| 8+ | Too large, decompose |

## Export Considerations

Tasks in `tasks.md` can export to:

**GitHub Issues** (`/oak.plan-export`)
- Epics → Milestones or Labels
- Stories → Issues with acceptance criteria
- Tasks → Checklist items in issue body

**Azure DevOps** (`/oak.plan-export`)
- Epics → Epics
- Stories → User Stories
- Tasks → Tasks linked to stories

## Best Practices

1. **INVEST criteria** - Independent, Negotiable, Valuable, Estimatable, Small, Testable
2. **Vertical slices** - Deliver user value, not horizontal layers
3. **Right-size tasks** - S/M preferred, L should be rare
4. **Front-load risk** - Put unknown work early
5. **Include testing** - Tests are not optional add-ons
6. **Reference files** - Always include specific paths

## Integration with OAK Commands

| Command | Task Role |
|---------|-----------|
| `/oak.plan-create` | Defines goals → epics |
| `/oak.plan-research` | Informs implementation details |
| `/oak.plan-tasks` | **Generates tasks.md** |
| `/oak.plan-implement` | Executes tasks with tracking |
| `/oak.plan-export` | Exports to issue tracker |
| `/oak.plan-validate` | Validates task completeness |

## Quick Reference

- **Tasks location**: `oak/plan/<name>/tasks.md`
- **State tracking**: `oak/plan/<name>/.manifest.json`
- **Input**: `plan.md` goals + `research/*.md` findings
- **Constitution**: Check `oak/constitution.md` for test/doc requirements
- **Export targets**: GitHub Issues, Azure DevOps Work Items
