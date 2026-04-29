# AI Assistant Instructions

This file contains instructions for AI assistants (Cursor, Codex CLI) when working with this project.

---

## Project Constitution

This project follows engineering standards and conventions defined in the project constitution.

**Read the constitution first:** [oak/constitution.md](oak/constitution.md)

The constitution defines:
- Architecture principles and patterns
- Code standards and best practices
- Testing requirements
- Documentation standards
- Governance and decision-making processes

All suggestions and code generated must align with the constitution.

- Type hints are required.
- Follow Ruff lint + format rules defined in `pyproject.toml`. Do not disable rules inline without reason.
- Google-style docstrings on public functions and classes.
- Do not swallow exceptions silently; log with context. Never put secrets, tokens, or session data in logs or error messages.

## Quality Gates

Before claiming work is done, run:

```
make lint
make test
```

Both MUST pass. Do not use `--no-verify` or skip hooks.

## Working Style

- Fix root causes, not symptoms.
- Prefer editing existing files over creating new ones.
- Default to no comments; add one only when the *why* is non-obvious.
- New dependencies require explicit approval — do not add them unprompted.


<!-- myco:managed:start -->
## Myco Managed Guidance

- When `capture.ignore_plan_dirs_in_git` is enabled, custom directories in `capture.plan_dirs` may be intentionally gitignored after capture into Myco.
- Do not force-add files from intentionally gitignored custom plan directories unless the user explicitly asks.
<!-- myco:managed:end -->
