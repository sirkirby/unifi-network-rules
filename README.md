# Unifi Network Rules Custom Integration

Pulls user-defined firewall policies and traffic routes from your Unifi Dream Machine/Router and allows you to enable/disable them as switches in Home Assistant. It will ignore pre-defined firewall policies to keep the amount of entities manageable.

## Requirements

A Unifi device running network application 9.0.92 or later.

> [!NOTE]
> For version 8.x.x of the Unifi Network application, please use the v.0.3.x release of this integration.

A local account with Admin privileges to the network application. Must not be a UniFi Cloud account.

## Installation

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=sirkirby&repository=unifi-network-rules&category=integration)

If you don't or can't use HACS, alternatively, copy the `custom_components/unifi_network_rules` directory to your `config/custom_components` directory.

I recommend installing the Studio Code Server addon to make it easier to copy in the custom component directly in the Home Assistant UI. `Settings -> Add-ons -> Studio Code Server -> Install`. The turn on `Show in Sidebar`.

THEN

1. Restart Home Assistant.
2. In the Home Assistant configuration page, click on "Integrations".
3. Click on the "+" button in the bottom right corner.
4. Search for "Unifi Network Rule Manager" and select it.
5. Enter credentials of a local admin user on your UDM and click on the "Submit" button.

## Configuration

**Host**: The IP address of your Unifi Device. Avoid using the hostname as it may not work.

**Username**: The local admin account on the UDM.

**Password**: The password for the UDM account.

**Updated Interval**: The automatic refresh interval in minutes.

## Usage

Once you have configured the integration, you will be able to see the firewall policies and traffic routes configured on your Unifi Network as switches in Home Assistant. Add the switch to a custom dashboard or use it in automations just like any other Home Assistant switch.

## Network Mode Detection

The integration automatically detects the UniFi network configuration mode:

- If zone-based firewall is detected, UniFi Network 9.0.92+ and opted to migrate, the integration will manage firewall policies using the new API.
- If legacy mode is detected, UniFi Network 8+ and do not have zone-based option or opted to not migrate, the integration will manage legacy firewall and traffic rules.
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
automation:
  - alias: "Refresh UniFi Rules when Button Pressed"
    trigger:
      platform: state
      entity_id: input_button.refresh_unifi_rules
    action:
      - service: unifi_network_rules.refresh
```

### Method 2: Using Scripts with a Lovelace Button Card (More Customizable)

First, create a script in your `configuration.yaml`:

```yaml
script:
  backup_unifi_rules:
    sequence:
      - service: unifi_network_rules.backup_rules
        data:
          filename: "unifi_rules_backup.json"
```

Then add a button card to your dashboard that references the script:
```yaml
type: button
name: Backup Rules
tap_action:
  action: call-service
  service: script.turn_on
  service_data:
    entity_id: script.backup_unifi_rules
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
alias: Backup UniFi Network Rule State
description: >-
  Creates a daily backup of all policy, rule, and route JSON state to a file in 
  the Home Assistant config directory every day at 2:00 AM
trigger:
  - platform: time
    at: "02:00:00"
action:
  - service: unifi_network_rules.backup_rules
    data:
      filename: unifi_rules_daily_backup.json

mode: single
```

### Guest Network Security Automation
```yaml
alias: Guest Network After Hours
description: Disable guest network access during off-hours
trigger:
  - platform: time
    at: "23:00:00"
action:
  - service: unifi_network_rules.bulk_update_rules
    data:
      name_filter: "Guest Network"
      state: false
  - service: notify.mobile_app
    data:
      message: "Guest network rules disabled for the night"
mode: single
```

### Regular Refresh with Backup
```yaml
alias: Regular UniFi Rules Refresh and Backup
description: >-
  Refreshes rule states every 8 hours and creates a backup if changes are detected
trigger:
  - platform: time_pattern
    hours: "/8"
action:
  - service: unifi_network_rules.refresh
  - delay: 
      seconds: 10
  - service: unifi_network_rules.backup_rules
    data:
      filename: "unifi_rules_latest.json"

mode: single
```

## Tips for Using Services

1. **Backup Organization**: Use descriptive filenames with timestamps:
   ```yaml
   filename: "unifi_rules_{{now().strftime('%Y%m%d_%H%M')}}.json"
   ```

2. **Selective Restore**: When restoring rules, use filters to target specific rules:
   ```yaml
   service: unifi_network_rules.restore_rules
   data:
     filename: "backup.json"
     name_filter: "Guest"  # Only restore guest-related rules
     rule_types: ["policy"]  # Only restore firewall policies
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

You can do this by logging into your Unifi device locally or via <https://unifi.ui.com>, navigate to Settings -> Admins & Users, and checking the local user's permissions. It should be Admin or Super Admin for the network application.

### Open a bug issue

If you are having trouble getting the integration to work, please open an [Issue](https://github.com/sirkirby/unifi-network-rules/issues) using the bug report template. Please enable debug logging and include the full log output in your report. Note that it may contain sensitive network information, so please review it before posting. The logs can be large, so i recommend attaching them as a file.

To get the debug log, navigate Devices and Services -> Unifi Network Rules -> Enable Debug Logging. Then reload the integration and try to reproduce the issue. Finally, disable debug logging and download the log file.

## Limitations

The integration supports:
- Zone-based firewall policies with full CRUD operations (create, read, update, delete) on UniFi OS 9.0.92+
- OR Legacy firewall rules (read and update) on pre-9.0.92 systems
- Traffic routes (read and update) on all systems

Note: The new service operations (create/delete) are only available for zone-based firewall policies. Legacy rule support will be used automatically on older systems.

## Contributions

Contributions are welcome! Please read our [Contributing Guidelines](CONTRIBUTING.md) and feel free to submit a PR.
