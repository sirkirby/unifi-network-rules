# Quick Start Guide

Get from zero to a working UniFi Network Rules integration in minutes.

> New to the project? See the [README](README.md) for an overview.
> Want to contribute? See [CONTRIBUTING.md](CONTRIBUTING.md).

## Prerequisites

| Requirement | Minimum Version |
|---|---|
| Home Assistant | 2025.8.0+ |
| UniFi Network Application | 9.0.92+ |
| Python (HA runtime) | 3.13+ |
| HACS | Latest recommended |

You also need a **local admin account** on your UniFi device. Cloud-only (UniFi SSO) accounts will not work — the integration authenticates directly against the device's local API.

## Installation

### Option 1: HACS (Recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=sirkirby&repository=UniFi-network-rules&category=integration)

1. Open HACS in your Home Assistant instance.
2. Search for **"UniFi Network Rule Manager"** and install it.
3. Restart Home Assistant.

### Option 2: Manual Installation

1. Download the latest release from [GitHub Releases](https://github.com/sirkirby/unifi-network-rules/releases).
2. Copy the `custom_components/unifi_network_rules` directory into your Home Assistant `config/custom_components/` directory.
3. Restart Home Assistant.

> **Tip**: The [Studio Code Server](https://community.home-assistant.io/t/home-assistant-community-add-on-visual-studio-code/107863) add-on makes it easy to manage files directly in the Home Assistant UI.

## First-Run Setup

After installation and restart:

1. Go to **Settings → Devices & Services → Integrations**.
2. Click the **"+ Add Integration"** button.
3. Search for **"UniFi Network Rule Manager"** and select it.
4. Fill in your connection details:

| Field | Description | Example |
|---|---|---|
| **Host** | IP or hostname of your UniFi device | `192.168.1.1` |
| **Username** | Local admin account | `admin` |
| **Password** | Account password | `••••••••` |
| **Site** | UniFi site name (usually "default") | `default` |
| **Update Interval** | Auto-refresh interval in minutes | `5` |
| **Verify SSL** | Enable for trusted certificates | Disabled by default |

5. Click **Submit**. The integration will discover and create entities for all your network rules.

## What You Get

Once configured, the integration creates **switch entities** for each of your:

- Firewall policies & traffic/firewall rules
- Port forwarding rules
- Traffic routes (with kill switches)
- Static routes
- NAT rules & QoS rules
- OON policies (with kill switches)
- VPN clients & servers (OpenVPN + WireGuard)
- WLANs, port profiles, networks, and device LEDs

Toggle any switch to enable/disable the corresponding rule on your UniFi device.

## Smart Polling Configuration

The integration uses intelligent polling that adapts to activity. Access these settings at **Settings → Devices & Services → UniFi Network Rules → Configure → Options**:

| Setting | Default | Purpose |
|---|---|---|
| Base Interval | 300s | Idle polling rate |
| Active Interval | 30s | Polling rate during activity |
| Realtime Interval | 10s | Rate immediately after changes |
| Activity Timeout | 120s | Time before returning to idle |
| Debounce Seconds | 10s | Wait window after HA-initiated changes |
| Optimistic Timeout | 15s | Max time for optimistic UI updates |

> **Tip**: The defaults work well for most setups. Lower values = faster response, higher values = less API load.

## Services Quick Reference

The integration provides these services for automations:

| Service | What It Does |
|---|---|
| `unifi_network_rules.refresh_rules` | Refresh all rules from controller |
| `unifi_network_rules.backup_rules` | Back up all rules to a JSON file |
| `unifi_network_rules.restore_rules` | Restore rules from a backup file |
| `unifi_network_rules.bulk_update_rules` | Enable/disable rules by name pattern |
| `unifi_network_rules.toggle_rule` | Toggle a specific rule on or off |
| `unifi_network_rules.delete_rule` | Delete a firewall policy by ID |
| `unifi_network_rules.apply_template` | Apply a predefined rule template |
| `unifi_network_rules.save_template` | Save a rule as a reusable template |
| `unifi_network_rules.websocket_diagnostics` | Run WebSocket connection diagnostics |
| `unifi_network_rules.force_cleanup` | Force cleanup of all entities |
| `unifi_network_rules.force_remove_stale` | Remove stale or broken entities |
| `unifi_network_rules.refresh_data` | Refresh data for a specific instance |

See the [README](README.md#services) for full parameter details and automation examples.

## Your First Automation

Here's a simple automation that backs up your rules every night:

```yaml
alias: Daily UniFi Backup
triggers:
  - trigger: time_pattern
    hours: "2"
actions:
  - action: unifi_network_rules.backup_rules
    data:
      filename: "unr_daily_backup.json"
mode: single
```

For trigger-based automations using the `unr_changed` event system, see the [Triggers section](README.md#smart-polling-triggers) in the README.

## Verifying Connectivity

If the integration can't connect, verify your credentials from a machine on the same network:

```bash
curl -k -X POST https://<UDM-IP>/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"<USERNAME>","password":"<PASSWORD>"}'
```

| Response | Meaning |
|---|---|
| `200 OK` | Credentials valid |
| `401 Unauthorized` | Wrong username or password |
| `429 Too Many Requests` | Rate limited — wait a few minutes |

## Enabling Debug Logs

For troubleshooting, enable debug logging:

```yaml
# configuration.yaml
logger:
  logs:
    custom_components.unifi_network_rules: debug
    aiounifi: debug
```

Or use the built-in toggle: **Devices & Services → UniFi Network Rules → Enable Debug Logging**.

## Troubleshooting

### Integration won't connect

- **Use the IP address**, not the hostname, of your UniFi device.
- Ensure your UDM is running Network Application **9.0.92+**.
- Verify HA and the UDM are on the **same network** (or a routed path exists).
- The account **must be a local admin** — UniFi Cloud (SSO) accounts are not supported.

### Entities not appearing after setup

- Restart Home Assistant after initial installation.
- Check that your account has **Admin or Super Admin** privileges in UniFi → Settings → Admins & Users.

### Options flow error (500 error when configuring)

> ⚠️ **Known Issue**: The options flow handler can throw an `AttributeError` due to a property/assignment conflict in [`config_flow.py`](custom_components/unifi_network_rules/config_flow.py). If you hit a 500 error when opening Configure → Options, check for integration updates or report the issue.

### VS Code shows validation errors on triggers

The Home Assistant automation validator (2025.7.0+) doesn't yet recognize custom trigger platforms. The `unr_changed` triggers work correctly despite these warnings — use YAML configuration as shown in the [README examples](README.md#smart-polling-triggers).

### Switches show "Unknown" state

If switches show "Unknown" after setup, wait for the first polling cycle to complete (up to 5 minutes at default base interval). You can force an immediate refresh by calling `unifi_network_rules.refresh_rules`.

### Home Assistant Diagnostics

For bug reports, download diagnostics: **Settings → Devices & Services → UniFi Network Rules → Configure → Download Diagnostics**. This provides system info without exposing sensitive data.

## Limitations

- Uses the same `aiounifi` library as the core HA UniFi integration — version conflicts are possible if both are installed. Restarting HA usually resolves this.
- Does not replicate all UniFi controller features. For full device management, use the core UniFi integration alongside this one.

## Next Steps

- 📖 [README](README.md) — Full services reference, trigger system, and automation examples
- 🤝 [Contributing](CONTRIBUTING.md) — Help improve the integration
- 🔒 [Security](SECURITY.md) — Vulnerability reporting policy
- 💬 [Discussions](https://github.com/sirkirby/unifi-network-rules/discussions) — Questions, ideas, and feedback
- 🐛 [Issues](https://github.com/sirkirby/unifi-network-rules/issues) — Bug reports
