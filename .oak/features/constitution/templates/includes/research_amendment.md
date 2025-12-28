## Research Phase for Pattern-Based Amendments (Capability-Aware)

**If the amendment introduces new patterns, technologies, or architectural changes, conduct research before proceeding.**

### When to Trigger Research

Scan the amendment summary and rationale for research-worthy topics.

**Reference:** `features/constitution/templates/decision_points.yaml` section `research_triggers` contains comprehensive patterns for detecting when research is valuable (architecture, frameworks, language versions, compliance).

{% if has_native_web %}

### Web Search Available

For pattern-introducing amendments:

1. Search for current best practices: "[pattern] best practices 2025"
2. Synthesize 3-5 key requirements the amendment should address
3. Present findings before finalizing amendment language

{% elif has_mcp %}

### MCP Web Search Available

Use your configured MCP web-search server. {{ research_strategy }}

For pattern-introducing amendments, query for best practices and present findings before finalizing.

{% else %}

### Limited Research Mode

When the amendment introduces patterns you're uncertain about:

1. Flag the uncertainty and ask the user for resources/docs they're following
2. Confirm the specific requirements they want to codify
3. Note any knowledge limitations in the final report

{% endif %}

### Skip Research When

- Amendment is clarifying existing language (patch)
- Amendment adjusts thresholds (e.g., coverage 70% -> 75%)
- Amendment removes outdated requirements
- User explicitly states they don't need research
