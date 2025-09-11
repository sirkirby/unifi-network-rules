"""Constants for UniFi Network Rules integration."""
from __future__ import annotations

import logging
from typing import Final

from homeassistant.const import Platform

# Integration
DOMAIN = "unifi_network_rules"
DEFAULT_NAME = "UniFi Network Rules"
MANUFACTURER = "Ubiquiti, Inc."

# Platforms
PLATFORMS = [Platform.SWITCH]

# Configuration and options
CONF_SITE = "site"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_HOST = "host"
CONF_PASSWORD = "password"
CONF_PORT = "port"
CONF_USERNAME = "username"
CONF_VERIFY_SSL = "verify_ssl"

# Smart Polling Configuration Options
CONF_SMART_POLLING_BASE_INTERVAL = "base_interval"
CONF_SMART_POLLING_ACTIVE_INTERVAL = "active_interval"
CONF_SMART_POLLING_REALTIME_INTERVAL = "realtime_interval"
CONF_SMART_POLLING_ACTIVITY_TIMEOUT = "activity_timeout"
CONF_SMART_POLLING_DEBOUNCE_SECONDS = "debounce_seconds"
CONF_SMART_POLLING_OPTIMISTIC_TIMEOUT = "optimistic_timeout"

# Default values
DEFAULT_SITE = "default"
DEFAULT_PORT = 443

# Timers and retry values
DEFAULT_UPDATE_INTERVAL: Final = 300  # 5 minutes - longer interval is fine since websocket provides real-time updates
DEFAULT_RETRY_TIMER = 30  # seconds - Time between retries for failed commands
DEFAULT_TIMEOUT = 10
DEFAULT_WEBSOCKET_RECONNECT_DELAY = 30  # seconds - Time to wait before reconnecting after websocket error

# Web Socket Events
WS_EVENT_TYPE = "type"
WS_EVENT_DATA = "data"
WS_EVENT_META = "meta"
WS_EVENT_MESSAGE = "message"

# Debug related constants
DEBUG_WEBSOCKET = False  # Set to True to enable detailed WebSocket debug logging

# Define logger
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
LOG_TRIGGERS: Final = False  # Trigger detection and firing logs - ENABLED FOR STATE-DIFF DEBUGGING

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
CONF_MAX_RETRIES = "max_retries"
CONF_RETRY_DELAY = "retry_delay"
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 1

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
BACKUP_FILE_PREFIX = "backup"
BACKUP_LOCATION = "unr/backups"  # Subdirectory in HA config directory
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
API_ENDPOINT_QOS_RULES = "/proxy/network/v2/api/site/{site}/qos-rules"
API_ENDPOINT_QOS_RULE_DETAIL = "/proxy/network/v2/api/site/{site}/qos-rules/{rule_id}"
API_ENDPOINT_QOS_RULES_BATCH = "/proxy/network/v2/api/site/{site}/qos-rules/batch"
API_ENDPOINT_NETWORK_CONF = "/proxy/network/api/s/{site}/rest/networkconf"
API_ENDPOINT_NETWORK_CONF_DETAIL = "/proxy/network/api/s/{site}/rest/networkconf/{network_id}"
# Objects and Profiles
API_ENDPOINT_OBJECTS = "/proxy/network/v2/api/site/{site}/objects"
API_ENDPOINT_OBJECT_DETAIL = "/proxy/network/v2/api/site/{site}/objects/{object_id}"
API_ENDPOINT_PORT_PROFILES = "/proxy/network/api/s/{site}/rest/portconf"
API_ENDPOINT_PORT_PROFILE_DETAIL = "/proxy/network/api/s/{site}/rest/portconf/{profile_id}"
API_ENDPOINT_WLAN_RATE_PROFILES = "/proxy/network/v2/api/site/{site}/profiles/wlanrate"
API_ENDPOINT_WLAN_RATE_PROFILE_DETAIL = "/proxy/network/v2/api/site/{site}/profiles/wlanrate/{profile_id}"
API_ENDPOINT_RADIUS_PROFILES = "/proxy/network/api/s/{site}/rest/radiusprofile"
API_ENDPOINT_RADIUS_PROFILE_DETAIL = "/proxy/network/api/s/{site}/rest/radiusprofile/{profile_id}"
API_ENDPOINT_WAN_SLA_PROFILES = "/proxy/network/v2/api/site/{site}/profiles/wansla"
API_ENDPOINT_WAN_SLA_PROFILE_DETAIL = "/proxy/network/v2/api/site/{site}/profiles/wansla/{profile_id}"

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
API_PATH_QOS_RULES = "/qos-rules"
API_PATH_QOS_RULE_DETAIL = "/qos-rules/{rule_id}"
API_PATH_QOS_RULES_BATCH = "/qos-rules/batch"
API_PATH_QOS_RULES_BATCH_DELETE = "/qos-rules/batch-delete"
API_PATH_NETWORK_CONF = "/rest/networkconf"
API_PATH_NETWORK_CONF_DETAIL = "/rest/networkconf/{network_id}"
# Objects and Profiles (aiounifi path fragments)
API_PATH_PORT_PROFILES = "/rest/portconf"
API_PATH_PORT_PROFILE_DETAIL = "/rest/portconf/{profile_id}"
API_PATH_WLAN_RATE_PROFILES = "/profiles/wlanrate"
API_PATH_WLAN_RATE_PROFILE_DETAIL = "/profiles/wlanrate/{profile_id}"
API_PATH_RADIUS_PROFILES = "/rest/radiusprofile"
API_PATH_RADIUS_PROFILE_DETAIL = "/rest/radiusprofile/{profile_id}"
API_PATH_WAN_SLA_PROFILES = "/profiles/wansla"
API_PATH_WAN_SLA_PROFILE_DETAIL = "/profiles/wansla/{profile_id}"
API_PATH_FIREWALL_GROUPS = "/rest/firewallgroup"
API_PATH_FIREWALL_GROUP_DETAIL = "/rest/firewallgroup/{group_id}"

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
SWITCH_DELAYED_VERIFICATION_SLEEP_SECONDS = 20