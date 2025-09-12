"""Configuration constants for UniFi Network Rules."""
from __future__ import annotations

from typing import Final

# Configuration and options
CONF_SITE: Final = "site"
CONF_UPDATE_INTERVAL: Final = "update_interval"
CONF_HOST: Final = "host"
CONF_PASSWORD: Final = "password"
CONF_PORT: Final = "port"
CONF_USERNAME: Final = "username"
CONF_VERIFY_SSL: Final = "verify_ssl"

# Smart Polling Configuration Options
CONF_SMART_POLLING_BASE_INTERVAL: Final = "base_interval"
CONF_SMART_POLLING_ACTIVE_INTERVAL: Final = "active_interval"
CONF_SMART_POLLING_REALTIME_INTERVAL: Final = "realtime_interval"
CONF_SMART_POLLING_ACTIVITY_TIMEOUT: Final = "activity_timeout"
CONF_SMART_POLLING_DEBOUNCE_SECONDS: Final = "debounce_seconds"
CONF_SMART_POLLING_OPTIMISTIC_TIMEOUT: Final = "optimistic_timeout"

# Config entry keys
CONF_SITE_ID: Final = "site_id"
CONF_MAX_RETRIES: Final = "max_retries"
CONF_RETRY_DELAY: Final = "retry_delay"
DEFAULT_MAX_RETRIES: Final = 3
DEFAULT_RETRY_DELAY: Final = 1

# Configuration
CONF_TEMPLATE_ID: Final = "template_id"
CONF_TEMPLATE_VARIABLES: Final = "variables"
CONF_RULE_TYPE: Final = "rule_type"

# Backup and Restore
BACKUP_FILE_PREFIX: Final = "backup"
BACKUP_LOCATION: Final = "unr/backups"  # Subdirectory in HA config directory
CONF_FILENAME: Final = "network_rules.json"
CONF_RULE_IDS: Final = ""
CONF_NAME_FILTER: Final = ""
CONF_RULE_TYPES: Final = ""

# Web Socket Events
WS_EVENT_TYPE: Final = "type"
WS_EVENT_DATA: Final = "data"
WS_EVENT_META: Final = "meta"
WS_EVENT_MESSAGE: Final = "message"

# Events
EVENT_RULE_UPDATED: Final = "unifi_network_rules_rule_updated"
EVENT_RULE_DELETED: Final = "unifi_network_rules_rule_deleted"

# Services
SERVICE_APPLY_TEMPLATE: Final = "apply_template"
SERVICE_SAVE_TEMPLATE: Final = "save_template"
SERVICE_SYNC_DEVICE: Final = "sync_device"
SERVICE_REFRESH_ALL: Final = "refresh_all"

# Signal dispatchers
SIGNAL_ADD_FIREWALL_RULE: Final = "unifi_network_rules_add_firewall_rule"

# Authentication and headers
ZONE_BASED_FIREWALL_FEATURE: Final = "ZONE_BASED_FIREWALL"
COOKIE_TOKEN: Final = "TOKEN"

# Headers
DEFAULT_HEADERS: Final = {
    "Accept": "application/json",
    "Content-Type": "application/json"
}
