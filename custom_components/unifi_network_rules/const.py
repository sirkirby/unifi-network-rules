"""Constants for UniFi Network Rules integration."""
from __future__ import annotations

import logging
from typing import Final

# Integration
DOMAIN: Final = "unifi_network_rules"
MANUFACTURER: Final = "Ubiquiti Inc."
LOGGER = logging.getLogger(__package__)

# Debugging flags - set specific flags to True only when troubleshooting that area
# These can also be enabled via configuration.yaml:
# logger:
#   logs:
#     custom_components.unifi_network_rules: debug
#     aiounifi: debug

# More targeted debugging flags - enable only what you need
LOG_WEBSOCKET: Final = False  # WebSocket connection/reconnection logs
LOG_API_CALLS: Final = False  # API requests and responses
LOG_DATA_UPDATES: Final = False  # Data refresh and update cycles 
LOG_ENTITY_CHANGES: Final = False  # Entity addition/removal/state changes

# For backwards compatibility - will be removed in a future update
# Use LOG_WEBSOCKET instead
DEBUG_WEBSOCKET: Final = LOG_WEBSOCKET  # Use LOG_WEBSOCKET instead

# Integration services
SERVICE_SYNC_DEVICE: Final = "sync_device"
SERVICE_REFRESH_ALL: Final = "refresh_all"

# Signal dispatchers
SIGNAL_WEBSOCKET_EVENT = "unifi_network_rules_websocket"
SIGNAL_ADD_FIREWALL_RULE = "unifi_network_rules_add_firewall_rule"

# Default UniFi site
DEFAULT_SITE: Final = "default"

# Data update interval
DEFAULT_UPDATE_INTERVAL: Final = 300  # 5 minutes - longer interval is fine since websocket provides real-time updates

# Maximum number of failed attempts
MAX_FAILED_ATTEMPTS: Final = 5

# Config entry keys
CONF_SITE_ID: Final = "site_id"
CONF_UPDATE_INTERVAL: Final = "update_interval"
CONF_MAX_RETRIES = "max_retries"
CONF_RETRY_DELAY = "retry_delay"
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 1
CONF_UPDATE_INTERVAL = "update_interval"
DEFAULT_UPDATE_INTERVAL = 300  # 5 minutes - longer interval is fine since websocket provides real-time updates
SESSION_TIMEOUT = 30

# Site configuration
CONF_SITE = "site"
DEFAULT_SITE = "default"

# Events
EVENT_RULE_UPDATED = f"{DOMAIN}_rule_updated"
EVENT_RULE_DELETED = f"{DOMAIN}_rule_deleted"

# WebSocket signals
SIGNAL_WEBSOCKET_EVENT = f"{DOMAIN}_websocket_event"

# Services
SERVICE_APPLY_TEMPLATE = "apply_template"
SERVICE_SAVE_TEMPLATE = "save_template"

# Backup and Restore
BACKUP_FILE_PREFIX = "unr_backup"
BACKUP_LOCATION = "/"
CONF_FILENAME = "network_rules.json"
CONF_RULE_IDS = ""
CONF_NAME_FILTER = ""
CONF_RULE_TYPES = ""

# Configuration
CONF_TEMPLATE_ID = "template_id"
CONF_TEMPLATE_VARIABLES = "variables"
CONF_RULE_TYPE = "rule_type"

# API Endpoints
API_ENDPOINT_SITE_FEATURE_MIGRATION = "/site-feature-migration"
API_ENDPOINT_FIREWALL_POLICIES = "/firewall-policies"
API_ENDPOINT_FIREWALL_POLICIES_BATCH_UPDATE = "/proxy/network/v2/api/site/{site}/firewall-policies/batch"
API_ENDPOINT_FIREWALL_POLICIES_BATCH_DELETE = "/firewall-policies/batch-delete"
API_ENDPOINT_TRAFFIC_ROUTES  = "/proxy/network/v2/api/site/{site}/trafficroutes"
API_ENDPOINT_TRAFFIC_ROUTES_DETAIL = "/proxy/network/v2/api/site/{site}/trafficroutes/{route_id}"
API_ENDPOINT_LEGACY_TRAFFIC_RULES = "/proxy/network/v2/api/site/{site}/trafficrules"
API_ENDPOINT_LEGACY_TRAFFIC_RULES_DETAIL = "/proxy/network/v2/api/site/{site}/trafficrules/{rule_id}"
API_ENDPOINT_LEGACY_FIREWALL_RULES = "/proxy/network/api/s/{site}/rest/firewallrule"
API_ENDPOINT_LEGACY_FIREWALL_RULES_DETAIL = "/proxy/network/api/s/{site}/rest/firewallrule/{rule_id}"
API_ENDPOINT_FIREWALL_ZONES = "/proxy/network/v2/api/site/{site}/firewall/zones"
API_ENDPOINT_WLANS = "/proxy/network/api/s/{site}/rest/wlanconf"
API_ENDPOINT_WLAN_DETAIL = "/proxy/network/api/s/{site}/rest/wlanconf/{wlan_id}"
API_ENDPOINT_FIREWALL_ZONE_MATRIX = "/proxy/network/v2/api/site/{site}/firewall/zone-matrix"
API_ENDPOINT_PORT_FORWARD = "/proxy/network/api/s/{site}/rest/portforward"
API_ENDPOINT_PORT_FORWARD_DETAIL = "/proxy/network/api/s/{site}/rest/portforward/{forward_id}"

# API Paths used for aiounifi API Requests
API_PATH_FIREWALL_POLICIES = "/firewall-policies"
API_PATH_FIREWALL_POLICIES_BATCH_DELETE = "/firewall-policies/batch-delete"
API_PATH_FIREWALL_POLICIES_BATCH_UPDATE = "/firewall-policies/batch"
API_PATH_LEGACY_TRAFFIC_RULES = "/trafficrules"
API_PATH_LEGACY_TRAFFIC_RULE_DETAIL = "/trafficrules/{rule_id}"
API_PATH_LEGACY_FIREWALL_RULES = "/firewallrule"
API_PATH_LEGACY_FIREWALL_RULE_DETAIL = "/firewallrule/{rule_id}"
API_PATH_TRAFFIC_ROUTES = "/trafficroutes"
API_PATH_TRAFFIC_ROUTE_DETAIL = "/trafficroutes/{route_id}"
API_PATH_PORT_FORWARDS = "/portforward"
API_PATH_PORT_FORWARD_DETAIL = "/portforward/{forward_id}"
API_PATH_FIREWALL_ZONES = "/firewall/zones"
API_PATH_FIREWALL_ZONE_MATRIX = "/firewall/zone-matrix"
API_PATH_WLANS = "/wlanconf"
API_PATH_WLAN_DETAIL = "/wlanconf/{wlan_id}"
API_PATH_SITE_FEATURE_MIGRATION = "/site-feature-migration"

# Detection endpoints
API_ENDPOINT_SDN_STATUS = "/proxy/network/api/s/{site}/stat/sdn"

API_ENDPOINT_AUTH_LOGIN = "/api/auth/login"

ZONE_BASED_FIREWALL_FEATURE = "ZONE_BASED_FIREWALL"

COOKIE_TOKEN = "TOKEN"

# Headers
DEFAULT_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json"
}

# Rate limiting and delays
MIN_REQUEST_INTERVAL = 2.0
STATE_VERIFICATION_SLEEP_SECONDS = 2