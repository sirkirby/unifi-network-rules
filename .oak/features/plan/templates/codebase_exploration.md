## Systematic Codebase Exploration

**Step 1: Find Similar Features**

```bash
# Search for related functionality
rg "keyword_from_plan" src/
rg "class.*Service" src/           # If implementing a service
rg "class.*Command" src/commands/  # If implementing a command
rg "def test_" tests/               # Find test patterns
```

**Step 2: Identify Patterns**
- Look at 2-3 similar implementations
- Note common patterns: error handling, logging, validation, type hints
- Check how they're tested (unit tests, integration tests, fixtures)
- Review recent changes: `git log -p --since="1 month ago" path/to/relevant/`
- Check imports and dependencies used by similar code

**Step 3: Understand Testing Strategy**

```bash
# Find test files for similar features
find tests/ -name "*similar_feature*"

# See how services are tested
rg "class Test.*Service" tests/

# Check test fixtures and mocking patterns
rg "@pytest.fixture" tests/
rg "Mock" tests/
```

**Step 4: Document Findings**
- Update `plan.md` with patterns you found
- Note file/module naming conventions
- Document test strategy (where tests go, what patterns to follow)
- Reference specific files/functions as examples

### Identify Unknowns and Questions

Before creating the detailed plan, identify what you don't know yet:

- **Technical unknowns**: Libraries, APIs, or technologies you need to research
- **Integration questions**: How does this connect with existing systems?
- **Pattern questions**: Which approach best fits the codebase?
- **Constitution gaps**: Are there constitution rules that need clarification?

**For each unknown:**
- Mark it as **NEEDS CLARIFICATION** in your notes
- Ask the user directly if it's something they can answer
- Document what research is needed if it requires investigation

**Examples:**
```text
NEEDS CLARIFICATION: Which authentication library is used for API calls?
→ Ask user or search codebase: rg "auth" src/

NEEDS CLARIFICATION: Should validation use Pydantic or custom validators?
→ Check existing patterns: rg "BaseModel" src/

NEEDS CLARIFICATION: Where do shared utilities live?
→ Constitution says "centralized utilities" - check constitution for path
```

**Resolve before proceeding**: Don't write the full plan until all NEEDS CLARIFICATION items are resolved.
