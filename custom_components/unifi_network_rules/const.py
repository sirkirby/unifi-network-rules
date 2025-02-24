"""Constants for UniFi Network Rules integration."""
import logging

DOMAIN = "unifi_network_rules"

# Initialize logger at module level
LOGGER = logging.getLogger(DOMAIN)

CONF_MAX_RETRIES = "max_retries"
CONF_RETRY_DELAY = "retry_delay"
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 1

CONF_UPDATE_INTERVAL = "update_interval"
DEFAULT_UPDATE_INTERVAL = 1  # Changed from 5 to 1 minute for more responsive updates
SESSION_TIMEOUT = 30

# Site configuration
CONF_SITE = "site"
DEFAULT_SITE = "default"

# Events
EVENT_RULE_UPDATED = f"{DOMAIN}_rule_updated"
EVENT_RULE_DELETED = f"{DOMAIN}_rule_deleted"

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
LEGACY_FIREWALL_RULES_ENDPOINT = "/proxy/network/api/s/{site}/rest/firewallrule"
LEGACY_TRAFFIC_RULES_ENDPOINT = "/proxy/network/v2/api/site/{site}/trafficrules"
FIREWALL_ZONE_MATRIX_ENDPOINT = "/proxy/network/v2/api/site/{site}/firewall/zone-matrix"
FIREWALL_POLICY_TOGGLE_ENDPOINT = "/proxy/network/v2/api/site/{site}/firewall-policies/batch"
PORT_FORWARD_ENDPOINT = "/proxy/network/api/s/{site}/rest/portforward"

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