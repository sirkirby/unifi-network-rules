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

# API endpoints - using v2 API endpoints where available
FIREWALL_RULE_ENDPOINT: Final = "/proxy/network/api/s/{site}/rest/firewallrule"
LEGACY_FIREWALL_RULES_ENDPOINT: Final = "/proxy/network/api/s/{site}/rest/firewallrule"

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

# Configuration
CONF_TEMPLATE_ID = "template_id"
CONF_TEMPLATE_VARIABLES = "variables"
CONF_RULE_TYPE = "rule_type"

# API Endpoints
SITE_FEATURE_MIGRATION_ENDPOINT = "/proxy/network/v2/api/site/{site}/site-feature-migration"
FIREWALL_POLICIES_ENDPOINT = "/proxy/network/v2/api/site/{site}/firewall-policies"
FIREWALL_POLICIES_DELETE_ENDPOINT = "/proxy/network/v2/api/site/{site}/firewall-policies/batch-delete"
TRAFFIC_ROUTES_ENDPOINT = "/proxy/network/v2/api/site/{site}/trafficroutes"
LEGACY_TRAFFIC_RULES_ENDPOINT = "/proxy/network/v2/api/site/{site}/trafficrules"
FIREWALL_ZONE_MATRIX_ENDPOINT = "/proxy/network/v2/api/site/{site}/firewall/zone-matrix"
FIREWALL_POLICY_TOGGLE_ENDPOINT = "/proxy/network/v2/api/site/{site}/firewall-policies/batch"
PORT_FORWARD_ENDPOINT = "/proxy/network/api/s/{site}/rest/portforward"

# V2 API EndPoint Constants for ApiRequestV2
API_ENDPOINT_FIREWALL_POLICIES = "/firewall-policies"
API_ENDPOINT_FIREWALL_POLICIES_BATCH_DELETE = "/firewall-policies/batch-delete"
API_ENDPOINT_TRAFFIC_RULES = "/trafficrules"
API_ENDPOINT_TRAFFIC_RULE_DETAIL = "/trafficrules/{rule_id}"
API_ENDPOINT_TRAFFIC_ROUTES = "/trafficroutes"
API_ENDPOINT_TRAFFIC_ROUTE_DETAIL = "/trafficroutes/{route_id}"

# Detection endpoints
SDN_STATUS_ENDPOINT = "/proxy/network/api/s/{site}/stat/sdn"

AUTH_LOGIN_ENDPOINT = "/api/auth/login"

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