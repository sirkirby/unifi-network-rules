# UniFi Network Rules

[![License][license-shield]](LICENSE)
![Project Maintenance][maintenance-shield]
[![GitHub Activity][commits-shield]][commits]

[![GitHub Release][release-shield]][releases]
[![issues][issues-shield]][issues-link]
[![validate-badge]][validate-workflow]

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/sirkirby)

UniFi Network Rules is a custom integration for Home Assistant that integrates with your UniFi Dream Machine/Router to both provide and help you create useful interactions and automations for your Home Lab. The goal of this integration is to simplify policy and rule management for real world use cases. I built this because I wanted to unlock the power of my UniFi firewall. From simple things like screen time and game server access controls for my kids, to more advanced like getting notified when a critical rule is changed and automatically backing up your rules. And most importantly, make all of this easy to use and share with anyone in your home or home lab. I hope you find it useful!

> 📖 **[Quick Start Guide](QUICKSTART.md)** — Installation, setup, and troubleshooting
> 🤝 **[Contributing](CONTRIBUTING.md)** — Development setup and PR workflow
> 🔒 **[Security](SECURITY.md)** — Vulnerability reporting policy

## What this integration provides

### Switches for enabling and disabling rules and configuration

- Firewall policies (zone-based firewall)
- Traffic/firewall rules (non-zone-based firewall)
- Port Forwarding rules
- Traffic Routes & Traffic Route Kill Switch
- Static Routes (network routing configurations)
- NAT rules
- QoS rules
- Object-Oriented Network (OON) policies & OON Policy Kill Switch
- OpenVPN Client and Server configurations
- WireGuard Client and Server configurations
- UniFi Device LEDs
- WLAN SSIDs
- Port Profiles (switch port configurations)
- Networks (network configurations)

### Advanced automations powered by [Custom Triggers](#smart-polling-triggers) and [Custom Services](#services)

