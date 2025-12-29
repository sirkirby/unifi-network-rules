---
name: constitution-authoring
description: Guide OAK engineering constitution creation with decision-driven requirements,
  requirement language patterns, and reality-grounded standards.
---

# Constitution Authoring Expertise

Guide the creation of effective engineering constitutions that balance aspirational standards with project reality.

## OAK Constitution Workflow

```
/oak.constitution-create  →  Analyze & Gather Decisions  →  Generate  →  /oak.constitution-validate
```

### CLI Commands

| Command | Purpose |
|---------|---------|
| `oak constitution create` | Generate constitution from decisions |
| `oak constitution analyze --json` | Analyze project structure and capabilities |
| `oak constitution validate --json` | Validate structure and quality |
| `oak constitution list-agent-files` | List synced agent instruction files |

### File Structure

```
oak/
├── constitution.md              # Main engineering constitution
└── agent-instructions/          # Per-agent instruction files (synced)
    ├── CLAUDE.md
    └── ...
```

## Decision-Driven Constitution Creation

Constitutions should be **decision-driven**, not template-filled. Each section should reflect explicit decisions about project standards.

### Core Decision Points

#### 1. Testing Strategy
Choose based on project maturity, team size, and risk tolerance:

| Strategy | Coverage | TDD | E2E | Best For |
|----------|----------|-----|-----|----------|
| **Comprehensive** | High (80%+) | Required | Required | Critical systems, regulated industries |
| **Balanced** | Moderate (60-80%) | Encouraged | Recommended | Most production applications |
| **Pragmatic** | Flexible | Optional | Optional | MVPs, prototypes, rapid iteration |

**Decision questions**:
- What's the cost of a bug in production?
- How often does the team refactor?
- Is there existing test infrastructure?

#### 2. Architectural Pattern
Choose based on domain complexity and team experience:

| Pattern | Complexity | Coupling | Best For |
|---------|------------|----------|----------|
| **Clean Architecture** | High | Very Low | Complex domains, long-lived systems |
| **Vertical Slice** | Medium | Low | Feature-focused teams, rapid delivery |
| **Modular Monolith** | Medium | Medium | Future microservices candidates |
| **Layered** | Low | Medium | Traditional enterprise apps |
| **Pragmatic** | Adaptive | Varies | Mixed complexity, smaller teams |

**Decision questions**:
- How complex is the business domain?
- Will the team grow significantly?
- Is eventual microservices extraction needed?

#### 3. Documentation Level
Choose based on team turnover and system complexity:

| Level | Public APIs | Internal | ADRs | Best For |
|-------|-------------|----------|------|----------|
| **Extensive** | All documented | All documented | Required | High turnover, complex systems |
| **Standard** | All documented | Complex only | Recommended | Most teams |
| **Minimal** | Critical only | None | Optional | Small stable teams, simple systems |

**Decision questions**:
- How often do new engineers join?
- How complex is the domain?
- Is this a long-term system?

#### 4. Code Review Policy
Choose based on team trust and risk tolerance:

| Policy | Reviews | Approvals | Direct Commits | Best For |
|--------|---------|-----------|----------------|----------|
| **Strict** | All PRs | 1-2 required | Never allowed | Regulated, critical systems |
| **Standard** | All PRs | 1 required | Hotfixes only | Most production teams |
| **Flexible** | Recommended | Optional | Simple changes | High-trust small teams |

**Decision questions**:
- What's the team's experience level?
- Are there compliance requirements?
- How fast must fixes be deployed?

#### 5. CI/CD Enforcement
Choose based on infrastructure maturity:

| Level | Quality Gates | Coverage Check | Deploy Blocking |
|-------|---------------|----------------|-----------------|
| **Full** | All must pass | Enforced | Yes |
| **Standard** | Most must pass | Advisory | Most |
| **Basic** | Advisory | No | No |

## Requirement Language (RFC 2119)

Use precise requirement keywords to indicate obligation levels:

| Keyword | Meaning | Use When |
|---------|---------|----------|
| **MUST** | Absolute requirement | Violation is unacceptable |
| **MUST NOT** | Absolute prohibition | Action is never acceptable |
| **SHOULD** | Strong recommendation | Exceptions need justification |
| **SHOULD NOT** | Strong discouragement | Only in unusual cases |
| **MAY** | Optional | Team discretion |

