# Contributing to UniFi Network Rules

Thanks for your interest in contributing! This guide will get you from "I want to help" to your first pull request.

> **First time here?** Check the [Quick Start Guide](QUICKSTART.md) to understand what the integration does and how it works.

## Before You Start

Please create a [Feature Request](https://github.com/sirkirby/unifi-network-rules/issues/new?template=feature_request.md) or [Bug Report](https://github.com/sirkirby/unifi-network-rules/issues/new?template=bug_report.md) **before** starting work on a pull request. This ensures alignment and avoids duplicate effort.

## Prerequisites

| Tool | Version |
|---|---|
| Python | 3.13+ |
| pip | Latest |
| Git | Any recent version |

A UniFi device is helpful for end-to-end testing but not required — the test suite uses mocks.

## Development Setup

```bash
# Clone the repository
git clone https://github.com/sirkirby/unifi-network-rules.git
cd unifi-network-rules

# Create a virtual environment and install dependencies
make venv
make install
```

This installs all runtime and development dependencies from [`requirements.txt`](requirements.txt), including:
- `homeassistant`, `aiounifi`, `aiohttp` — runtime dependencies
- `pytest`, `pytest-asyncio`, `pytest-cov` — testing
- `ruff` — linting and formatting

## Available Make Commands

Run `make help` for the full list. The most important ones:

| Command | What It Does |
|---|---|
| `make venv` | Create a Python virtual environment |
| `make install` | Install all dependencies |
| `make lint` | Run Ruff linter |
| `make fix` | Auto-fix lint issues + format code |
| `make test` | Run the test suite |
| `make test-cov` | Run tests with coverage report |
| `make check` | **Run all checks** (lint + test) — run this before every PR |

## Quality Gate

Before submitting a PR, run:

```bash
make check
```

This runs linting and tests — the same checks that CI will run. Your PR will not be merged if these fail.

### Code Style

The project uses [Ruff](https://docs.astral.sh/ruff/) for both linting and formatting, configured in [`pyproject.toml`](pyproject.toml):
- Line length: 120 characters
- Python target: 3.13
- Quote style: double quotes

Run `make fix` to auto-format your code before committing.

## Workflow

1. **Create an issue** (or find an existing one to work on)
2. **Fork and branch**: Create a branch from `main` with a descriptive name
3. **Write code**: Follow existing patterns in the codebase
4. **Write tests**: Add or update tests in [`tests/`](tests/) for your changes
5. **Run checks**: `make check` — fix any failures
6. **Submit PR**: Reference the issue in your PR description

## Pull Request Checklist

- [ ] References an existing issue
- [ ] `make check` passes locally
- [ ] Tests added or updated for the change
- [ ] [`README.md`](README.md) updated if adding user-facing features
- [ ] [`manifest.json`](custom_components/unifi_network_rules/manifest.json) updated if dependencies change

## API Testing

For manual API testing against a real UniFi device, the project maintains a [Bruno collection](https://github.com/sirkirby/bruno-udm-api) with the same requests the integration makes. This is useful for verifying credentials and device compatibility.

## Project Standards

For detailed coding standards, architectural patterns, and conventions, see the [Constitution](oak/constitution.md).

## Getting Help

- 💬 [Discussions](https://github.com/sirkirby/unifi-network-rules/discussions) — Questions and ideas
- 🐛 [Issues](https://github.com/sirkirby/unifi-network-rules/issues) — Bug reports
- 📖 [README](README.md) — Full project documentation
- 🔒 [Security](SECURITY.md) — Vulnerability reporting
