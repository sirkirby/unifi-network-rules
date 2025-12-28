# {{ project_name }} Engineering Constitution

## Metadata

- **Project:** {{ project_name }}
- **Version:** {{ version }}
- **Status:** Ratified
- **Ratification Date:** {{ ratification_date }}
- **Last Amendment:** N/A
- **Author:** {{ author }}
{% if tech_stack -%}
- **Tech Stack:** {{ tech_stack }}
{% endif -%}

{% if description -%}
**Description:** {{ description }}
{% endif %}

---

## Principles

### P1: Code Quality

**Requirements:**
{% if ci_enforcement in ["full", "standard"] -%}
- All code MUST pass automated quality checks before merge
{% elif ci_enforcement == "basic" -%}
- Code SHOULD pass automated quality checks before merge
{% else -%}
- Automated quality checks will be implemented as project matures
{% endif -%}
{% if coverage_target and coverage_strict -%}
- Code coverage MUST be maintained above {{ coverage_target }}%
{% elif coverage_target -%}
- Code coverage target is {{ coverage_target }}% (advisory)
{% endif -%}
{% if ci_enforcement == "full" -%}
- No critical security vulnerabilities SHALL be merged
{% endif -%}
{% if code_review_policy in ["strict", "standard"] -%}
- Code reviews MUST be completed by at least one other engineer
{% elif code_review_policy == "flexible" -%}
- Code reviews SHOULD be conducted for non-trivial changes
{% endif -%}

**Rationale:**
Maintaining high code quality reduces technical debt, improves maintainability, and prevents production incidents.{% if ci_enforcement in ["full", "standard"] %} Quality gates ensure consistent standards across the codebase.{% endif %}

### P2: Testing

**Requirements:**
{% if testing_strategy == "comprehensive" -%}
- All new features MUST include unit tests (written first in TDD approach)
- Integration tests MUST cover critical user paths
- E2E tests MUST cover key user flows
{% elif testing_strategy == "balanced" -%}
- All new features MUST include unit tests
- Integration tests MUST cover critical user paths
- E2E tests are recommended for key workflows
{% elif testing_strategy == "pragmatic" -%}
- Critical features MUST include unit tests
- Integration tests SHOULD cover critical paths
{% else -%}
- All new features MUST include unit tests
{% endif -%}
- Flaky tests MUST be fixed or removed within 48 hours
- Test data MUST be isolated from production

**Rationale:**
{% if testing_strategy == "comprehensive" -%}
Comprehensive testing with TDD ensures reliability, enables confident refactoring, and catches issues early in development.
{% elif testing_strategy == "balanced" -%}
Balanced testing ensures reliability while maintaining development velocity. Flaky tests erode confidence and must be addressed promptly.
{% elif testing_strategy == "pragmatic" -%}
Pragmatic testing focuses resources on critical paths while enabling rapid development. Flaky tests erode confidence and must be addressed promptly.
{% else -%}
Testing ensures reliability and enables confident refactoring. Flaky tests erode confidence in the test suite and must be addressed promptly.
{% endif -%}

### P3: Documentation

**Requirements:**
{% if documentation_level == "extensive" -%}
- All public APIs MUST be documented
- All modules MUST have documentation
- Architecture decisions MUST be recorded in ADRs
- README MUST be kept up-to-date with setup instructions
- Complex logic MUST include inline comments
{% elif documentation_level == "standard" -%}
- All public APIs MUST be documented
- Architecture decisions SHOULD be recorded in ADRs
- README MUST be kept up-to-date with setup instructions
- Complex logic MUST include inline comments
{% elif documentation_level == "minimal" -%}
- Critical public APIs MUST be documented
- README MUST exist with basic setup instructions
- Complex logic SHOULD include inline comments
{% else -%}
- All public APIs MUST be documented
- README MUST be kept up-to-date with setup instructions
{% endif -%}

**Rationale:**
{% if documentation_level == "extensive" -%}
Comprehensive documentation accelerates onboarding, reduces knowledge silos, ensures institutional knowledge is preserved, and supports long-term maintainability.
{% elif documentation_level == "standard" -%}
Good documentation accelerates onboarding, reduces knowledge silos, and ensures institutional knowledge is preserved.
{% else -%}
Essential documentation helps new developers get started quickly without overwhelming them with details.
{% endif -%}

---

## Architecture

{% if architectural_pattern == "vertical_slice" -%}
### Architectural Pattern: Vertical Slice Architecture

This project follows **Vertical Slice Architecture**, organizing code by features rather than technical layers.

