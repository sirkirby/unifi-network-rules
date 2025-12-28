## Pre-Decision Relevance Assessment

**Before presenting any decision options, assess which decisions are RELEVANT to this project type.**

The decision framework is comprehensive, but NOT all decisions apply to all projects.

### Project Type Classification

| Project Type | Example Tech | Relevant Decisions | Skip or Adapt |
|--------------|--------------|-------------------|---------------|
| **Web Application** | React, Next.js, Django, FastAPI | All 5 decisions | None |
| **Backend Service/API** | FastAPI, Express, Spring Boot | All 5 decisions | None |
| **CLI Tool** | Click, Typer, Commander | Testing, Review, Docs, CI/CD | Architecture may not apply |
| **Automation/Scripts** | GitHub Actions, Bash, Make | Testing (adapted), Review, Docs, CI/CD | Architecture typically N/A |
| **Infrastructure/IaC** | Terraform, Pulumi | Testing (adapted), Review, Docs | Standard architecture N/A |
| **Library/Package** | PyPI, npm package | All decisions | Architecture may be simpler |
| **Data Pipeline** | Airflow, Dagster, dbt | Testing, Review, Docs, CI/CD | Architecture adapted |

### Decision Applicability Rules

**For Automation/Scripts repos:**
- **Testing**: ASK, but adapt to "workflow testing," "smoke tests," "dry-run validation"
- **Architecture**: SKIP - traditional patterns don't apply

**For CLI tools:**
- **Architecture**: Offer "Pragmatic/Adaptive" or "Custom" - don't push enterprise patterns

**For Infrastructure/IaC:**
- **Testing**: Adapt to "plan validation," "policy-as-code testing"
- **Architecture**: SKIP - IaC has its own patterns (modules, environments, workspaces)

### How to Handle Non-Applicable Decisions

**DO NOT:** Present all options and let user say "doesn't apply"
**DO:** Skip the decision and note it, or adapt the question to the project context

### Assessment Template

Before presenting decisions, determine:

```text
Project Type: [Web App / CLI / Automation / Infrastructure / etc.]

Decision Applicability:
- Testing: [RELEVANT / ADAPT to: _____]
- Code Review: [RELEVANT - always]
- Documentation: [RELEVANT - always]
- CI/CD: [RELEVANT / N/A - reason]
- Architecture: [RELEVANT / SKIP - reason / ADAPT to: _____]
```

**Proceed to gather ONLY the relevant decisions.**
