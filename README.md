# UniFi Network Rules Custom Integration

[![License][license-shield]](LICENSE)
![Project Maintenance][maintenance-shield]
[![GitHub Activity][commits-shield]][commits]

[![GitHub Release][release-shield]][releases]
[![issues][issues-shield]][issues-link]
[![validate-badge]][validate-workflow]

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/sirkirby)

Pulls user-defined firewall policies and traffic routes from your UniFi Dream Machine/Router and allows you to enable/disable them and build more sophisticated automations in Home Assistant.

## Requirements

A UniFi device running network application 9.0.92 or later.

A local account with Admin privileges to the network application. Must not be a UniFi Cloud account.

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

## Configuration

**Host**: The IP address of your UniFi Device. Avoid using the hostname as it may not work.

**Username**: The local admin account on the UDM.

**Password**: The password for the UDM account.

**Updated Interval**: The automatic refresh interval in minutes.

## Usage

Once you have configured the integration, you will be able to see the firewall policies and traffic routes configured on your UniFi Network as switches in Home Assistant. Add the switch to a custom dashboard or use it in automations just like any other Home Assistant switch.

## Network Mode Detection

The integration automatically detects the UniFi network configuration mode:

- If a zone-based firewall is detected (available in UniFi Network 9.0.92+ systems that have migrated), the integration will manage firewall policies using the new API.
- If legacy mode is detected (on UniFi Network 8+ systems that either lack the zone-based option or have opted not to migrate), the integration will manage legacy firewall and traffic rules.
- Traffic routes are managed the same way in both modes.

Migration from legacy mode to zone-based firewall is handled by UniFi OS. After migration, legacy rules become policies and the integration will automatically switch to managing them as policies.

## Services

The integration provides several services focused on managing and automating existing UniFi Network rules:

### Method 1: Using an Input Button Helper with Automation

This is the simplest method:

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
  - action: UniFi_network_rules.backup_rules
    metadata: {}
    data:
      filename: unr_daily_backup.json
mode: single
```
<img src="./assets/backup_unr_button.png" alt="Backup UNR Button" width="200" />

### Method 2: Using Scripts with a Lovelace Button Card (More Customizable)

First, create a script in your Settings → Automations & Scenes → Scripts:

```yaml
sequence:
  - sequence:
      - action: UniFi_network_rules.backup_rules
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
  perform_action: script.backup_my_UniFi_rules
  target: {}
name: Backup my Network Rules
icon: mdi:cloud-upload
```

### Available Services

#### Refresh Rules
Manually refresh the state of all network rules. Useful if you've made changes directly in the UniFi interface.

#### Backup Rules
Create a backup of all your firewall policies and traffic routes. The backup will be stored in your Home Assistant config directory.

#### Restore Rules
Restore rules from a previously created backup file. You can selectively restore specific rules by their IDs, names, or rule types.

#### Bulk Update Rules
Enable or disable multiple rules at once by matching their names. This is useful for automating rule management based on conditions or schedules.

#### Delete Rule
Delete an existing zone-based firewall policy by its ID. Only available for UniFi OS 9.0.92+ with zone-based firewall enabled.

## Automation Examples

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
  - action: UniFi_network_rules.backup_rules
    metadata: {}
    data:
      filename: unr_daily_backup.json
mode: single
```

### Full and Selective backups
**Fully restore the state of all policies**
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

**Selectively restore rules based on name and type**
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
  - action: UniFi_network_rules.bulk_update_rules
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
   action: UniFi_network_rules.restore_rules
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

## Local Development

### Testing

To run the tests, you need to install the dependencies in the `requirements_test.txt` file.

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements_test.txt
```

Then run the tests:

```bash
pytest tests
```

### API Testing

We've created a [Bruno](https://github.com/sirkirby/bruno-udm-api) collection to manually test the API requests. These are the same requests that the integration makes. This is a great way to verify your credentials are valid and to verify device connectivity and compatibility.

## Troubleshooting

If you are having trouble getting the integration to work, please check the following:

1. Ensure the UDM is running the latest version of the network application.
2. Ensure the UDM is connected to the same network as your Home Assistant instance.
3. Ensure you are using the IP address of the UDM, not the hostname.
4. Verify your local account has proper admin privileges.

### Verify your local account is working

Run this on a computer connected to the same network as your UDM or directly on your Home Assistant instance to verify connectivity to the UDM and that your credentials are valid.

```bash
curl -k -X POST https://[UDM-IP]/api/auth/login \
-H "Content-Type: application/json" \
-d '{"username":"[USERNAME]","password":"[PASSWORD]"}' 
```

Possible responses:

- 200 OK: Credentials are valid. Returns a JSON object with the user's information.
- 401 Unauthorized: Credentials are invalid.
- 429 Too Many Requests: The user has made too many requests in a short period of time. Wait a few minutes and try again.

### Verify your account has admin privileges

You can do this by logging into your UniFi device locally or via <https://UniFi.ui.com>, navigate to Settings -> Admins & Users, and checking the local user's permissions. It should be Admin or Super Admin for the network application.

### Open a bug issue

If you are having trouble getting the integration to work, please open an [Issue](https://github.com/sirkirby/UniFi-network-rules/issues) using the bug report template. Please enable debug logging and include the full log output in your report. Note that it may contain sensitive network information, so please review it before posting. The logs can be large, so i recommend attaching them as a file.

To get the debug log, navigate Devices and Services -> UniFi Network Rules -> Enable Debug Logging. Then reload the integration and try to reproduce the issue. Finally, disable debug logging and download the log file.

## Limitations

The integration supports:
- Zone-based firewall policies with full CRUD operations (create, read, update, delete) on UniFi OS 9.0.92+
- OR Legacy firewall rules (read and update) on pre-9.0.92 systems
- Traffic routes (read and update) on all systems
- Port forwarding rules (read and update) on all systems

Note: The new service operations (create/delete) are only available for zone-based firewall policies. Legacy rule support will be used automatically on older systems.

## Port Forwarding Rules

The integration now supports managing port forwarding rules from your UniFi Dream Machine/Router. Each port forwarding rule is represented as a switch entity that lets you enable or disable it. The rule name includes:
- The name you assigned in UniFi
- The protocol (TCP, UDP, or both)
- The port configuration (e.g., "port 80->80" or "port 80->8080")
- The destination IP address

Example entity name: `Port Forward: Minecraft (tcp_udp port 25565 to 10.29.13.235)`

Note: Creating new port forwarding rules through the integration is only supported for backup/restore purposes. Configure new rules through the UniFi interface.

## Contributions

Contributions are welcome! Please read our [Contributing Guidelines](CONTRIBUTING.md) and feel free to submit a PR.

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

[validate-badge]: https://github.com/sirkirby/unifi-network-rules/actions/workflows/python-tests.yml/badge.svg
[validate-workflow]: https://github.com/sirkirby/unifi-network-rules/actions/workflows/python-tests.yml