**Core Principles:**
- Features are self-contained vertical slices
- Each slice contains all layers it needs (UI, business logic, data access)
- Minimal coupling between slices
- Easy to understand and modify feature scope

**Requirements:**
{% if feature_organization -%}
- Features MUST be organized in: `{{ feature_organization }}`
{% else -%}
- Features MUST be organized by feature/use-case
{% endif -%}
- Each feature MUST be independently testable
- Cross-feature dependencies MUST be explicit and minimized
- Shared code MUST be justified and well-documented
{% if dependency_injection -%}
- Dependency injection MUST be used for feature dependencies
{% endif -%}
{% if domain_events -%}
- Domain events MUST be used for cross-feature communication
{% endif -%}

**Rationale:**
{{ architectural_rationale if architectural_rationale else "Vertical slices enable rapid feature development with minimal coupling between features" }}

{% elif architectural_pattern == "clean_architecture" -%}
### Architectural Pattern: Clean Architecture

This project follows **Clean Architecture** (Onion/Hexagonal Architecture) with business logic at the center.

**Core Principles:**
- Core business logic has no external dependencies
- Dependencies point inward toward the domain
- External concerns (UI, DB, APIs) are implementation details
- Business rules are testable in isolation

**Requirements:**
{% if layer_organization -%}
- Code MUST be organized in layers: {{ layer_organization }}
{% else -%}
- Code MUST be organized in layers: domain, application, infrastructure, presentation
{% endif -%}
- Domain layer MUST NOT depend on infrastructure or presentation
- Application layer MUST define interfaces for infrastructure
- Infrastructure layer MUST implement domain/application interfaces
{% if dependency_injection -%}
- Dependency injection MUST be used to wire layers
{% endif -%}
- Use cases/Application services MUST orchestrate business logic
- Domain entities MUST encapsulate business rules
{% if domain_events -%}
- Domain events MUST be used for decoupling within the domain
{% endif -%}

**Rationale:**
{{ architectural_rationale if architectural_rationale else "Clean Architecture ensures business logic remains independent and testable, enabling long-term maintainability" }}

{% elif architectural_pattern == "layered" -%}
### Architectural Pattern: Layered Architecture

This project follows **Traditional Layered Architecture** with horizontal separation by technical concern.

**Core Principles:**
- Horizontal separation: Presentation → Business → Data access
- Each layer depends only on the layer below
- Clear separation of technical responsibilities
- Well-established patterns for enterprise applications

**Requirements:**
{% if layer_organization -%}
- Code MUST be organized in layers: {{ layer_organization }}
{% else -%}
- Code MUST be organized in layers: presentation, business, data access
{% endif -%}
- Presentation layer handles UI concerns only
- Business layer contains all business logic
- Data access layer handles all database operations
- Layers MUST NOT skip dependencies (e.g., presentation to data directly)
- DTOs MUST be used for cross-layer communication where needed

**Rationale:**
{{ architectural_rationale if architectural_rationale else "Layered architecture provides clear separation of concerns and is well-understood by enterprise development teams" }}

{% elif architectural_pattern == "modular_monolith" -%}
### Architectural Pattern: Modular Monolith

This project follows **Modular Monolith Architecture** with strong module boundaries in a single deployment.

**Core Principles:**
- Modules are independently developable units
- Clear module interfaces and contracts
- Shared database but isolated schemas/tables per module
- Path to eventual microservices if needed

**Requirements:**
{% if feature_organization -%}
- Modules MUST be organized in: `{{ feature_organization }}`
{% else -%}
- Modules MUST be organized with clear boundaries
{% endif -%}
- Each module MUST have a well-defined public API
- Modules MUST communicate through public interfaces only
- Direct database access across modules is PROHIBITED
{% if domain_events -%}
- Domain events MUST be used for inter-module communication
{% endif -%}
{% if dependency_injection -%}
- Module dependencies MUST be declared explicitly via DI
{% endif -%}
- Shared kernel (cross-cutting concerns) MUST be minimal and justified

**Rationale:**
{{ architectural_rationale if architectural_rationale else "Modular monolith provides microservices-like benefits without operational complexity, enabling future extraction if needed" }}

{% elif architectural_pattern == "pragmatic" -%}
### Architectural Pattern: Pragmatic / Adaptive

This project follows a **Pragmatic approach**, adapting architectural patterns based on context.

**Core Principles:**
- Use patterns where they add value
- Keep simple features simple
- Apply sophisticated patterns for complex domains
- Architecture emerges from actual needs, not dogma

