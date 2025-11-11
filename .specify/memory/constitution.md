<!--
Sync Impact Report:
Version: 1.0.0 (initial creation)
Ratification Date: TODO(ratification_date): Unknown - project is established but constitution creation date unknown
Last Amended: 2025-11-11

Modified Principles: N/A (initial creation)
Added Sections:
- Core Principles (12 principles)
- Code Quality Standards
- Development Workflow
- Testing Requirements
- Documentation Standards

Removed Sections: N/A (initial creation)

Templates Requiring Updates:
- ✅ plan-template.md (Constitution Check section exists, aligns with principles)
- ✅ spec-template.md (no constitution-specific references)
- ✅ tasks-template.md (no constitution-specific references)
- ✅ checklist-template.md (no constitution-specific references)

Follow-up TODOs:
- TODO(ratification_date): Determine original project ratification date if available
-->

# UniFi Network Rules Constitution

## Core Principles

### I. DRY & Testability (NON-NEGOTIABLE)
Code MUST follow DRY (Don't Repeat Yourself) principles for testability and separation of concerns. Functions and classes MUST have single responsibility. Duplicate code MUST be refactored into reusable components. This ensures maintainability, reduces bugs, and enables comprehensive testing.

### II. Native Library Prioritization
MUST prioritize native Home Assistant libraries, especially `aiounifi`, and other core Home Assistant capabilities to respect available resources and avoid building duplicate functionality. MUST leverage the latest Home Assistant documentation. If a reference to the `aiounifi` library is needed, check for a local copy in the root `/aiounifi` directory first.

### III. Type Safety (NON-NEGOTIABLE)
ALL data retrieved and stored from the API MUST be typed. If types are not supplied by `aiounifi`, then a custom type MUST be created. Use type hints heavily throughout the codebase (`def calculate_area(length: float, width: float) -> float:`). This improves clarity, enables static analysis (like mypy), and aids tooling.

### IV. Root Cause Analysis
When fixing a problem or bug, MUST avoid treating the symptom and MUST look for the root cause. Fixes MUST address underlying issues, not surface-level problems. This prevents recurring issues and technical debt.

### V. Preserve Existing Functionality
Details matter. MUST always preserve existing functionality unless otherwise explicitly instructed. Changes that break existing behavior MUST be justified and documented. Backward compatibility changes may not be required - ask before assuming.

### VI. Code Quality Standards
MUST follow PEP 8 (naming, indentation, whitespace, line length). Use clear, descriptive names for variables, functions, and classes. Follow Single Responsibility Principle (SRP) - functions and classes MUST do one thing and do it well. Keep functions small and focused. Prefer pure functions (no side effects) where possible, especially in core logic, as they are trivial to test. Isolate I/O and state changes.

### VII. KISS (Keep It Simple, Stupid)
MUST prefer simple, elegant solutions over complex ones. When designing a new feature, prefer elegant solutions using established best practices and patterns. Avoid unnecessary complexity. YAGNI (You Aren't Gonna Need It) principles apply.

### VIII. Code Hygiene
MUST maintain consistent code hygiene by addressing code and markdown linting errors and warnings. All linting issues MUST be resolved before proceeding with subsequent phases of work. Enforce code style and quality checks automatically using tools like Ruff, Flake8, formatters (Black), and type checkers (mypy) via pre-commit hooks.

### IX. Targeted Diagnostics
Diagnostics enabled for observability and debugging MUST be targeted, respecting the resources of the system. Avoid excessive logging. Use targeted debug flags (e.g., `LOG_WEBSOCKET`, `LOG_API_CALLS`, `LOG_DATA_UPDATES`) rather than blanket debug logging. Documentation MUST explain how to enable/disable diagnostics.

### X. Project Structure Standards
MUST follow standard Python project structure:
- Root: Contains meta-files (README.md, LICENSE, configuration files, top-level build files)
- Source Code: Place all reusable library code in `custom_components/unifi_network_rules/`
- Tests: Use dedicated `tests/` directory outside the source package
- Dependency Management: Explicitly manage dependencies using `requirements.txt` or `pyproject.toml`
- Environment Isolation: Always use virtual environments (venv) to isolate project dependencies
- Configuration Separation: Separate configuration from code. Do NOT hardcode secrets.

### XI. Documentation Standards
MUST document public APIs (classes, methods, functions) using clear docstrings (e.g., NumPy or Google style) explaining what they do, why, and how to use them. Avoid excessive code comments. Keep a rolling log of each change in `changelog.md`. Update README.md when functionality changes.

### XII. Open Source Accessibility
The integration MUST remain accessible and usable by a wide variety of users and supported devices. Code MUST be open source friendly. Focus on home and home lab use cases. Examples include enhancing guest network access, managing child device access, and promoting good security practices.

## Code Quality Standards

### Python Best Practices
- **Readability First**: Follow PEP 8 strictly. Use clear, descriptive names.
- **Concise & Idiomatic**: Leverage Python features like list comprehensions, generator expressions, and context managers (`with`) instead of long, verbose loops or try/finally blocks.
- **Performance Awareness**: Understand Python's data structures (e.g., set lookups are O(1)). Profile critical sections before optimizing. Avoid premature optimization. Use built-in functions and standard library modules where possible.
- **Modern Python**: Prefer modern idiomatic Python 3.13 and open source conventions. Use CONST over hard-coded strings.

### Code Organization
- **Modular Structure**: Large files MUST be decomposed into focused modules following project patterns (e.g., `switches/` directory with domain-specific modules).
- **Separation of Concerns**: Clear separation between models, services, helpers, UDM API interactions, and coordination logic.
- **Dead Code Removal**: Regularly audit and remove unused code, methods, and attributes.

## Development Workflow

### Pre-Commit Requirements
1. Run linting tools (Ruff, Flake8) and fix all errors
2. Run type checking (mypy) and resolve type issues
3. Run formatters (Black) to ensure consistent formatting
4. Verify tests pass (if applicable)
5. Update `changelog.md` with change description

### Pull Request Process
1. MUST reference an existing issue in the PR description
2. MUST update README.md if functionality changes
3. MUST update manifest.json if needed (version, dependencies, etc.)
4. MUST update config_flow.py if configuration changes
5. MUST update hacs.json if HACS metadata changes
6. MUST ensure all linting errors are resolved

### Code Review Standards
- All PRs/reviews MUST verify constitution compliance
- Complexity MUST be justified
- Breaking changes MUST be documented with migration guides
- Tests MUST be included for new functionality

## Testing Requirements

### Test Organization
- Tests MUST be in dedicated `tests/` directory
- Use pytest for test execution
- Tests MUST be independent and repeatable
- Integration tests MUST cover critical user journeys

### Test Coverage Expectations
- Core logic MUST have test coverage
- API interactions SHOULD have integration tests
- Edge cases MUST be tested
- Error handling MUST be tested

## Documentation Standards

### Required Documentation
- **README.md**: MUST be kept current with functionality changes
- **changelog.md**: MUST log each change made
- **Public APIs**: MUST have docstrings explaining purpose and usage
- **Migration Guides**: MUST be provided for breaking changes
- **Configuration**: MUST document all configuration options

### Documentation Style
- Use clear, concise language
- Include practical examples
- Document edge cases and limitations
- Keep documentation accessible to users of varying technical levels

## Governance

This constitution supersedes all other practices and guidelines. All development work MUST comply with these principles.

### Amendment Process
- Amendments require documentation of rationale
- Breaking principle changes require major version bump
- New principles require minor version bump
- Clarifications and refinements require patch version bump

### Versioning Policy
- Constitution version follows semantic versioning (MAJOR.MINOR.PATCH)
- MAJOR: Backward incompatible principle removals or redefinitions
- MINOR: New principle/section added or materially expanded guidance
- PATCH: Clarifications, wording, typo fixes, non-semantic refinements

### Compliance Review
- All PRs MUST verify constitution compliance
- Code reviews MUST check adherence to principles
- Linting MUST pass before merge
- Documentation MUST be updated for functionality changes

**Version**: 1.0.0 | **Ratified**: TODO(ratification_date) | **Last Amended**: 2025-11-11
