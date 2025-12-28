---
name: research-synthesis
description: Synthesize research findings for OAK planning using the oak.plan-research
  workflow. Use when consolidating findings from codebase exploration, comparing approaches,
  or creating research/*.md documents.
---

# OAK Research Synthesis

This skill provides expertise in synthesizing research findings for OAK's planning system - creating structured findings documents that inform task generation and implementation decisions.

## OAK Research System Overview

### Research in the OAK Workflow

```
/oak.plan-create          /oak.plan-research         /oak.plan-tasks
      │                          │                         │
      ↓                          ↓                         ↓
 plan.md with             research/<topic>.md         tasks.md
 Research Topics    ────►  for each topic      ────►  informed by
                                                      research
```

### File Structure

```
oak/plan/<plan-name>/
├── plan.md                    # Contains ## Research Topics
└── research/
    ├── research-manifest.yml  # Tracks research state
    ├── <topic-slug>.md        # Finding for each topic
    ├── api-integration.md
    ├── auth-patterns.md
    └── performance-approach.md
```

## When to Use This Skill

Use when you need to:
- Research topics identified in an OAK plan
- Consolidate findings from codebase exploration
- Compare multiple technical approaches
- Create `research/<topic>.md` documents
- Synthesize web research and documentation review

## Source Categories for OAK Research

### Codebase Analysis (Primary)
- Existing patterns and conventions
- Similar feature implementations
- Test patterns and coverage strategies
- Architecture decisions in code

### Project Documentation
- `oak/constitution.md` - Project standards
- Architecture docs in `docs/`
- API documentation
- README files

### External Research (via web search)
- Library documentation
- Best practices guides
- Similar project implementations
- Industry standards (2024-2025 content preferred)

## OAK Research Document Format

Each topic becomes `research/<topic-slug>.md`:

```markdown
# Research: [Topic Name]

## Objective
What we're trying to learn or decide.

## Sources Consulted
- [x] Codebase patterns (searched: [what])
- [x] Project documentation
- [ ] External resources
- [ ] Constitution requirements

## Key Findings

### Finding 1: [Title]
- **Source**: [Where discovered - file path, URL, or doc]
- **Relevance**: [How it applies to our plan]
- **Confidence**: High/Medium/Low

### Finding 2: [Title]
- **Source**: [Where discovered]
- **Relevance**: [How it applies]
- **Confidence**: High/Medium/Low

## Synthesis

### Patterns Identified
- [Pattern 1]: [Where found, how to apply]
- [Pattern 2]: [Where found, how to apply]

### Contradictions/Tensions
- [Issue 1]: [Resolution approach]

### Gaps Identified
- [Gap 1]: [Mitigation or acceptance]

## Recommendation

**Decision**: [Chosen approach]

**Rationale**:
- [Reason 1 with evidence]
- [Reason 2 with evidence]

**Alternatives Considered**:
- [Alternative 1]: [Why not chosen]

## Impact on Tasks
[How this research affects task generation]

## Open Questions
[Things still needing investigation - may spawn additional research]
```

## Research Workflow

### Step 1: Load Plan Context

Read the plan to understand research topics:

```markdown
## Research Topics (from plan.md)

- **API Integration**: How to integrate with external service
  - Questions: Authentication pattern? Rate limiting?
  - Priority: High

- **Caching Strategy**: Where and how to cache
  - Questions: Redis vs in-memory? TTL approach?
  - Priority: Medium
```

### Step 2: Prioritize and Research

Research topics by priority:
1. **High priority** - Research immediately, blocks other work
2. **Medium priority** - Research before task generation
3. **Low priority** - Can research during implementation

### Step 3: Synthesis Process

For each topic:

1. **Organize findings** by source type and confidence
2. **Identify patterns** - consistent approaches across sources
3. **Note contradictions** - resolve or escalate
4. **Create recommendation** with evidence-based rationale
5. **Document impact** on upcoming tasks

### Step 4: Cross-Reference with Constitution

Every recommendation should reference constitution alignment:

```markdown
## Constitution Alignment

- **Architecture**: Recommendation follows [pattern] per constitution §Architecture
- **Testing**: Will require [test approach] per constitution §Testing
- **Documentation**: Need to document [what] per constitution §Documentation
```

## Quality Indicators for OAK Research

Good synthesis demonstrates:
- Multiple source corroboration (code + docs + external)
- Clear reasoning chain from findings to recommendation
- Constitution alignment explicitly stated
- Practical applicability to tasks
- Acknowledged uncertainties with mitigation

## Best Practices

1. **Cite sources** - Include file paths, URLs, line numbers for traceability
2. **Quantify confidence** - Not all findings are equal
3. **Note contradictions** - Don't force false consensus
4. **Prioritize codebase** - Existing patterns often trump external best practices
5. **Test assumptions** - Validate critical findings with actual code
6. **Update manifest** - Mark topics as complete in research-manifest.yml

## Integration with OAK Commands

| Command | Research Role |
|---------|--------------|
| `/oak.plan-create` | Identifies research topics |
| `/oak.plan-research` | **This is the research command** |
| `/oak.plan-tasks` | Consumes research findings |
| `/oak.plan-implement` | May spawn ad-hoc research |

## Quick Reference

- **Research location**: `oak/plan/<name>/research/<topic-slug>.md`
- **State tracking**: `oak/plan/<name>/research/research-manifest.yml`
- **Input**: Topics from `oak/plan/<name>/plan.md` § Research Topics
- **Output**: Feeds into `/oak.plan-tasks` for task generation
- **Constitution**: Always check `oak/constitution.md` for alignment
