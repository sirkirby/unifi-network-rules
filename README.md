# Unifi Network Rules Custom Integration

Pulls firewall policies and traffic routes from your Unifi Dream Machine and allows you to enable/disable them in Home Assistant.

## Requirements

A Unifi Dream Machine (UDM) running network application 9.0.92 or later.

> [!NOTE]
> For version 8.x.x of the Unifi Network application, please use the v.0.3.x release of this integration.

## Installation

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=sirkirby&repository=ha-udm-rule-manager&category=integration)

OR

Copy the`custom_components/unifi_network_rules` directory to your `config/custom_components` directory.

THEN

1. Restart Home Assistant.
2. In the Home Assistant configuration page, click on "Integrations".
3. Click on the "+" button in the bottom right corner.
4. Search for "Unifi Network Rule Manager" and select it.
5. Enter credentials of a local admin user on your UDM and click on the "Submit" button.

## Configuration

**Host**: The IP address of your Unifi Dream Machine.

**Username**: The local admin account on the UDM.

**Password**: The password for the UDM account.

## Usage

Once you have configured the integration, you will be able to see the firewall policies and traffic routes configured on your Unifi Network as switches in Home Assistant. Add the switch to a custom dashboard or use it in automations just like any other Home Assistant switch.

## Local Development

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

## Limitations

The integration is currently limited to managing firewall, traffic rules, and traffic routes. It does not currently support managing other types of rules.

## Contributions

Contributions are welcome! Please feel free to submit a PR.
