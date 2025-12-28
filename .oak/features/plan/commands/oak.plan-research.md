---
description: Research topics from a strategic plan to gather insights and inform task generation.
requires:
  - path: oak/plan/<plan-name>/plan.md
    error: "Run /oak.plan first to create a plan with research topics."
  - path: oak/constitution.md
    error: "Run /oak.constitution-create to establish project standards."
generates:
  - oak/plan/<plan-name>/research/<topic-slug>.md
  - oak/plan/<plan-name>/research-manifest.yml (orchestration state)
handoffs:
  - label: Generate Tasks
    agent: oak.plan-tasks
    prompt: Generate structured tasks based on the plan and research findings.
  - label: Implement Directly
    agent: oak.plan-implement
    prompt: Skip task generation and implement directly from research findings (for simple plans).
---

## User Input

```text
$ARGUMENTS
```

This should be a plan name or can be inferred from the current git branch. If a specific topic slug is provided, focus on that topic. Otherwise, research all pending topics.

## Interaction Guidelines

**Always ask when:**
- Plan name is ambiguous or missing
- Topic prioritization needs adjustment
- Research scope needs clarification
- Multiple competing approaches are discovered

**Proceed without asking when:**
- Plan name is clearly stated or inferable from branch
- Research topics have clear questions defined
- Standard research workflow applies

## Responsibilities

1. Load the plan and identify research topics.
2. Research each topic thoroughly, prioritizing by priority level.
3. Create findings files in `research/{topic-slug}.md`.
4. Update topic status as research completes.
5. Support ad-hoc research that updates the plan.
6. Summarize findings and prepare for task generation.

## Research Strategy

{% if has_native_web %}
### Primary: Web Search

**You have native web search capabilities.** Use them proactively:

- Search for official documentation and guides
- Find recent articles and best practices (prioritize 2024-2025 content)
- Look for case studies and implementation examples
- Check for known issues, limitations, or gotchas
- Compare different approaches with real-world feedback

**Search Patterns:**
```text
"<technology> best practices 2025"
"<pattern> implementation guide"
"<library> vs <alternative> comparison"
"<topic> production experience"
```
{% else %}
### Research Without Native Web Search

This agent may not have built-in web search. Adapt your strategy:

{% if has_mcp %}
**MCP Tools Available**: Check for web search MCP servers:
- Keyless options: DuckDuckGo, web-fetch, Puppeteer
- Look for configured search tools in your available tools list
- Use MCP-based fetch for specific URLs if you know them
{% endif %}

**Codebase-First Research:**
- Explore existing implementations for patterns
- Read internal documentation
- Analyze similar features in the codebase
- Check configuration files and dependencies

**General Knowledge:**
- Apply established best practices
- Reference well-known patterns and architectures
- Document assumptions for later validation
{% endif %}

{% if has_background_agents %}
### Parallel Research with Background Agents (DEFAULT)

**You MUST use parallel research with background agents when 3+ independent topics exist.**

Parallel research is the DEFAULT mode for this agent. Only fall back to sequential research when topics have explicit dependencies.

**REQUIRED for parallel research (all must be true):**
- 3+ topics with priority 1-2
- Topics are independent (no dependencies between them)
- Topics don't require sequential learning (one informing another)

**Fall back to sequential ONLY when:**
- Topics explicitly build on each other
- Earlier findings MUST inform later research
- Research questions reference other topics' outputs

#### Launching Background Agents

**HOW TO LAUNCH:** {{ background_agent_instructions }}

For each topic, use this delegation prompt:

```markdown
# Research Assignment: <Topic Title>

## Context
- **Plan:** oak/plan/<plan-name>/plan.md
- **Constitution:** oak/constitution.md (focus: Architecture, Code Standards)
- **Output:** oak/plan/<plan-name>/research/<topic-slug>.md

## Your Research Topic

**Title:** <Topic Title>
**Priority:** <1-5>

**Description:**
<Full topic description from plan>

**Questions to Answer:**
1. <Research question 1>
2. <Research question 2>
3. <Research question 3>

**Sources to Check:**
- <Suggested source 1>
- <Suggested source 2>

## Research Strategy

1. Search for official documentation and best practices
2. Find implementation examples and case studies
3. Identify trade-offs and common pitfalls
4. Check how this aligns with constitution standards

## Output Format

Create a findings file with:
- Summary (2-3 sentences)
- Key insights (3-5 bullet points)
- Recommendations (actionable next steps)
- Trade-offs (pros/cons of approaches)
- Sources (with links where available)

## When Complete

Update the topic status to "completed" and return findings summary.
```

