# UniFi Network Rules Engineering Constitution

## Metadata

- **Project:** UniFi Network Rules
- **Version:** 1.0.0
- **Status:** Ratified
- **Ratification Date:** 2025-12-28
- **Last Amendment:** N/A
- **Author:** Chris Kirby (@sirkirby)
- **Tech Stack:** Python 3.13, Home Assistant Core, aiounifi, asyncio/aiohttp, pytest

**Description:** Custom integration for Home Assistant that integrates with your UniFi Dream Machine/Router to provide and help create useful interactions and automations for your Home Lab

---

## Principles

### P1: Code Quality

**Requirements:**
- All code MUST pass automated quality checks before merge
- Code coverage target is 60% (advisory)
- Code reviews SHOULD be conducted for non-trivial changes
**Rationale:**
Maintaining high code quality reduces technical debt, improves maintainability, and prevents production incidents. Quality gates ensure consistent standards across the codebase.
### P2: Testing

**Requirements:**
- All new features MUST include unit tests
- Integration tests MUST cover critical user paths
- E2E tests are recommended for key workflows
- Flaky tests MUST be fixed or removed within 48 hours
- Test data MUST be isolated from production

**Rationale:**
Balanced testing ensures reliability while maintaining development velocity. Flaky tests erode confidence and must be addressed promptly.
### P3: Documentation

**Requirements:**
- All public APIs MUST be documented
- Architecture decisions SHOULD be recorded in ADRs
- README MUST be kept up-to-date with setup instructions
- Complex logic MUST include inline comments
**Rationale:**
Good documentation accelerates onboarding, reduces knowledge silos, and ensures institutional knowledge is preserved.
---

## Architecture

### System Design

**Requirements:**
- Services MUST be loosely coupled
- APIs MUST follow RESTful principles where applicable
- Data models MUST use strong typing
- Shared dependencies MUST be minimized

**Rationale:**
Loose coupling enables independent development and deployment. Strong typing catches errors at compile time rather than runtime.

### Project Architecture Patterns

This project follows Home Assistant integration conventions with additional patterns for scalability:

**Required Patterns:**

1. **Coordinator Pattern** - Centralized data fetching and state management via `coordination/` module
2. **UDM API Layer** - Domain-specific API handlers in `udm/` (firewall, nat, routes, vpn, oon, etc.)
3. **Base Switch Abstraction** - `switches/base.py` with specialized implementations per feature domain
4. **Typed Models Layer** - All API response data MUST have typed models in `models/`
5. **Grouped Services Layer** - Action handlers organized in `services/` (backup, cleanup, rules, system, template)

**Structural Requirements:**

- **Modular File Organization** - Avoid monolithic files. Split functionality into module directories
  - BAD: `coordinator.py` with 1000+ lines
  - GOOD: `coordination/` directory with `coordinator.py`, `state_manager.py`, `data_fetcher.py`, etc.
- New features MUST follow the established module structure
- Each module directory MUST have an `__init__.py` that exports public interfaces

**Home Assistant Integration Requirements:**

- Prioritize native Home Assistant libraries (aiounifi) over custom implementations
- Follow Home Assistant entity patterns for switches, sensors, etc.
- Use Home Assistant's built-in coordinator patterns for data refresh
- Diagnostics SHOULD be targeted and resource-conscious

### Technology Stack

**Primary Technologies:**
- Python 3.13, Home Assistant Core, aiounifi, asyncio/aiohttp, pytest

**Requirements:**
- New dependencies MUST be reviewed by the team
- Deprecated technologies MUST be upgraded within 6 months
- Security patches MUST be applied within 2 weeks of disclosure
- Technology choices MUST consider long-term maintainability

**Rationale:**
Careful dependency management prevents security vulnerabilities and technical debt. Regular updates ensure we benefit from bug fixes and performance improvements.

---

## Code Standards

### Project Principles

**Core Development Principles:**

- **KISS** - Prefer simple, elegant solutions over complex ones
- **DRY** - Keep code testable with clear separation of concerns
- **Single Responsibility** - Functions and classes do one thing well
- **Root Cause Fixes** - Fix underlying problems, not symptoms
- **Minimal Comments** - Code SHOULD be self-documenting; use comments only where logic isn't self-evident

### Style Guide

**Requirements:**
- Code MUST follow PEP 8 style guidelines
- Type hints MUST be used throughout
- Linting MUST pass in CI/CD pipeline (Ruff)
- Style violations MUST be addressed before merge
- Formatting MUST be automated with tools

**Rationale:**
Consistent code style improves readability and reduces cognitive load when reviewing code.

### Naming Conventions

**Requirements:**
- Names MUST be descriptive and unambiguous
- Abbreviations MUST be avoided unless standard
- Constants MUST use UPPER_SNAKE_CASE
- Functions and variables MUST use language conventions