**Requirements:**
- Code organization MUST be clear and consistent within each area
- Complex features MAY use domain-driven patterns
- Simple CRUD features MAY use straightforward implementations
- Architectural decisions MUST be documented when they deviate from norms
- Team MUST agree on when to apply which patterns

**Rationale:**
{{ architectural_rationale if architectural_rationale else "Pragmatic architecture balances best practices with development velocity, avoiding over-engineering while maintaining quality" }}

{% else -%}
### System Design

**Requirements:**
- Services MUST be loosely coupled
- APIs MUST follow RESTful principles where applicable
- Data models MUST use strong typing
- Shared dependencies MUST be minimized

**Rationale:**
Loose coupling enables independent development and deployment. Strong typing catches errors at compile time rather than runtime.

{% endif -%}

{% if error_handling_pattern -%}
### Error Handling Pattern

{% if error_handling_pattern == "result_pattern" -%}
This project uses the **Result Pattern** for explicit error handling.

**Requirements:**
- Domain operations MUST return `Result<T, Error>` types
- Success and failure cases MUST be explicit in return types
- Exceptions SHOULD be reserved for truly exceptional conditions
- Result types MUST be handled explicitly (no ignoring errors)
- Error types MUST be descriptive and actionable

**Rationale:**
Result pattern makes errors visible in the type system, forcing explicit handling and preventing forgotten error cases.

{% elif error_handling_pattern == "exceptions" -%}
This project uses **exception-based error handling**.

**Requirements:**
- Exceptions MUST be used for error conditions
- Custom exception types MUST be defined for domain errors
- Exception messages MUST be clear and actionable
- Exceptions MUST be caught at appropriate boundaries
- Error logging MUST capture context and stack traces

**Rationale:**
Exception-based handling is well-understood and supported by language ecosystems.

{% elif error_handling_pattern == "mixed" -%}
This project uses a **mixed approach** to error handling.

**Requirements:**
- Domain logic MUST use Result Pattern for expected errors
- Infrastructure failures MAY use exceptions
- Result types MUST be converted to exceptions at API boundaries if needed
- Both error patterns MUST be documented where used
- Team MUST agree on when to use each pattern

**Rationale:**
Mixed approach leverages Result Pattern benefits for domain logic while allowing exceptions for infrastructure concerns.

{% endif -%}
{% endif -%}

{% if coding_principles -%}
### Coding Principles

This project adheres to these core principles:

{% for principle in coding_principles -%}
- **{{ principle }}**: Apply this principle consistently across the codebase
{% endfor -%}

**Rationale:**
These principles guide decision-making and ensure consistent, maintainable code.

{% endif -%}

### Technology Stack

**Primary Technologies:**
{% if tech_stack -%}
- {{ tech_stack }}
{% else -%}
- To be defined based on project needs
{% endif %}

**Requirements:**
- New dependencies MUST be reviewed by the team
- Deprecated technologies MUST be upgraded within 6 months
- Security patches MUST be applied within 2 weeks of disclosure
- Technology choices MUST consider long-term maintainability

**Rationale:**
Careful dependency management prevents security vulnerabilities and technical debt. Regular updates ensure we benefit from bug fixes and performance improvements.

---

## Code Standards

### Style Guide

**Requirements:**
- Code MUST follow language-specific style guides
{% if ci_enforcement in ["full", "standard"] -%}
- Linting MUST pass in CI/CD pipeline
- Style violations MUST be addressed before merge
{% elif ci_enforcement == "basic" -%}
- Linting SHOULD pass before merge
- Style violations SHOULD be addressed
{% else -%}
- Linting is encouraged but not yet enforced
{% endif -%}
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

{% if testing_strategy == "comprehensive" -%}
### Testing Philosophy

This project follows a **comprehensive testing approach** with test-driven development and high coverage requirements.

{% elif testing_strategy == "balanced" -%}
### Testing Philosophy

This project follows a **balanced testing approach** with moderate coverage and selective integration testing.

{% elif testing_strategy == "pragmatic" -%}
### Testing Philosophy

This project follows a **pragmatic testing approach** focusing on essential tests for critical functionality.

{% endif -%}

### Unit Testing

**Requirements:**
{% if testing_strategy == "comprehensive" -%}
- All functions MUST have unit tests written before implementation (TDD)
- Each function MUST have unit tests for core logic and edge cases
{% elif testing_strategy == "balanced" -%}
- New functions MUST have unit tests for core logic
- Tests MAY be written after implementation
{% elif testing_strategy == "pragmatic" -%}
- Critical functions MUST have unit tests
- Helper functions SHOULD have tests where complexity warrants
{% else -%}
- Each function MUST have unit tests for core logic
{% endif -%}
- Tests MUST be deterministic and repeatable
- Tests MUST run in under 5 seconds per test
- Mocks MUST be used for external dependencies