The included [Triggers](#smart-polling-triggers) and [Services](#services) provide a framework for building custom UDM automations to cover a wide range of use cases. For example, you can [backup](#3-backup-trigger---save-config-on-important-changes) and [restore](#full-and-selective-restore) all rules when a change is detected, ensure game server port [forwarding rules get disabled](#2-game-server-management---auto-disable-after-hours) at bedtime, [create and maintain an audit log](#1-security-monitoring---alert-on-unexpected-rule-changes) of all UDM configuration changes, and so much more. Get inspired by the many examples below.

> Questions, ideas, help, or feedback? [Discussions](https://github.com/sirkirby/unifi-network-rules/discussions). Errors or bugs? [Issues](https://github.com/sirkirby/unifi-network-rules/issues).

## Installation

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=sirkirby&repository=UniFi-network-rules&category=integration)

[![hacs][hacsbadge]][hacs]
[![Discord][discord-shield]][discord]
[![Community Forum][forum-shield]][forum]

If you don't or can't use HACS, alternatively, copy the `custom_components/unifi_network_rules` directory to your `config/custom_components` directory.

I recommend installing the Studio Code Server addon to make it easier to copy in the custom component directly in the Home Assistant UI. `Settings -> Add-ons -> Studio Code Server -> Install`. Then turn on `Show in Sidebar`.

THEN

1. Restart Home Assistant.
2. In the Home Assistant configuration page, click on "Integrations".
3. Click on the "+" button in the bottom right corner.
4. Search for "UniFi Network Rule Manager" and select it.
5. Enter credentials of a local admin user on your UDM and click on the "Submit" button.

### Requirements

- A UniFi device running network application 9.0.92 or later.
- A local account with Admin privileges to the network application. Must not be a UniFi Cloud account.
- Home Assistant 2025.2 or later with network access to the UniFi device.

## Configuration

**Host**: The IP address or hostname of your UniFi Device. ex. `192.168.1.1` or `udm.mydomain.com`

**Username**: The local admin account on the UDM. ex. `admin`

**Password**: The password for the UDM account. ex. `password`

**Site**: The UniFi site name to connect to (defaults to "default" if not specified).

**Update Interval**: The automatic refresh interval in minutes. Can be longer since updates real-time.

**Verify SSL**: Enable SSL certificate verification (defaults to disabled for self-signed certificates).

### Advanced Smart Polling Options

These options configure the intelligent polling system that provides near real-time updates. You can access these settings by going to **Settings → Devices & Services → UniFi Network Rules → Configure → Options**.

**Base Interval** (default: 300 seconds): The standard polling interval when the system is idle and no recent activity has been detected. This is the baseline refresh rate that maintains system state without excessive API calls.

**Active Interval** (default: 30 seconds): The faster polling interval used when recent activity has been detected. The system automatically switches to this mode after detecting changes to maintain responsiveness.

**Realtime Interval** (default: 10 seconds): The fastest polling interval used immediately after detecting changes, providing near real-time updates. The system uses this for a short period after activity before stepping down to the active interval.

**Activity Timeout** (default: 120 seconds): How long (in seconds) the system remains in active/realtime polling mode after the last detected activity before returning to the base interval. This balances responsiveness with resource usage.

**Debounce Seconds** (default: 10 seconds): The debounce window for Home Assistant-initiated changes. When you toggle a switch in HA, the system waits this long before polling to allow the change to propagate, preventing unnecessary API calls from rapid successive changes.

**Optimistic Timeout** (default: 15 seconds): Maximum time to show optimistic state updates in the UI before requiring confirmation from the UniFi controller. This provides instant feedback while ensuring accuracy.

> **💡 Tip**: The default values work well for most setups. Only adjust these if you need faster response times (lower values) or want to reduce API load (higher values). The smart polling system automatically adapts based on activity levels.

## Services

The integration provides several services focused on managing and automating existing UniFi Network rules:

### Getting Started with Services

Here are some examples of how to get started with services in Home Assistant:

#### Example 1: Using an Input Button Helper with Automation

1. Go to Settings → Devices & Services → Helpers
2. Add a Button helper (e.g., "Refresh UniFi Rules")
3. Create an automation that triggers when the button is pressed
4. Use the service in the automation's action

Example automation for refresh:

```yaml
alias: Backup UniFi Network Rules
description: >-
  Dumps all policy, rule, and route JSON state to a file in the ha config
  directory
triggers:
  - trigger: state
    entity_id:
      - input_button.backup_unr
conditions: []
actions:
  - action: unifi_network_rules.backup_rules
    metadata: {}
    data:
      filename: unr_daily_backup.json
mode: single
```

#### Example 2: Using Scripts with a Lovelace Button Card (More Customizable)

First, create a script in your Settings → Automations & Scenes → Scripts:

```yaml
sequence:
  - sequence:
      - action: unifi_network_rules.backup_rules
        metadata: {}
        data:
          filename: my_custom_unr_backup.json
alias: Backup my UniFi Rules
description: Custom script that will backup all rules and routes imported from your UDM
```

Then add a button card to your dashboard that references the script:

```yaml
show_name: true
show_icon: true
type: button
tap_action:
  action: perform-action
  perform_action: script.backup_my_unifi_rules
  target: {}
name: Backup my Network Rules
icon: mdi:cloud-upload
```

See below for more automation examples using [Services with Triggers](#service-automation-examples).

### Services Reference

| Service | Description | Parameters |
|---------|-------------|------------|
| `unifi_network_rules.refresh_rules` | Manually refresh all network rules from the UniFi controller | None |
| `unifi_network_rules.backup_rules` | Create a backup of all firewall policies and traffic routes | `filename`: Name of the backup file to create |
| `unifi_network_rules.restore_rules` | Restore rules from a backup file | `filename`: Backup file to restore from<br>`name_filter`: (Optional) Only restore rules containing this string<br>`rule_ids`: (Optional) List of specific rule IDs to restore<br>`rule_types`: (Optional) List of rule types to restore (policy, port_forward, traffic_route, qos_rule, port_profile, network, static_route, nat, oon_policy) |
| `unifi_network_rules.bulk_update_rules` | Enable or disable multiple rules by name pattern | `state`: true (enable) or false (disable)<br>`name_filter`: String to match in rule names |
| `unifi_network_rules.delete_rule` | Delete an existing firewall policy by ID | `rule_id`: ID of the rule to delete |
| `unifi_network_rules.refresh_data` | Refresh data for a specific integration instance or all | `entry_id`: (Optional) Specific integration instance ID |
| `unifi_network_rules.websocket_diagnostics` | Run diagnostics on WebSocket connections and try to repair if needed | None |
| `unifi_network_rules.force_cleanup` | Force cleanup of all entities in the integration | None |
| `unifi_network_rules.force_remove_stale` | Force removal of stale or broken entities | `remove_all`: (Optional) Remove all entities instead of just stale ones |
| `unifi_network_rules.apply_template` | Apply a predefined rule template | `template_id`: ID of the template to apply<br>`variables`: (Optional) Variables to use in the template |
| `unifi_network_rules.save_template` | Save a rule as a template for reuse | `rule_id`: UniFi rule ID (use `trigger.rule_id` in automations)<br>`template_id`: ID to save the template as<br>`rule_type`: (Optional) Type of rule - auto-detected if not provided |
| `unifi_network_rules.toggle_rule` | Toggle a specific rule on or off | `rule_id`: UniFi rule ID (use `trigger.rule_id` in automations)<br>`rule_type`: (Optional) Type of the rule - auto-detected if not provided |

> **Note**: For `rule_types` parameter, you can specify one or more of: `policy` (firewall policies), `port_forward` (port forwarding rules), `traffic_route` (policy-based routes), `qos_rule` (quality of service rules), `port_profile` (switch port profiles), `network` (network configurations), `static_route` (static routes), `nat` (NAT rules), or `oon_policy` (Object-Oriented Network policies). While not all of these are strictly "rules," they are all toggleable configuration entities. See the "Understanding Rule Types" section for more details.

## Smart Polling Triggers

> **⚠️ BREAKING CHANGE**: Legacy triggers (`rule_enabled`, `rule_disabled`, `rule_changed`, `rule_deleted`, `device_changed`) have been **removed** and replaced with a unified `unr_changed` trigger system. See [Migration Guide](#migration-options) below.

UniFi Network Rules provides a **unified trigger system** powered by intelligent polling that gives you near real-time notifications when network rules change, regardless of whether the changes originate from Home Assistant or directly from the UniFi console.

### Key Features

- **🔄 Bi-Directional Monitoring**: Triggers fire for changes made both from Home Assistant and directly from the UniFi console
- **⚡ Smart Polling**: Intelligent polling with dynamic intervals (10s during activity, 5min when idle)
- **🎯 Unified Interface**: Single `unr_changed` trigger with powerful filtering options
- **📊 Rich Data**: Each trigger includes entity IDs, old/new states, timestamps, and metadata
- **🛡️ Reliable Detection**: Centralized state comparison ensures accurate change detection
- **🚀 Debounced Updates**: Batches rapid changes into single operations to prevent API spam

### The Unified Trigger

**All events now use a single trigger type:** `unr_changed`

| Filter | Description | Example |
|--------|-------------|---------|
| `entity_id` | Monitor specific entity | `switch.unr_firewall_policy_abc123` |
| `change_type` | Monitor entity type | `firewall_policy`, `traffic_route`, `port_forward` |
| `change_action` | Monitor action type | `enabled`, `disabled`, `modified`, `created`, `deleted` |
| `name_filter` | Filter by entity name | `"Guest Network"` (case-insensitive substring) |

### Supported Entity Types

- **Firewall Policies** (`firewall_policy`): Zone-based firewall rules
- **Port Forwards** (`port_forward`): Port forwarding rules  
- **Traffic Routes** (`traffic_route`): Network routing rules
- **Static Routes** (`route`): Static network routing configurations
- **Traffic Rules** (`traffic_rule`): Legacy firewall rules
- **QoS Rules** (`qos_rule`): Quality of Service rules
- **Object-Oriented Network Policies** (`oon_policy`): Unified policies combining QoS, routing, and security features
- **VPN Clients** (`vpn_client`): VPN client configurations
- **VPN Servers** (`vpn_server`): VPN server configurations
- **WLANs** (`wlan`): Wireless network configurations
- **Devices** (`device`): Device LED controls
- **Port Profiles** (`port_profile`): Switch port profiles
- **Networks** (`network`): Network configurations
- **NAT Rules** (`nat`): UniFi NAT (SNAT/DNAT) rules

### Setting Up Triggers

#### YAML Configuration

```yaml
triggers:
  - trigger: unifi_network_rules
    type: unr_changed
    change_type: firewall_policy    # Optional: filter by entity type
    change_action: enabled          # Optional: filter by action type
    name_filter: "Minecraft"       # Optional: filter by entity name
```

#### Advanced Examples

```yaml
# Monitor any firewall policy change
triggers:
  - trigger: unifi_network_rules
    type: unr_changed
    change_type: firewall_policy

# Monitor specific entity
triggers:  
  - trigger: unifi_network_rules
    type: unr_changed
    entity_id: switch.unr_firewall_policy_abc123

# Monitor multiple actions
triggers:
  - trigger: unifi_network_rules
    type: unr_changed
    change_action: [enabled, disabled]
    name_filter: "Gaming"
```

### Available Trigger Data

Each trigger provides rich data you can use in conditions and actions:

```yaml
# Available in automations as trigger.*
platform: "unifi_network_rules"         # Platform name
type: "unr_changed"                      # Trigger type (always unr_changed)
entity_id: "switch.unr_firewall_policy_abc123"  # HA entity ID
unique_id: "unr_firewall_policy_abc123"  # Unique identifier
rule_id: "64f1a2b3c4d5e6f7g8h9i0j1"     # UniFi rule ID
change_type: "firewall_policy"           # Entity type that changed
change_action: "enabled"                 # What happened (enabled/disabled/modified/created/deleted)
entity_name: "Minecraft Server Access"   # Human-readable entity name
old_state: { ... }                       # Previous rule configuration
new_state: { ... }                       # New rule configuration  
timestamp: "2025-08-27T10:30:00Z"        # When the change occurred
source: "polling"                        # Always "polling" in new architecture
```

### Example Usage in Templates

```yaml
# Use trigger data in notifications
action: notify.mobile_app
data:
  title: "🔥 Network Rule Changed"
  message: >
    {{ trigger.entity_name }} was {{ trigger.change_action }}
    Entity: {{ trigger.entity_id }}
    Time: {{ trigger.timestamp }}

# Use trigger data in service calls
action: unifi_network_rules.toggle_rule
data:
  rule_id: "{{ trigger.rule_id }}"        # Clean UniFi rule ID from trigger
  enabled: true

# Example service calls
action: unifi_network_rules.delete_rule
data:
  rule_id: "{{ trigger.rule_id }}"        # Use trigger data for clean automation
  
action: unifi_network_rules.save_template  
data:
  rule_id: "{{ trigger.rule_id }}"        # Consistent approach across all services
  template_id: "my_vpn_template"
```

## Trigger Migration Guide 📝

> **Required for users upgrading from previous versions with legacy triggers**

### Overview

**Legacy triggers have been completely removed** in favor of a unified, more powerful `unr_changed` trigger system. This is a **breaking change** that requires updating your automation files.

### Migration Options

#### Option 1: Automated Migration (Recommended)

Use the migration utility script to automatically convert your automations. The utility offers multiple workflows depending on your comfort level:

##### Copy-and-Migrate Workflow (Safest - Recommended for Most Users)

This workflow is perfect if you need to download your automations file from Home Assistant. The easiest method is using the Visual Studio Code add-on:

**Step-by-step using VS Code Add-on:**

1. **Download your automations.yaml**:
   - Install the [Visual Studio Code add-on](https://community.home-assistant.io/t/home-assistant-community-add-on-visual-studio-code/107863) from Home Assistant Community Add-ons
   - Open VS Code in your browser and navigate to `/config/automations.yaml`
   - Right-click the file and select "Download"

2. **Run the migration**:

   ```bash
   python migrate_triggers.py --copy-migrate automations.yaml
   ```

3. **Review the migrated file** to ensure it looks correct

4. **Upload the migrated file**:
   - In VS Code, navigate to the `/config/` folder
   - Drag and drop the migrated file to replace your existing `automations.yaml`
   - Or right-click in the folder and select "Upload Files"

5. **Restart Home Assistant**

##### Additional Commands

```bash
# 1. Scan for legacy triggers
python migrate_triggers.py --scan /config/automations.yaml

# 2. Preview migration (dry-run)
python migrate_triggers.py --migrate /config/automations.yaml --dry-run

# 3. Apply migration (creates backup automatically)
python migrate_triggers.py --migrate /config/automations.yaml --apply
```

##### Getting the Migration Utility

Since the migration utility is not included in the integration itself (it's only needed once), you have a few options:

1. **Download from GitHub** (Recommended):
   - Go to the [UniFi Network Rules repository](https://github.com/sirkirby/unifi-network-rules)
   - Download `scripts/migrate_triggers.py` to your computer
   - Ensure you have Python 3 and PyYAML installed (`pip install pyyaml`)

2. **Clone the repository**:

   ```bash
   git clone https://github.com/sirkirby/unifi-network-rules.git
   cd unifi-network-rules
   python scripts/migrate_triggers.py --help
   ```

##### Alternative ways to download your Automations File from Home Assistant

If you don't have direct access to your Home Assistant files, you can download them through the web interface:

1. **Using File Editor Add-on**:
   - Install the "File Editor" add-on from the Add-on Store
   - Navigate to `/config/automations.yaml`
   - Copy the content and save it to a local file

2. **Using SSH/SCP** (Advanced):

   ```bash
   scp homeassistant@your-ha-ip:/config/automations.yaml ./automations.yaml
   ```

**After migration, upload the migrated file back:**

- **VS Code Add-on**: Drag and drop the migrated file into the `/config/` folder, or right-click and select "Upload Files"
- **File Editor Add-on**: Copy and paste the migrated content into the editor
- **SSH/SCP**: Use `scp` to upload the migrated file back to your Home Assistant system

##### Migration Utility Troubleshooting

**Python/PyYAML not installed:**

```bash
# Install Python 3 (if needed)
# On Windows: Download from python.org
# On macOS: brew install python
# On Linux: apt-get install python3 python3-pip

# Install PyYAML
pip install pyyaml
# or
pip3 install pyyaml
```

**"No legacy triggers found" but you have v3.x automations:**

- Ensure you're running the utility on the correct automations.yaml file
- Check that your automations use `platform: unifi_network_rules` (not just any triggers)
- Verify your automations use legacy trigger types: `rule_enabled`, `rule_disabled`, `rule_changed`, `rule_deleted`, or `device_changed`

**Need help?**

- Use `python migrate_triggers.py --help` for command line options
- Use `python migrate_triggers.py --scan your_file.yaml` to see what would be migrated
- [Open a discussion](https://github.com/sirkirby/unifi-network-rules/discussions) if you need assistance

#### Option 2: Manual Migration

Update your automation triggers manually using the examples below.

### Common Migration Patterns

#### Basic State Changes

```yaml
# OLD (removed)
trigger:
  platform: unifi_network_rules
  type: rule_enabled
  rule_type: firewall_policies

# NEW (required)
trigger:
  platform: unifi_network_rules
  type: unr_changed
  change_type: firewall_policy
  change_action: enabled
```

#### Rule Disabled

```yaml  
# OLD (removed)
trigger:
  platform: unifi_network_rules
  type: rule_disabled
  rule_id: "abc123"

# NEW (required)
trigger:
  platform: unifi_network_rules
  type: unr_changed
  entity_id: "switch.unr_firewall_policy_abc123"  # Convert rule_id to entity_id
  change_action: disabled
```

#### Any Rule Change

```yaml
# OLD (removed) 
trigger:
  platform: unifi_network_rules
  type: rule_changed
  rule_type: port_forwards

# NEW (required)
trigger:
  platform: unifi_network_rules
  type: unr_changed
  change_type: port_forward
  change_action: [enabled, disabled, modified]
```

#### Rule Deletion

```yaml
# OLD (removed)
trigger:
  platform: unifi_network_rules
  type: rule_deleted
  name_filter: "Guest*"

# NEW (required)
trigger:
  platform: unifi_network_rules
  type: unr_changed
  change_action: deleted
  name_filter: "Guest"
```

#### Device Changes (LED)

```yaml
# OLD (removed)
trigger:
  platform: unifi_network_rules
  type: device_changed
  device_id: "aa:bb:cc:dd:ee:ff"
  change_type: "led_toggled"

# NEW (required)
trigger:
  platform: unifi_network_rules
  type: unr_changed
  change_type: device
  entity_id: "switch.unr_device_aabbccddeeff_led"
  change_action: [enabled, disabled]
```

### Benefits of New System

- **🎯 More Precise Filtering**: Target specific entities, actions, or patterns
- **📊 Richer Data**: Access to entity IDs, timestamps, and structured state data
- **🔧 Simpler Configuration**: One trigger type instead of five
- **⚡ Better Performance**: Smart polling reduces API load while maintaining responsiveness  
- **🛡️ More Reliable**: No WebSocket dependency, consistent behavior

### Need Help?

- **Questions about migration?** [Open a Discussion](https://github.com/sirkirby/unifi-network-rules/discussions)
- **Found a migration issue?** [Report a Bug](https://github.com/sirkirby/unifi-network-rules/issues)
- **See examples below** for updated automation patterns

## Trigger Automation Examples

### 1. Security Monitoring - Alert on Unexpected Rule Changes

Create rich notifications when firewall policies are modified:

```yaml
alias: Security Alert - Firewall Changes
description: Alert when firewall rules are modified outside of HA
triggers:
  - trigger: unifi_network_rules
    type: unr_changed
    change_type: firewall_policy
    change_action: [modified, deleted]
conditions: []
actions:
  - action: notify.mobile_app_admin_phone
    data:
      title: "🚨 Network Security Alert"
      message: >
        Firewall rule "{{ trigger.entity_name }}" was {{ trigger.change_action }}
        Entity: {{ trigger.entity_id }}
        Time: {{ trigger.timestamp }}
      data:
        priority: high
        category: security
mode: single
```

Use the `new_state` and `old_state` to get the full details of the rule change. (check your backup file to see what is available for each rule type)

```yaml
alias: UniFi Policy Changed
description: UniFi Rule Changed Trigger
triggers:
  - trigger: unifi_network_rules
    type: unr_changed
    change_type: firewall_policy
    change_action: [enabled, disabled, modified]
conditions: []
actions:
  - data:
      title: >-
        Firewall Policy {{ trigger.entity_name }} was {{ trigger.change_action.upper() }}
      message: |-
        {% if trigger.new_state %}
          The {{ trigger.new_state.action }} policy '{{ trigger.entity_name }}' was updated. It is now {{ 'enabled' if trigger.new_state.enabled else 'disabled' }}.
        {% else %}
          The policy '{{ trigger.entity_name }}' was deleted.
        {% endif %}
    action: persistent_notification.create
mode: single
```

### 2. Game Server Management - Auto-Disable After Hours

Automatically disable game server access when enabled outside of allowed hours:

```yaml
alias: Game Server Auto-Disable
description: Disable Minecraft server if enabled during school hours
triggers:
  - trigger: unifi_network_rules
    type: unr_changed
    change_action: enabled
    name_filter: "Minecraft"
conditions:
  - condition: time
    after: "08:00:00"
    before: "15:30:00"
  - condition: time
    weekday:
      - mon
      - tue
      - wed
      - thu
      - fri
actions:
  - delay:
      minutes: 5  # Give a 5-minute grace period
  - action: unifi_network_rules.toggle_rule
    data:
      rule_id: "{{ trigger.rule_id }}"
      enabled: false
  - action: notify.family_devices
    data:
      title: "🎮 Game Server Disabled"
      message: "Minecraft server was automatically disabled during school hours"
mode: single
```

### 3. Backup Trigger - Save Config on Important Changes

Automatically backup network rules when critical changes are made by combining triggers and services:

```yaml
alias: Auto-Backup on Critical Changes
description: Backup rules when important firewall or VPN changes occur
triggers:
  - trigger: unifi_network_rules
    type: unr_changed
    change_type: firewall_policy
    change_action: [modified, deleted]
  - trigger: unifi_network_rules
    type: unr_changed
    change_type: vpn_server
    change_action: [enabled, disabled, modified]
conditions:
  # Only backup if it's been more than 1 hour since last backup
  - condition: template
    value_template: >
      {% set last = state_attr('automation.auto_backup_on_critical_changes','last_triggered') %}
      {% set last_ts = last.timestamp() if last else 0 %}
      {{ (now().timestamp() - last_ts) > 3600 }}
actions:
  - action: unifi_network_rules.backup_rules
    data:
      filename: "auto_backup_{{ now().strftime('%Y%m%d_%H%M') }}.json"
  - action: persistent_notification.create
    data:
      title: "📁 Network Rules Backed Up"
      message: >
        Automatic backup created due to {{ trigger.change_action }} 
        of {{ trigger.change_type.replace('_', ' ').title() }}: "{{ trigger.entity_name }}"
mode: single
```

### 4. VPN Connection Monitoring

Monitor specificVPN client connections and reconnect them when they disconnect:

```yaml
alias: Reconnect VPN Client
description: Monitor when a specific VPN client disconnects and reconnect
triggers:
  - trigger: unifi_network_rules
    type: unr_changed
    change_type: vpn_client
    change_action: disabled
    name_filter: "NordVPN-Chicago"
actions:
  - action: unifi_network_rules.toggle_rule
    data:
      rule_id: "{{ trigger.rule_id }}"      # Direct UniFi ID (recommended)
      enabled: true
      # Note: rule_type auto-detected from ID, no need to specify
  - action: persistent_notification.create
    data:
      title: "🔒 Attempting to reconnect VPN"
      message: >
        VPN "{{ trigger.entity_name }}" was disconnected, attempting to reconnect
mode: parallel
```

```yaml
alias: VPN Client connected
description: Notify when VPN clients connect
triggers:
  - trigger: unifi_network_rules
    type: unr_changed
    change_type: vpn_client
    change_action: enabled
actions:
  - action: persistent_notification.create
    data:
      title: "🔒 VPN Connected"
      message: >
        VPN "{{ trigger.entity_name }}" was connected
```

### 5. Kids' Device Management with Notifications

Monitor and log when parental control rules change:

```yaml
alias: Parental Control Monitor
description: Track changes to kids' internet access rules
triggers:
  - trigger: unifi_network_rules
    type: unr_changed
    change_action: [enabled, disabled]
    name_filter: "Kid"
  - trigger: unifi_network_rules
    type: unr_changed
    change_action: modified
    name_filter: "Block"
actions:
  - action: logbook.log
    data:
      name: "Parental Controls"
      message: >
        {{ trigger.entity_name }} was {{ trigger.change_action }}
        {% if trigger.change_action == 'enabled' %}
        ✅ Internet access restored
        {% elif trigger.change_action == 'disabled' %}
        🚫 Internet access blocked
        {% else %}
        🔧 Settings modified
        {% endif %}
      entity_id: automation.parental_control_monitor
  - action: notify.parents_devices
    data:
      title: "👨‍👩‍👧‍👦 Parental Control Update"
      message: "{{ trigger.entity_name }} - {{ trigger.change_action.title() }}"
mode: parallel
```

### 6. Network Health Dashboard

Create input helpers to track network rule changes on your dashboard:

```yaml
alias: Update Network Stats
description: Update dashboard counters for network changes
triggers:
  - trigger: unifi_network_rules
    type: unr_changed
    change_action: [enabled, disabled, modified]
actions:
  - action: counter.increment
    target:
      entity_id: counter.network_rule_changes
  - action: input_text.set_value
    target:
      entity_id: input_text.last_network_change
    data:
      value: >
        {{ now().strftime('%H:%M') }}: {{ trigger.entity_name }} ({{ trigger.change_action }})
  - action: input_datetime.set_datetime
    target:
      entity_id: input_datetime.last_rule_change
    data:
      datetime: "{{ now() }}"
mode: parallel
```

### 7. OON Policy Management - Unified Policy Automation

Monitor and manage Object-Oriented Network policies that combine QoS, routing, and security:

```yaml
alias: OON Policy Monitor
description: Alert when OON policies are modified or disabled
triggers:
  - trigger: unifi_network_rules
    type: unr_changed
    change_type: oon_policy
    change_action: [modified, disabled]
conditions: []
actions:
  - action: notify.admin_team
    data:
      title: "🛡️ OON Policy Changed"
      message: >
        OON Policy "{{ trigger.entity_name }}" was {{ trigger.change_action }}.
        {% if trigger.change_action == 'modified' %}
        This policy combines QoS, routing, and security features - verify the changes are intentional.
        {% else %}
        Policy disabled - traffic routing and QoS features are now inactive.
        {% endif %}
      data:
        priority: normal
        category: network
mode: single
```

Automatically enable OON policy kill switch when routing is enabled:

```yaml
alias: Auto-Enable OON Kill Switch
description: Automatically enable kill switch when OON policy routing is enabled
triggers:
  - trigger: unifi_network_rules
    type: unr_changed
    change_type: oon_policy
    change_action: enabled
conditions:
  - condition: template
    value_template: >
      {% if trigger.new_state and trigger.new_state.route %}
        {{ trigger.new_state.route.enabled == true }}
      {% else %}
        false
      {% endif %}
actions:
  - delay:
      seconds: 5  # Wait for policy to fully enable
  - action: switch.turn_on
    target:
      entity_id: "{{ trigger.entity_id.replace('oon_policy', 'oon_policy_kill_switch') }}"
  - action: persistent_notification.create
    data:
      title: "🔒 Kill Switch Enabled"
      message: >
        Automatically enabled kill switch for OON Policy "{{ trigger.entity_name }}"
        to prevent data leakage if routing fails.
mode: single
```

### 8. Static Route Management - Network Connectivity Monitoring

Monitor static route changes and ensure critical network paths remain active:

```yaml
alias: Critical Route Monitor
description: Alert when critical static routes are disabled
triggers:
  - trigger: unifi_network_rules
    type: unr_changed
    change_type: route
    change_action: disabled
    name_filter: "Critical"
conditions: []
actions:
  - action: notify.admin_team
    data:
      title: "⚠️ Critical Network Route Disabled"
      message: >
        ALERT: Critical network route "{{ trigger.entity_name }}" was disabled.
        Destination: {{ trigger.old_state.destination if trigger.old_state else "Unknown" }}
        This may affect network connectivity to critical services.
      data:
        priority: high
        category: network
  - action: persistent_notification.create
    data:
      title: "Network Route Alert"
      message: >
        Critical route {{ trigger.entity_name }} was disabled at {{ trigger.timestamp }}
mode: single
```

### Advanced Filtering Examples

#### Filter by Multiple Rule Types

```yaml
triggers:
  - trigger: unifi_network_rules
    type: unr_changed
    change_type: port_forward
    change_action: [enabled, disabled, modified]
  - trigger: unifi_network_rules
    type: unr_changed
    change_type: vpn_client
    change_action: [enabled, disabled, modified]
  - trigger: unifi_network_rules
    type: unr_changed
    change_type: route
    change_action: [enabled, disabled, modified]
  - trigger: unifi_network_rules
    type: unr_changed
    change_type: oon_policy
    change_action: [enabled, disabled, modified]
```

#### Filter by Specific Rule Names

```yaml
triggers:
  - trigger: unifi_network_rules
    type: unr_changed
    change_action: enabled
    name_filter: "Gaming"  # Matches any rule containing "Gaming"
```

#### Monitor Specific Entity

```yaml
triggers:
  - trigger: unifi_network_rules
    type: unr_changed
    entity_id: "switch.unr_firewall_policy_abc123"  # Monitor one specific entity
    change_action: [enabled, disabled, modified]
```

### Best Practices for Triggers

1. **Use Specific Filters**: Filter triggers to avoid unnecessary automation runs
2. **Add Conditions**: Use time, state, or template conditions to refine when automations run
3. **Set Appropriate Modes**: Use `single`, `parallel`, or `queued` based on your needs
4. **Log Important Changes**: Use logbook entries for audit trails
5. **Test Thoroughly**: Test triggers with both HA-initiated and console-initiated changes
6. **Monitor Performance**: Triggers are real-time, so ensure your automations are efficient

### Troubleshooting Triggers

- **VS Code Validation Errors**: The automation validator in HA 2025.7.0 doesn't recognize custom trigger platforms yet, causing false validation errors. The triggers work correctly despite these warnings.
- **UI Shows "Unknown"**: The automation UI doesn't display custom trigger options. Use YAML configuration as shown in the examples above.
- **Enable Debug Logging**: Set `LOG_TRIGGERS = True` in `const.py` for detailed trigger logs
- **Check WebSocket Connection**: Triggers require active WebSocket connection to UniFi OS
- **Verify Permissions**: Ensure your UniFi user has admin access to receive all rule change events
- **Test Both Sources**: Verify triggers work for both HA-initiated and console-initiated changes

## Service Automation Examples

### Automated Daily Backup

```yaml
alias: Backup UniFi Network Rules
description: >-
  Creates a daily backup of all policy, rule, and route JSON state to a file in 
  the Home Assistant config directory every day at 2:00 AM
triggers:
  - trigger: time_pattern
    hours: "2"
conditions: []
actions:
  - action: unifi_network_rules.backup_rules
    metadata: {}
    data:
      filename: unr_daily_backup.json
mode: single
```

### Full and Selective restore

Fully restore the state of all policies

```yaml
alias: Restore all policies from last backup
description: Restores the backed-up state of all policies, including zones, devices, objects, etc.
triggers:
  - trigger: state
    entity_id:
      - input_button.restore_unr
conditions: []
actions:
  - action: unifi_network_rules.restore_rules
    metadata: {}
    data:
      filename: unr_daily_backup.json
mode: single
```

Selectively restore rules based on name and type

```yaml
alias: Restore Kid Downtime Policies
description: Restores the backed-up state of the policies that contain the name `Block Kid`
triggers:
  - trigger: state
    entity_id:
      - input_button.restore_unr
conditions: []
actions:
  - action: unifi_network_rules.restore_rules
    metadata: {}
    data:
      filename: unr_daily_backup.json
      name_filter: Block Kid
      rule_types:
        - policy
mode: single
```

### Block Kid's devices at bedtime

Every night at 11PM, Policies or Rules that contain the name "Block Kid Internet" will `enable` and send a notification to Chris's iPhone

```yaml
alias: Daily Device Downtime
description: Block kid devices at bedtime daily
triggers:
  - trigger: time_pattern
    hours: "23"
conditions: []
actions:
  - action: unifi_network_rules.bulk_update_rules
    metadata: {}
    data:
      state: true
      name_filter: Block Kid internet
  - action: notify.mobile_app_chrisiphone
    metadata: {}
    data:
      message: Kids Device Downtime Enabled
      title: Daily Device Downtime
mode: single
```

### Temporarily Enable Game Server Access

```yaml
alias: Turn Off Minecraft Server Port after 2 hours
description: >-
  We don't want to leave this port open indefinitely, just leave open for a
  normal gaming session, then automatically turn off.
triggers:
  - trigger: state
    entity_id:
      - switch.port_forward_minecraft_10_1_1_75_4882
    from: "off"
    to: "on"
conditions: []
actions:
  - delay:
      hours: 2
      minutes: 0
      seconds: 0
      milliseconds: 0
  - action: switch.turn_off
    metadata: {}
    data: {}
    target:
      entity_id: switch.port_forward_minecraft_10_1_1_75_4882
mode: single
```

This automation uses a helper to toggle port forwarding access to a game server. When enabled, it automatically disables the port forwarding after 2 hours for security.

## Tips for Using Services

1. **Backup Organization**: Use descriptive filenames with timestamps:

   ```yaml
   filename: "UniFi_rules_{{now().strftime('%Y%m%d_%H%M')}}.json"
   ```

2. **Selective Restore**: When restoring rules, use filters to target specific rules:

   ```yaml
   action: unifi_network_rules.restore_rules
   data:
     filename: "backup.json"
     name_filter: "Guest"  # Only restore guest-related rules
     rule_types:
       - policy  # Only restore firewall policies
   ```

3. **Bulk Updates**: Use naming conventions in UniFi to make bulk updates easier:
   - Name related rules with common prefixes (e.g., "Guest_", "IoT_")
   - Use the bulk_update_rules service with name_filter to manage groups of rules

4. **Integration with Other Services**: Combine with other Home Assistant integrations:
   - Use the Folder Watcher integration to monitor backup file changes
   - Combine with the Google Drive Backup integration for offsite copies
   - Set up notifications when rule states change

## Understanding Rule Types

The UniFi Network Rules integration supports several types of rules:

1. **Firewall Policies (policy)**: Zone-based firewall rules that control traffic between different security zones (WAN, LAN, Guest, etc.). These form the backbone of your network security.

2. **Port Forwarding Rules (port_forward)**: Allow external traffic to reach specific internal devices and services by forwarding specific ports from your WAN to internal IP addresses.

3. **Traffic Routes (route)**: Control how traffic is routed through your network, typically used for VPN routing or specific network destinations. Each traffic route has two components:
   - The main switch that enables/disables the route
   - A child "kill switch" that blocks all traffic if the route is down (prevents data leakage if your VPN disconnects)

4. **Static Routes (route)**: Configure static network routes that define how traffic is routed between different network segments. These are fundamental routing table entries that determine network paths and can be enabled/disabled for network management and troubleshooting.

5. **QoS Rules (qos_rule)**: Quality of Service rules that prioritize certain types of traffic on your network. These rules can ensure critical applications (like video conferencing) get bandwidth priority over less time-sensitive applications.

6. **Port Profiles (port_profile)**: Switch port configurations that define how network ports are configured, including VLAN assignments, PoE settings, and operational modes. These control the behavior of individual switch ports.

7. **Networks (network)**: Network configurations that define VLANs and network segments in your UniFi environment. These control the fundamental network infrastructure and IP addressing schemes.

8. **Object-Oriented Network Policies (oon_policy)**: Unified policies that combine QoS, traffic routing, and security features into a single configuration. These policies provide a simplified way to manage complex network rules. OON policies can include:
   - QoS configuration (bandwidth limits, prioritization)
   - Traffic routing (VPN routing, network selection)
   - Security features (internet access controls)
   - Each OON policy with routing enabled can have a child "kill switch" that blocks all traffic if the route fails (similar to traffic route kill switches)

9. **Legacy Rules**: For older UniFi OS versions, there are also legacy_firewall and legacy_traffic rule types, which are mapped to "policy" when using the service.

## Diagnostics and Debugging

The integration includes targeted diagnostics and debugging capabilities to help troubleshoot issues while minimizing resource usage.

### Standard Logging

To enable debug logging for the entire integration, add the following to your `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.unifi_network_rules: debug
    aiounifi: debug  # Also log the underlying UniFi library
```

### Targeted Debugging

For more focused debugging of specific subsystems, you can enable only what you need by editing the constants in `custom_components/unifi_network_rules/const.py`:

- `LOG_WEBSOCKET`: Enable detailed WebSocket connection and message logs
- `LOG_API_CALLS`: Log API requests and responses
- `LOG_DATA_UPDATES`: Log data refresh and update cycles
- `LOG_ENTITY_CHANGES`: Log entity addition, removal, and state changes
- `LOG_TRIGGERS`: Log trigger detection and firing

These targeted flags help reduce log noise when troubleshooting specific issues.

### Home Assistant Diagnostics

This integration supports Home Assistant's built-in diagnostics. To access:

1. Go to Settings → Devices & Services → Integrations
2. Find the UniFi Network Rules integration
3. Click on Configure → Download Diagnostics
4. Share the generated file when reporting issues

The diagnostics provide essential information about your system configuration without exposing sensitive data.

### Temporary Websocket Health Monitor

For advanced troubleshooting of connectivity issues, the integration includes a WebSocket health monitor that can help identify connection problems with the UniFi controller.

### Temporary Enable API Call Tracing [Advanced]

To temporarily enable API call tracing for a session:

1. SSH into your Home Assistant instance
2. Enter the `/config/custom_components/unifi_network_rules` directory
3. Edit the file: `const.py`
4. Change `LOG_API_CALLS = False` to `LOG_API_CALLS = True`
5. Restart Home Assistant

*Remember to revert this change after troubleshooting to prevent excessive logging.*

> **Having trouble?** See the [Troubleshooting section](QUICKSTART.md#troubleshooting) in the Quick Start Guide.

## Limitations

This integration uses the same core library that Home Assistant Unifi integration uses, so there can be version incompatibility issues at time. We may ship with a higher version causing conflicts if you use multiple UniFi integrations. Sometimes restarting Home Assistant can help.

This will not support all the features of the UniFi controller, for that, leverage the core integration. The focus of this integration will be home and home lab use cases to extend and differentiate from the core integration.

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, the quality gate (`make check`), and the PR workflow.

Report security vulnerabilities through our [Security Policy](SECURITY.md).

***

[commits-shield]: https://img.shields.io/github/commit-activity/y/sirkirby/unifi-network-rules?style=for-the-badge
[commits]: https://github.com/sirkirby/unifi-network-rules/commits/main
[license-shield]: https://img.shields.io/github/license/sirkirby/unifi-network-rules.svg?style=for-the-badge
[maintenance-shield]: https://img.shields.io/badge/maintainer-sirkirby-blue.svg?style=for-the-badge

[hacs]: https://github.com/custom-components/hacs
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge
[discord]: https://discord.gg/Qa5fW2R
[discord-shield]: https://img.shields.io/discord/330944238910963714.svg?style=for-the-badge
[forum-shield]: https://img.shields.io/badge/community-forum-brightgreen.svg?style=for-the-badge
[forum]: https://community.home-assistant.io/

[releases]: https://github.com/sirkirby/unifi-network-rules/releases
[release-shield]: https://img.shields.io/github/v/release/sirkirby/unifi-network-rules?style=flat

[issues-shield]: https://img.shields.io/github/issues/sirkirby/unifi-network-rules?style=flat
[issues-link]: https://github.com/sirkirby/unifi-network-rules/issues

[validate-badge]: https://github.com/sirkirby/unifi-network-rules/actions/workflows/test-suite.yml/badge.svg
[validate-workflow]: https://github.com/sirkirby/unifi-network-rules/actions/workflows/test-suite.yml
