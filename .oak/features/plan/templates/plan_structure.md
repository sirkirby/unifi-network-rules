## Create Detailed Implementation Plan

Open and edit `oak/plan/<name>/plan.md` to fill in the details:

### A. Plan Sections (Standard)

- **Objectives**: Refined based on requirements (acceptance criteria if from issue, clarifying answers if from idea)
- **Constitution Check**: Document compliance with MUST/SHOULD rules
- **Technical Context**:
  - Technologies/libraries to use
  - Integration points
  - **All NEEDS CLARIFICATION resolved**
- **Approach**:
  - Which patterns you'll follow (reference specific files)
  - Where new code will live (module, class, function names)
  - How you'll handle edge cases
  - Constitution rules you're applying

### B. Task Breakdown (Structured Phases)

Use this phased structure (adjust based on constitution's test strategy):

**Phase 1: Setup & Investigation**
```markdown
- [ ] Setup: Review context (parent issue, related items, or clarifying answers)
- [ ] Setup: Identify affected modules/files from codebase exploration
- [ ] Setup: Install/configure any new dependencies per constitution
- [ ] Setup: Create feature branch (already done by CLI)
```

**Phase 2: Core Implementation**
```markdown
# Map to acceptance criteria (from issue) or goals (from idea)
- [ ] Implement: [Requirement 1]
  - File: [specific file path]
  - Function/Class: [specific names]
  - Pattern: [reference to similar implementation]
- [ ] Implement: [Requirement 2]
  - File: [specific file path]
  - Function/Class: [specific names]
  - Pattern: [reference to similar implementation]
# Continue for all requirements
```

**Phase 3: Testing** (constitution-driven)
```markdown
# Test phase structure depends on constitution guidance:
# - If constitution requires test-first (TDD): Phase 3 becomes Phase 2
# - If constitution requires high coverage: Create explicit tasks for each test scenario
# - If constitution is flexible: Make testing optional but recommended

# If issue includes test cases, convert them to tasks:
- [ ] Test: [Test case title]
  - Test file: [specific test file path per constitution structure]
  - Test function: test_[specific_name]
  - Covers: [requirement reference]

# If constitution requires comprehensive testing, add:
- [ ] Test: Unit tests for [component] (per constitution coverage requirements)
- [ ] Test: Integration tests for [workflow] (if required by constitution)
- [ ] Test: Edge case handling for [scenario]

# If constitution is flexible on testing, make it optional:
- [ ] (Optional) Test: Consider adding tests for [critical paths]
```

**Phase 4: Integration**
```markdown
# Consider integration with related systems/issues
- [ ] Integration: Connect with [related component]
- [ ] Integration: Verify compatibility with [system component]
- [ ] Integration: Test end-to-end workflow
```

**Phase 5: Polish & Documentation**
```markdown
- [ ] Documentation: Update [specific files per constitution]
- [ ] Documentation: Add inline code comments for complex logic
- [ ] Documentation: Update API docs (if applicable)
- [ ] Quality: Run linters and formatters per constitution
- [ ] Quality: Verify constitution compliance (all MUST rules)
- [ ] Quality: Review against definition of done
```

### Task Guidelines

- **Be specific**: "Add user_id validation to IssueService.validate_provider()" not "Add validation"
- **Reference files**: Always include actual file paths and function/class names
- **Map to requirements**: Each requirement should have at least one implementation task
- **Leverage test cases**: If issue includes test cases, create corresponding test tasks
- **Constitution-driven testing**:
  - Read constitution's test strategy (TDD vs test-after, coverage requirements, test organization)
  - Adjust phase order if constitution requires test-first approach
  - Make testing explicit if constitution has strict requirements, optional if flexible
- **Constitution alignment**: Reference specific constitution rules in relevant tasks

### C. Additional Plan Sections

- **Testing Strategy** (constitution-driven):
  - **Constitution requirements**: Document what the constitution mandates (TDD, coverage %, test organization)
  - **Test timing**: Test-first (TDD) or test-after (per constitution guidance)
  - **Unit tests**: Specific test files and functions to write (if required/recommended)
  - **Integration tests**: Specific scenarios to test (if required/recommended)
  - **Test fixtures**: Reference existing patterns found in codebase exploration
  - **Expected coverage**: Per constitution requirements (or recommend % if flexible)
  - **Optional tests**: If constitution is flexible, suggest additional valuable tests
- **Risks & Mitigations**: Technical blockers and solutions
- **Definition of Done**:
  - ✅ All requirements met
  - ✅ Tests written and passing (per constitution coverage)
  - ✅ Documentation updated (per constitution standards)
  - ✅ Constitution standards followed (all MUST rules)
  - ✅ Code reviewed (if required by constitution)
