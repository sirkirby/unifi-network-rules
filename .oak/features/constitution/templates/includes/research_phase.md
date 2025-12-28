## Research Phase (Capability-Aware)

**Before presenting decision options, conduct research on technologies and patterns mentioned by the user.**

This step ensures the constitution reflects current best practices rather than outdated or generic patterns.

### Research Trigger Detection

Scan user input (project description, tech stack, $ARGUMENTS) for research-worthy topics.

**Reference:** `features/constitution/templates/decision_points.yaml` section `research_triggers` contains comprehensive regex patterns for:
- Language/runtime versions (Python, TypeScript, Node, Java, Go, Rust, C#, .NET)
- Frameworks (FastAPI, Django, Next.js, Spring Boot, ASP.NET Core, etc.)
- CLI frameworks (Ink, Commander, Click/Typer, Cobra)
- Architecture patterns (vertical slice, hexagonal, clean, DDD, CQRS, microservices)
- Testing frameworks (pytest, Jest, Vitest, Playwright, xUnit, NUnit)
- Industry/compliance (fintech, healthcare, GDPR)

Use your judgment to identify which triggers are relevant for this project.

{% if has_native_web %}

### Web Search Available

You have built-in web search capabilities. For each research topic:

1. Search for current best practices: "[technology] best practices 2025"
2. Synthesize findings into 3-5 actionable patterns per topic
3. Present findings to user BEFORE relevant decision points
4. Document sources for traceability

{% elif has_mcp %}

### MCP Web Search Available

Use your configured MCP web-search server. {{ research_strategy }}

For each research topic:

1. Query MCP web-search with: "[topic] best practices 2025"
2. Synthesize top results into actionable patterns
3. Present findings before relevant decisions

{% else %}

### Limited Research Mode

No web search available. When encountering unfamiliar patterns:

1. Use your training knowledge but note the knowledge cutoff
2. Ask the user for clarification on specific patterns
3. Flag any patterns you're uncertain about in the final report

{% endif %}

### Research Presentation

Present research findings BEFORE each relevant decision point:

```text
RESEARCH FINDINGS: [Topic]

Based on current best practices:

1. **[Pattern Name]**: [Description, when to use]
2. **[Pattern Name]**: [Description, when to use]
3. **[Pattern Name]**: [Description, when to use]

How this affects your decisions:
- Testing: [implication]
- Architecture: [implication]
```