**Rationale:**
Clear naming makes code self-documenting and reduces the need for comments.

### Error Handling

**Requirements:**
- All errors MUST be caught and logged appropriately
- User-facing errors MUST be actionable and clear
- Critical errors MUST trigger monitoring alerts
- Error messages MUST NOT expose sensitive information

**Rationale:**
Proper error handling ensures system reliability and helps with debugging production issues.

---

## Testing

### Testing Philosophy

This project follows a **balanced testing approach** with moderate coverage and selective integration testing.

### Unit Testing

**Requirements:**
- New functions MUST have unit tests for core logic
- Tests MAY be written after implementation
- Tests MUST be deterministic and repeatable
- Tests MUST run in under 5 seconds per test
- Mocks MUST be used for external dependencies

**Rationale:**
Fast, reliable unit tests enable rapid development cycles and give immediate feedback on code changes.

### Integration Testing

**Requirements:**
- Critical user paths MUST have integration tests
- Tests MUST use test fixtures, not production data
- Tests MUST clean up resources after execution
- Integration tests SHOULD run in CI/CD
**Rationale:**
Integration tests catch issues that unit tests miss by verifying component interactions.

### End-to-End Testing

**Recommendations:**
- Consider E2E tests for critical user journeys
- E2E tests MAY be implemented for high-risk workflows
- Use dedicated test environments when running E2E tests

**Rationale:**
E2E tests are valuable for critical paths but optional given project constraints.

### Coverage Requirements

**Target:** 60% code coverage for new code

**Enforcement:** Coverage is monitored but does not block merges. Teams SHOULD maintain 60% coverage as a guideline.
**Rationale:**
Balanced approach with 60% coverage guideline. TDD strongly recommended for critical functionality but not mandated.
---

## Documentation

### Documentation Philosophy

This project maintains **standard documentation** focusing on public interfaces and complex logic.

### Code Documentation

**Requirements:**
- All public functions MUST have docstrings
- Complex algorithms MUST have explanatory comments
- Public classes MUST have docstrings
- Internal functions SHOULD have docstrings where complexity warrants
- Docstrings MUST follow google style
- Type hints MUST be used where supported
- Documentation MUST be kept in sync with code

**Rationale:**
Well-documented code is easier to maintain and reduces onboarding time for new team members.

### Project Documentation

**Requirements:**
- README MUST include setup and development instructions
- CONTRIBUTING guide SHOULD explain development workflow
- CHANGELOG SHOULD track releases and major changes
- Documentation MUST be versioned with code

**Rationale:**
Project documentation ensures contributors understand the development workflow and project standards.
### Architecture Documentation

**Requirements:**
- Major architectural decisions SHOULD have ADRs
- Key system diagrams SHOULD be maintained
- API contracts SHOULD be documented
**Rationale:**
Architecture documentation helps developers understand key design decisions without requiring exhaustive detail.
---

## Governance

### Code Review Policy

This project follows a **flexible code review policy** emphasizing collaboration over enforcement.

**Requirements:**
- Code reviews SHOULD be conducted for non-trivial changes
- Team members MAY merge without formal approval for simple changes
- Complex changes SHOULD be reviewed by at least one other team member
- Reviews are encouraged for knowledge sharing and quality improvement

**Rationale:**
Flexible review trusts team judgment while encouraging collaboration and knowledge sharing.

### Amendment Process

**To amend this constitution:**

1. **Proposal:** Submit amendment via `/oak.constitution-amend` with summary and rationale
2. **Review:** Team reviews and discusses the proposed amendment
3. **Approval:** Amendment requires team consensus or majority vote
4. **Recording:** Amendment is added to this document with incremented version

**Amendment Types:**
- **Major (X.0.0):** Breaking changes that invalidate existing requirements
- **Minor (0.X.0):** New requirements added without breaking existing ones
- **Patch (0.0.X):** Clarifications or corrections to existing requirements

### Versioning

This constitution follows semantic versioning:
- **MAJOR** version for breaking changes to existing requirements
- **MINOR** version for new requirements that don't break existing ones
- **PATCH** version for clarifications that don't change meaning

### Review Cadence

This constitution MUST be reviewed:
- **Quarterly** for continued relevance and applicability
- **After major incidents** to identify process improvements
- **When team composition changes** significantly
- **Before major architectural changes**

**Rationale:**
Regular reviews ensure the constitution evolves with the team and project needs.

### Compliance

**Requirements:**
- All team members MUST be familiar with this constitution
- New team members MUST review constitution during onboarding
- Constitution violations MUST be addressed constructively
- Repeated violations MUST be discussed with team lead

**Rationale:**
Compliance ensures the constitution serves its purpose of maintaining quality and consistency.

---

*This constitution was ratified on 2025-12-28 and represents the team's commitment to engineering excellence.*