**Rationale:**
Fast, reliable unit tests enable rapid development cycles and give immediate feedback on code changes.

{% if testing_strategy in ["comprehensive", "balanced"] -%}
### Integration Testing

**Requirements:**
{% if critical_integration_points -%}
- The following integration points MUST have integration tests: {{ critical_integration_points | join(", ") }}
{% else -%}
- Critical user paths MUST have integration tests
{% endif -%}
- Tests MUST use test fixtures, not production data
- Tests MUST clean up resources after execution
{% if testing_strategy == "comprehensive" -%}
- Integration tests MUST run in CI/CD
- Integration test failures MUST block merges
{% else -%}
- Integration tests SHOULD run in CI/CD
{% endif -%}

**Rationale:**
Integration tests catch issues that unit tests miss by verifying component interactions.

{% elif testing_strategy == "pragmatic" -%}
### Integration Testing

**Recommendations:**
- Consider integration tests for critical user paths
- Use test fixtures when testing integrations
- Run integration tests in CI/CD when feasible

**Rationale:**
While not required, integration tests can catch issues that unit tests miss by verifying component interactions.

{% endif -%}

{% if testing_strategy == "comprehensive" and has_e2e_infrastructure -%}
### End-to-End Testing

**Requirements:**
- Key user flows MUST be covered by E2E tests
{% if tdd_required -%}
- E2E tests SHOULD be written alongside feature development
{% endif -%}
- E2E tests MUST run before production deployment
- Test failures MUST block deployment
- E2E tests MUST use dedicated test environments

**Rationale:**
E2E tests verify the system works as a whole from the user's perspective.

{% elif testing_strategy == "comprehensive" and e2e_planned -%}
### End-to-End Testing

**Future Requirements** (when infrastructure is ready):
- Key user flows SHOULD be covered by E2E tests
- E2E tests SHOULD run before production deployment
- Dedicated test environments SHOULD be used

**Current Status:** E2E infrastructure is planned but not yet implemented.

**Rationale:**
E2E tests will verify the system works as a whole once infrastructure is in place.

{% elif testing_strategy == "balanced" -%}
### End-to-End Testing

**Recommendations:**
- Consider E2E tests for critical user journeys
- E2E tests MAY be implemented for high-risk workflows
- Use dedicated test environments when running E2E tests

**Rationale:**
E2E tests are valuable for critical paths but optional given project constraints.

{% endif -%}

### Coverage Requirements

{% if coverage_target -%}
**Target:** {{ coverage_target }}% code coverage for new code

{% if coverage_strict -%}
**Enforcement:** Coverage checks MUST pass in CI/CD. Pull requests that decrease coverage below {{ coverage_target }}% will be blocked.
{% else -%}
**Enforcement:** Coverage is monitored but does not block merges. Teams SHOULD maintain {{ coverage_target }}% coverage as a guideline.
{% endif -%}
{% else -%}
**Target:** Coverage goals are flexible and determined per-component. Focus on meaningful tests over percentage targets.

**Enforcement:** Coverage is tracked but not enforced via CI/CD.
{% endif -%}

**Rationale:**
{% if testing_rationale -%}
{{ testing_rationale }}
{% else -%}
Appropriate test coverage ensures reliability while balancing development velocity.
{% endif -%}

---

## Documentation

{% if documentation_level == "extensive" -%}
### Documentation Philosophy

This project maintains **extensive documentation** for all aspects of the system to support knowledge sharing and onboarding.

{% elif documentation_level == "standard" -%}
### Documentation Philosophy

This project maintains **standard documentation** focusing on public interfaces and complex logic.

{% elif documentation_level == "minimal" -%}
### Documentation Philosophy

This project maintains **minimal documentation** covering essential setup and critical functionality.

{% endif -%}

### Code Documentation

**Requirements:**
{% if documentation_level == "extensive" -%}
- All public functions MUST have docstrings
- All modules MUST have module-level docstrings
- All classes MUST have class-level docstrings
- Complex algorithms MUST have explanatory comments
- Internal helper functions SHOULD have docstrings
{% elif documentation_level == "standard" -%}
- All public functions MUST have docstrings
- Complex algorithms MUST have explanatory comments
- Public classes MUST have docstrings
- Internal functions SHOULD have docstrings where complexity warrants
{% elif documentation_level == "minimal" -%}
- Critical public functions MUST have docstrings
- Complex algorithms SHOULD have explanatory comments
- Documentation SHOULD focus on non-obvious behavior
{% endif -%}
{% if docstring_style -%}
- Docstrings MUST follow {{ docstring_style }} style
{% endif -%}
- Type hints MUST be used where supported
- Documentation MUST be kept in sync with code

