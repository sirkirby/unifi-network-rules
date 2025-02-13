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

The integration provides several services that can be used as buttons in your dashboards or in automations:

### Refresh Rules

Manually refresh the state of all network rules. Useful if you've made changes directly in the UniFi interface.

Example button card configuration:
```yaml
type: button
name: Refresh Rules
tap_action:
  action: call-service
  service: unifi_network_rules.refresh
```

### Backup Rules

Create a backup of all your firewall policies and traffic routes. The backup will be stored in your Home Assistant config directory.

Example button card configuration:
```yaml
type: button
name: Backup Rules
tap_action:
  action: call-service
  service: unifi_network_rules.backup_rules
  data:
    filename: "unifi_rules_backup.json"
```

### Restore Rules

Restore rules from a previously created backup file. You can selectively restore specific rules by their IDs, names, or rule types.

Example button card configuration for full restore:
```yaml
type: button
name: Restore Rules
tap_action:
  action: call-service
  service: unifi_network_rules.restore_rules
  data:
    filename: "unifi_rules_backup.json"
```

Example selective restore by name:
```yaml
type: button
name: Restore Guest Rules
tap_action:
  action: call-service
  service: unifi_network_rules.restore_rules
  data:
    filename: "unifi_rules_backup.json"
    name_filter: "Guest"
    rule_types: ["policy"]
```

### Bulk Update Rules

Enable or disable multiple rules at once by matching their names.

Example button card configuration:
```yaml
type: button
name: Disable Guest Network Rules
tap_action:
  action: call-service
  service: unifi_network_rules.bulk_update_rules
  data:
    name_filter: "Guest"
    state: false
```

### Create Rule from Template

Create a new firewall policy from a template. Currently supports only firewall policies.

Example template for a firewall policy:
```yaml
service: unifi_network_rules.create_from_template
data:
  rule_type: "policy"
  template:
    name: "Block Social Media"
    enabled: true
    action: "deny"
    description: "Block access to social media sites"
    match_rules:
      - type: "domain"
        values: ["facebook.com", "twitter.com", "instagram.com"]
```

### Delete Rule

Delete an existing firewall policy by its ID. Currently supports only firewall policies.

Example service call:
```yaml
service: unifi_network_rules.delete_rule
data:
  rule_id: "abc123def456"
  rule_type: "policy"
```

You can add these buttons to your dashboard by:
1. Edit your dashboard
2. Click the + button to add a card
3. Choose "Button"
4. Configure using the examples above

## Template Examples

Here are some common rule templates you can use:

### Guest Network Isolation
```yaml
service: unifi_network_rules.create_from_template
data:
  rule_type: policy
  template:
    name: Guest Network Isolation
    enabled: true
    action: deny
    description: "Prevent guest network access to internal network"
    match_rules:
      - type: network
        values: ["Guest Network"]
      - type: destination
        values: ["192.168.1.0/24"]
```

### Time-Based Gaming Route
```yaml
service: unifi_network_rules.create_from_template
data:
  rule_type: route
  template:
    name: Gaming Traffic - Peak Hours
    enabled: true
    description: "Prioritize gaming traffic during peak evening hours"
    match_rules:
      - type: port
        values: ["3074", "3075", "3076"]  # Common gaming ports
    priority: 1000
    schedule:
      days: ["mon", "tue", "wed", "thu", "fri"]
      start_time: "18:00"
      end_time: "23:00"
```

### IoT Device Restriction
```yaml
service: unifi_network_rules.create_from_template
data:
  rule_type: policy
  template:
    name: IoT Device Restrictions
    enabled: true
    action: deny
    description: "Restrict IoT devices to DNS only"
    match_rules:
      - type: group
        values: ["IoT Devices"]
      - type: destination
        values: ["!8.8.8.8", "!8.8.4.4"]  # Only allow DNS
      - type: port
        values: ["!53"]  # Only allow DNS port
```

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

### Backup Before Updates
```yaml
alias: Backup UniFi Rules Before Update
description: >-
  Automatically backup rules when UniFi OS updates are detected
trigger:
  - platform: event
    event_type: unifi_os_update_detected  # requires UniFi integration
action:
  - service: unifi_network_rules.backup_rules
    data:
      filename: "unifi_rules_pre_update_{{now().strftime('%Y%m%d')}}.json"
  - service: notify.mobile_app_your_phone  # customize this
    data:
      message: "UniFi rules backed up before system update"
      
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

1. **Multiple Backups**: Consider using timestamps in your backup filenames to maintain a history:
   ```yaml
   filename: "unifi_rules_{{now().strftime('%Y%m%d_%H%M')}}.json"
   ```

2. **Combine with Other Integrations**: The services work well with other Home Assistant integrations:
   - Use with the Folder Watcher integration to monitor backup file changes
   - Combine with the Google Drive Backup integration to ensure offsite copies
   - Set up notifications when backups complete or restores are performed

3. **Recovery Strategy**: Create an automation that:
   1. Backs up current rules
   2. Attempts to restore from a known good backup
   3. Notifies you of the result

4. **Version Control**: Store your backups in a version-controlled location by combining with the Git integration

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