**Update manifest as agents complete:**
```yaml
- slug: "<topic-slug>"
  status: "completed"
  agent_assigned: true
  findings_file: "research/<topic-slug>.md"
  completed_at: "<timestamp>"
```
{% else %}
### Sequential Research

Research topics one at a time, starting with highest priority. This ensures earlier findings can inform later research.
{% endif %}

## Workflow

### 1. Load Plan and Topics

```bash
# Check current plan (from branch)
oak plan show

# Or specify explicitly
oak plan show <plan-name>

# View research status
oak plan research <plan-name>
```

Read the plan file to understand:
- Overall objectives and context
- Research topics with their questions
- Priority ordering
- Any completed research

### 1.5. Create Research Orchestration Manifest

Create `oak/plan/<plan-name>/research-manifest.yml` to track research state:

```yaml
version: 1.0
plan_name: "<plan-name>"
created_at: "<timestamp>"
research_mode: "{% if has_background_agents %}parallel{% else %}sequential{% endif %}"

constitution_references:
  - section: "Code Standards"
    relevance: "Implementation approaches must align"
  - section: "Architecture"
    relevance: "Research should consider existing patterns"

topics:
  - slug: "<topic-1-slug>"
    title: "<Topic 1 Title>"
    priority: 1
    status: "pending"  # pending, in_progress, completed, skipped
    {% if has_background_agents %}agent_assigned: false{% endif %}
    findings_file: null

  - slug: "<topic-2-slug>"
    title: "<Topic 2 Title>"
    priority: 2
    status: "pending"
    {% if has_background_agents %}agent_assigned: false{% endif %}
    findings_file: null
```

This manifest serves as the **single source of truth** for research progress, enabling:
- Resumability if interrupted
- Progress tracking across sessions
- Parallel coordination (if using background agents)

{% if has_background_agents %}
### 1.6. DECISION GATE: Research Mode Selection (REQUIRED)

**STOP and analyze topics before proceeding. You MUST explicitly choose a research mode.**

**Analysis Steps:**
1. List all research topics from plan.md
2. Identify dependencies between topics (does one topic's answer inform another's questions?)
3. Count topics with priority 1-2 that are independent
4. Check if topics can be researched in isolation

**Decision Rule:**
- **IF** 3+ priority 1-2 topics are independent:
  → **USE PARALLEL RESEARCH** (launch background agents in Step 2)
- **OTHERWISE**:
  → **USE SEQUENTIAL RESEARCH** (research one at a time in Step 2)

**MANDATORY OUTPUT - Document your decision:**
```text
## Research Mode Decision

Total topics: [X]
Priority 1-2 topics: [Y]
Independent topics: [Z]
Topics with dependencies: [list or "none"]

**Decision: [PARALLEL / SEQUENTIAL]**
**Reason:** [Brief explanation based on analysis above]
```

**Verify manifest is created before proceeding to Step 2.**
{% endif %}

### 2. Research Each Topic

For each pending topic, in priority order:

**A. Understand the Topic**
- Read the topic description and questions
- Understand how it relates to plan goals
- Identify what a good answer looks like

**B. Conduct Research**

{% if has_native_web %}
**Web Search (Primary):**
```text
1. Search for official documentation
2. Find implementation guides and tutorials
3. Look for comparisons and trade-off analyses
4. Check for common pitfalls and solutions
5. Find real-world experience reports
```
{% endif %}

**Codebase Exploration:**
```bash
# Find related patterns
rg "<keyword>" src/
rg "class.*<Pattern>" src/

# Check existing implementations
find . -name "*<related>*" -type f

# Review dependencies
cat pyproject.toml | grep <library>
```

{% if has_mcp %}
**MCP Tools:**
- Use available search/fetch tools
- Access external APIs if configured
- Leverage specialized research tools
{% endif %}

**C. Document Findings**

Create a research file at `oak/plan/<plan-name>/research/<topic-slug>.md`:

```markdown
# Research: <Topic Title>

**Date:** <YYYY-MM-DD>

## Summary

<2-3 sentence executive summary of findings>

## Key Insights

- <Most important finding 1>
- <Most important finding 2>
- <Most important finding 3>

## Recommendations

- <Recommended approach 1>
- <Recommended approach 2>

## Trade-offs

- <Trade-off 1: pros vs cons>
- <Trade-off 2: pros vs cons>

## Sources

- <Source 1 with link if available>
- <Source 2 with link if available>

## Notes

<Additional context, caveats, or future considerations>
```

**D. Update Topic Status**

Edit `plan.md` to update the topic:
- Change status from `pending` to `completed`
- Add findings_path reference
- Optionally update priority based on urgency

### 3. Ad-Hoc Research

If you discover new topics during research:

1. Add the new topic to `plan.md` with appropriate priority
2. Research it following the same process
3. Document how it relates to existing topics

This keeps the plan as a living document that evolves with understanding.

### 4. Cross-Reference Findings

After researching multiple topics:

- Identify connections between findings
- Note where recommendations align or conflict
- Update earlier findings if later research provides new context
- Document dependencies between research areas

### 5. Verify Research Completeness

Before proceeding to task generation, verify:

#### 5.1 Coverage Check

```text
## Research Verification

### Topic Coverage
| Topic | Status | Questions Answered | Recommendations |
|-------|--------|-------------------|-----------------|
| <topic-1> | ✅ | 3/3 | 2 |
| <topic-2> | ✅ | 4/4 | 3 |
| <topic-3> | ⏭️ Skipped | - | - |

### Constitution Alignment
| Section | Considered | Notes |
|---------|------------|-------|
| Architecture | ✅ | Findings align with existing patterns |
| Code Standards | ✅ | Recommendations follow conventions |
| Testing | ⚠️ | Need to add testing approach recommendations |
```

#### 5.2 Quality Gates

Before marking research complete:
- [ ] All priority 1-2 topics have findings files
- [ ] Each finding answers its defined research questions
- [ ] Recommendations are actionable (not vague)
- [ ] Trade-offs are documented for key decisions
- [ ] Sources are cited for important claims
- [ ] Findings align with constitution standards

#### 5.3 Gap Identification

Document any gaps for the implementation phase:
- Questions that couldn't be fully answered
- Areas needing validation during implementation
- Assumptions that should be tested early

### 6. Update Plan Status

```bash
# Mark research complete when all topics are done
oak plan status <plan-name> planning
```

### 7. Stop and Report

After completing research, provide a comprehensive summary:

```text
## Research Complete

**Plan:** <plan-name>
**Topics Researched:** <count>/<total>

### Research Summary

| Topic | Priority | Status | Key Finding |
|-------|----------|--------|-------------|
| <Topic 1> | 1 | ✅ | <One-line summary> |
| <Topic 2> | 2 | ✅ | <One-line summary> |
| <Topic 3> | 3 | ⏭️ | Skipped: <reason> |

### Key Insights Across Topics

1. **<Theme 1>**: <Cross-cutting insight>
2. **<Theme 2>**: <Cross-cutting insight>
3. **<Theme 3>**: <Cross-cutting insight>

### Recommended Approach

Based on research, the recommended approach is:
<2-3 sentences summarizing the path forward>

### Trade-offs to Consider

- <Major trade-off 1>
- <Major trade-off 2>

### Open Questions

- <Question that couldn't be fully answered>
- <Area needing further investigation during implementation>

### Artifacts Created

- oak/plan/<plan-name>/research/<topic-1>.md
- oak/plan/<plan-name>/research/<topic-2>.md
- ...

### Next Steps

1. Review research findings
2. Generate tasks: /oak.plan-tasks <plan-name>
```

**Command ends here.** The user should review findings before task generation.

## Research Quality Guidelines

**Good Research:**
- Answers the specific questions defined for the topic
- Provides actionable recommendations
- Acknowledges trade-offs and limitations
- Cites sources for key claims
- Connects findings to plan objectives

**Avoid:**
- Generic information not specific to the context
- Unsourced claims for important decisions
- Ignoring trade-offs or presenting one-sided views
- Duplicating information across topic files
- Research rabbit holes that don't serve plan goals

## Notes

- **Research depth**: Match depth to topic priority and plan needs
- **Time-boxing**: Don't over-research low-priority topics
- **Living documents**: Findings can be updated as understanding evolves
- **Constitution alignment**: Ensure recommendations align with project standards
- **Graceful degradation**: If web search isn't available, document assumptions clearly
- **{{ research_strategy }}**: Agent-specific research guidance is incorporated above
