## Research Strategy (Capability-Aware)

{% if has_native_web %}
### Web Research Available

You have access to **web search capabilities**. Use them proactively to:
- Gather current documentation and best practices
- Research unfamiliar technologies or patterns
- Validate architectural decisions with industry standards
- Find examples and reference implementations

**When to research:**
- New libraries, frameworks, or APIs mentioned in requirements
- Architectural patterns you haven't used before
- Integration approaches with external services
- Security best practices for sensitive operations
{% else %}
### Limited Research Mode

This agent may not have native web search capabilities. During research, focus on:
- Codebase exploration for existing patterns
- General knowledge for established best practices
{% if has_mcp %}
- MCP tools if web search servers are available
{% endif %}

**When you encounter unfamiliar patterns:**
- Search the codebase for similar implementations
- Ask the user for guidance or documentation
- Note gaps in your notes for follow-up
{% endif %}

{% if has_mcp %}
### MCP-Enhanced Research

Leverage MCP tools for richer research:
- **Web search tools**: Find documentation and best practices
- **Document fetch**: Retrieve linked specifications or references
- **Code search tools**: Find patterns across the codebase
{% endif %}

{% if has_background_agents %}
### Parallel Research with Background Agents

For plans with multiple research topics, consider parallelizing:

**Research Agent Template:**
```markdown
# Research Assignment: <topic>

## Context
- **Plan:** <plan-name>
- **Priority:** <1-5>

## Research Questions
1. <Question 1>
2. <Question 2>

## Sources to Check
- <Source 1>
- <Source 2>

## Deliverables
Create `oak/plan/<name>/research/<topic-slug>.md` with:
- Summary of findings
- Recommended approach
- Key decisions to make
- Links/references
```

**Benefits:**
- Faster research for complex plans
- Parallel investigation of competing approaches
- Comprehensive coverage of research topics
{% endif %}
