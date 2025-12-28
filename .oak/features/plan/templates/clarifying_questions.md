## Idea-Based Planning

You're planning from an idea or concept. This path gathers requirements through clarifying questions to build a comprehensive plan.

### Clarifying Questions Phase

Before creating the plan, gather essential context:

**Scope Questions:**
- What is the primary objective of this plan?
- What problem are we solving or opportunity are we pursuing?
- What is in scope? What is explicitly out of scope?
- What are the key constraints (technical, timeline, resources)?

**Research Questions:**
- What unknowns need investigation before implementation?
- Are there competing approaches to evaluate?
- What external resources, APIs, or tools might be involved?
- What existing codebase patterns should inform this work?

**Success Questions:**
- How will we know when this is complete?
- What are the acceptance criteria for success?
- Who are the stakeholders and what do they need?

**Present questions strategically:**
- Group related questions together
- Provide examples or defaults where helpful
- Prioritize questions that unlock other answers

### Create Plan Structure

Once you have sufficient context:

```bash
# Create the plan with a URL-safe name
oak plan create <plan-name> --display-name "Human Readable Name"

# Example:
oak plan create auth-redesign --display-name "Authentication System Redesign"
```

The CLI will:
- Create `oak/plan/<plan-name>/` directory
- Initialize `plan.md` with basic structure
- Create `.manifest.json` with metadata
- Create `research/` directory for findings
- Create a git branch `plan/<plan-name>`

### Populate Plan Content

Edit `oak/plan/<plan-name>/plan.md` to include:

**Overview Section:**
- Executive summary of what this plan achieves
- Problem statement or opportunity description
- High-level approach

**Goals Section:**
- 3-5 specific, measurable objectives
- Each goal should be testable/verifiable

**Success Criteria Section:**
- How success will be measured
- Specific outcomes or deliverables

**Scope Section:**
- What's in scope (features, components, etc.)
- What's explicitly out of scope
- Known boundaries and limitations

**Constraints Section:**
- Technical constraints (languages, frameworks, APIs)
- Resource constraints (time, team, budget)
- Organizational constraints (approvals, dependencies)

### Identify Research Topics

Based on the clarifying conversation, create research topics:

**Research Topic Structure:**
```markdown
### Topic Title
**Slug:** `url-safe-slug`
**Priority:** 1-5 (1 = highest)
**Status:** pending

Description of what to research and why.

**Questions to answer:**
- Specific question 1?
- Specific question 2?

**Sources to check:**
- Documentation links
- Similar projects
- Internal resources
```

**Good Research Topics:**
- Technology comparisons (e.g., "OAuth Providers")
- Architecture patterns (e.g., "Event Sourcing Patterns")
- Integration approaches (e.g., "Payment Gateway APIs")
- Codebase analysis (e.g., "Existing Auth Patterns")

**Research Depth:**
- `minimal`: Quick validation, 1-2 sources
- `standard`: Comprehensive overview, 3-5 sources (default)
- `comprehensive`: Deep dive, extensive sources, comparisons