**Rationale:**
Well-documented code is easier to maintain and reduces onboarding time for new team members.

### Project Documentation

**Requirements:**
- README MUST include setup and development instructions
{% if documentation_level == "extensive" -%}
- CONTRIBUTING guide MUST explain development workflow
- CHANGELOG MUST track all releases and major changes
- CODE_OF_CONDUCT SHOULD be included for collaborative projects
{% elif documentation_level == "standard" -%}
- CONTRIBUTING guide SHOULD explain development workflow
- CHANGELOG SHOULD track releases and major changes
{% elif documentation_level == "minimal" -%}
- Basic development instructions MUST be in README
{% endif -%}
- Documentation MUST be versioned with code

**Rationale:**
{% if documentation_level == "extensive" -%}
Comprehensive project documentation ensures anyone can contribute effectively and maintains institutional knowledge.
{% elif documentation_level == "standard" -%}
Project documentation ensures contributors understand the development workflow and project standards.
{% else -%}
Essential documentation helps developers get started quickly without overwhelming them with details.
{% endif -%}

### Architecture Documentation

**Requirements:**
{% if documentation_level == "extensive" or adr_required -%}
- Major architectural decisions MUST have ADRs
- System diagrams MUST be kept current
- API contracts MUST be versioned and documented
- Dependencies between services MUST be documented
{% elif documentation_level == "standard" -%}
- Major architectural decisions SHOULD have ADRs
- Key system diagrams SHOULD be maintained
- API contracts SHOULD be documented
{% elif documentation_level == "minimal" -%}
- Critical architectural decisions MAY be documented
- Documentation focus is on getting started, not comprehensive architecture
{% endif -%}

**Rationale:**
{% if documentation_level == "extensive" or adr_required -%}
Architecture documentation provides context for technical decisions and helps new team members understand system design.
{% elif documentation_level == "standard" -%}
Architecture documentation helps developers understand key design decisions without requiring exhaustive detail.
{% else -%}
Minimal architecture documentation allows focus on rapid development while documenting critical decisions.
{% endif -%}

---

## Governance

### Code Review Policy

{% if code_review_policy == "strict" -%}
This project follows a **strict code review policy** where all code must be reviewed before merging.

**Requirements:**
- All pull requests MUST be reviewed before merge
{% if num_reviewers -%}
- At least {{ num_reviewers }} approval(s) required before merge
{% else -%}
- At least 1 approval required before merge
{% endif -%}
{% if reviewer_qualifications -%}
- Reviewers MUST meet these qualifications: {{ reviewer_qualifications }}
{% endif -%}
- No direct commits to main/master branch
- Review checklist MUST be followed
- No exceptions for urgent fixes (hotfixes must be reviewed post-merge if deployed)

**Rationale:**
Strict review ensures code quality and knowledge sharing across the team. All code benefits from a second set of eyes.

{% elif code_review_policy == "standard" -%}
This project follows a **standard code review policy** with flexibility for urgent situations.

**Requirements:**
- Pull requests MUST be reviewed before merge
{% if num_reviewers -%}
- At least {{ num_reviewers }} approval(s) required
{% else -%}
- At least 1 approval required
{% endif -%}
{% if reviewer_qualifications -%}
- Reviewers SHOULD meet these qualifications: {{ reviewer_qualifications }}
{% endif -%}
- Direct commits to main allowed only for urgent hotfixes
{% if hotfix_definition -%}
- Hotfix definition: {{ hotfix_definition }}
{% else -%}
- Hotfixes are production-critical fixes that cannot wait for review
{% endif -%}
- Hotfixes MUST be reviewed retrospectively within 24 hours

**Rationale:**
Standard review balances code quality with operational flexibility for urgent production issues.

{% elif code_review_policy == "flexible" -%}
This project follows a **flexible code review policy** emphasizing collaboration over enforcement.

**Requirements:**
- Code reviews SHOULD be conducted for non-trivial changes
- Team members MAY merge without formal approval for simple changes
- Complex changes SHOULD be reviewed by at least one other team member
- Reviews are encouraged for knowledge sharing and quality improvement

**Rationale:**
Flexible review trusts team judgment while encouraging collaboration and knowledge sharing.

{% endif -%}

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

*This constitution was ratified on {{ ratification_date }} and represents the team's commitment to engineering excellence.*
