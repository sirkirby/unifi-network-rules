# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in UniFi Network Rules, **please report it responsibly** — do not open a public GitHub issue.

### How to Report

1. **Email**: Send a detailed description to the maintainer via [GitHub private vulnerability reporting](https://github.com/sirkirby/unifi-network-rules/security/advisories/new).
2. **Include**:
   - A description of the vulnerability and its potential impact
   - Steps to reproduce the issue
   - Any suggested fixes (optional but appreciated)

### Response Timeline

| Stage | Timeframe |
|---|---|
| Acknowledgement | Within 72 hours |
| Initial assessment | Within 1 week |
| Fix or mitigation | Best effort, depends on severity |

## Supported Versions

| Version | Supported |
|---|---|
| 4.x (latest) | ✅ Active |
| 3.x | ⚠️ Critical fixes only |
| < 3.0 | ❌ No longer supported |

We recommend always running the latest release available through HACS.

## Security Practices

- **Local authentication only** — the integration connects directly to your UniFi device's local API. No cloud accounts or third-party services are involved.
- **Credentials stay local** — your username and password are stored in Home Assistant's encrypted config entries, never transmitted externally.
- **SSL verification** — optional SSL certificate verification is available for environments with trusted certificates.
- **No telemetry** — the integration does not collect or transmit usage data.

## Scope

This policy covers the `custom_components/unifi_network_rules` integration code. Issues with the UniFi controller itself, Home Assistant core, or the `aiounifi` library should be reported to their respective maintainers.

## More Information

- [README](README.md) — Project overview
- [Contributing](CONTRIBUTING.md) — Development guidelines
- [Quick Start](QUICKSTART.md) — Installation and setup
