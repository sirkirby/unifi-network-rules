## Constitution Alignment

Read the project constitution and identify rules relevant to this work:

```bash
# Read the full constitution
cat oak/constitution.md

# Or search for specific guidance
rg "MUST" oak/constitution.md
rg "SHOULD" oak/constitution.md
rg "testing" oak/constitution.md -i
rg "documentation" oak/constitution.md -i
```

**Extract and apply:**
- **Code Standards**: Type hints, docstrings, naming conventions, formatting rules
- **Testing Requirements**: Coverage expectations, test patterns, test organization
- **Documentation Standards**: What requires docs, format guidelines, examples
- **Review Protocols**: Approval requirements, validation steps, merge criteria

**Update plan.md** to explicitly reference applicable constitution rules in your approach section.

### Constitution Compliance Check & Test Strategy Extraction

Create a Constitution Check section in your plan analysis:

**Load constitution rules:**
```bash
# Extract MUST rules
rg "MUST" oak/constitution.md

# Extract SHOULD rules
rg "SHOULD" oak/constitution.md

# Find relevant sections
rg "testing|documentation|code standards" oak/constitution.md -i

# Extract test strategy specifically
rg "test.*first|TDD|coverage|unit.*test|integration.*test" oak/constitution.md -i
```

**Extract test strategy from constitution:**
- **Test timing**: Does constitution require test-first (TDD) or allow test-after?
- **Coverage requirements**: What coverage % is required? Are there exemptions?
- **Test organization**: Where do tests live? What naming conventions?
- **Test types**: Are unit tests required? Integration tests? E2E tests?
- **Flexibility**: Is testing strictly required or recommended/optional?

**Check compliance:**
- ✅ **PASS**: Implementation approach follows all MUST rules
- ⚠️ **NEEDS ATTENTION**: SHOULD rule requires consideration
- ❌ **VIOLATION**: MUST rule cannot be met (requires justification)

**Document in plan.md:**
```markdown
## Constitution Compliance

### Test Strategy (from constitution)
- **Timing**: Test-after allowed (not strict TDD)
- **Coverage**: 80% minimum required for new code
- **Required**: Unit tests for all public functions
- **Optional**: Integration tests recommended for workflows
- **Organization**: Tests mirror src/ structure in tests/

### MUST Rules
- ✅ All public functions have type hints (constitution Section 4.1)
- ✅ Tests required for new functionality (constitution Section 7.1)
- ✅ No magic strings - use constants (constitution Section 4.4)

### SHOULD Rules
- ⚠️ Consider extracting helper to shared utilities (constitution Section 4.2)
  - Approach: Will add to existing utils module per constitution pattern

### Violations (if any)
- ❌ None - all MUST rules satisfied
```

**Use test strategy for task planning**: Apply the constitution's test requirements when creating testing tasks. If constitution is strict, make all tests explicit. If flexible, suggest optional tests.