### Language Patterns

**Strong requirement (MUST)**:
```markdown
- All public APIs MUST be documented
- Tests MUST be deterministic and repeatable
- Security patches MUST be applied within 2 weeks
```

**Recommendation (SHOULD)**:
```markdown
- Complex logic SHOULD include inline comments
- Code reviews SHOULD be completed within 24 hours
- Integration tests SHOULD cover critical paths
```

**Optional (MAY)**:
```markdown
- Teams MAY use pair programming for complex features
- Documentation MAY include diagrams
- E2E tests MAY be skipped for internal tools
```

### Avoid Weak Language

| Instead of | Use |
|------------|-----|
| "should try to" | "SHOULD" |
| "ideally" | "SHOULD" or remove |
| "if possible" | "MAY" or remove |
| "we want to" | "MUST" or "SHOULD" |
| "best practice" | Specific requirement |

## Reality Alignment

Constitution requirements must be achievable, not aspirational fantasies.

### Reality Check Questions

Before adding a requirement, ask:

1. **Current State**: Does the project already do this? If not, what's needed?
2. **Enforcement**: Can this be checked automatically? If not, how is it verified?
3. **Exceptions**: When is it acceptable to deviate? Document the exception process.
4. **Timeline**: If aspirational, when will it be achievable?

### Handling Gaps

When a requirement doesn't match reality:

| Situation | Approach |
|-----------|----------|
| **Nearly there** | Use MUST, add implementation plan |
| **Significant gap** | Use SHOULD with timeline |
| **Aspirational** | Use "Future Requirement" section |
| **Unrealistic** | Don't include it |

**Example: Coverage Gap**

If constitution wants 80% coverage but project has 45%:

```markdown
### Coverage Requirements

**Target:** 80% code coverage for new code

**Current State:** Project-wide coverage is 45%. New code MUST meet 80% target.
Existing code coverage will be increased incrementally per the Coverage Roadmap.

**Enforcement:** Coverage checks run in CI. New code below 80% will be flagged
but not blocked until Q2 2025.
```

## Section Writing Guide

### Principles Section
**Goal**: Define core values that guide all other decisions.

**Include**:
- Code quality philosophy
- Testing philosophy
- Documentation philosophy

**Each principle needs**:
- Clear requirements (MUST/SHOULD/MAY)
- Rationale explaining why

### Architecture Section
**Goal**: Document the chosen architectural pattern and its implications.

**Include**:
- Pattern name and description
- Core principles of the pattern
- Specific requirements for following the pattern
- Rationale for choosing this pattern

### Testing Section
**Goal**: Define the testing strategy with measurable requirements.

**Include**:
- Testing philosophy (comprehensive/balanced/pragmatic)
- Unit test requirements
- Integration test requirements (if applicable)
- E2E test requirements (if applicable)
- Coverage requirements with enforcement level

### Governance Section
**Goal**: Define how the constitution itself is maintained.

**Include**:
- Code review policy
- Amendment process
- Versioning approach
- Review cadence

## Quality Checklist

Before finalizing a constitution:

- [ ] **All decisions documented**: Each section reflects an explicit decision, not a default
- [ ] **Reality-aligned**: Requirements match current capabilities or have timelines
- [ ] **Measurable**: Requirements can be verified (automated or manual)
- [ ] **Consistent**: No contradictions between sections
- [ ] **RFC 2119 language**: MUST/SHOULD/MAY used consistently
- [ ] **Rationale provided**: Each requirement explains "why"
- [ ] **No template tokens**: All `{{placeholders}}` replaced
- [ ] **Metadata complete**: Version, author, date all present

## Common Pitfalls

| Pitfall | How to Fix |
|---------|------------|
| Aspirational MUSTs | Downgrade to SHOULD or add timeline |
| Missing rationale | Add "Rationale:" explaining why |
| Vague requirements | Add specific measurable criteria |
| Copy-pasted templates | Customize to actual project decisions |
| Over-prescription | Use SHOULD instead of MUST for non-critical items |
| No enforcement path | Add how requirement will be verified |
