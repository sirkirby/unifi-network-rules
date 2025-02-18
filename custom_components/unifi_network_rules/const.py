DOMAIN = "unifi_network_rules"

CONF_MAX_RETRIES = "max_retries"
CONF_RETRY_DELAY = "retry_delay"
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 1

CONF_UPDATE_INTERVAL = "update_interval"
DEFAULT_UPDATE_INTERVAL = 1  # Changed from 5 to 1 minute for more responsive updates
SESSION_TIMEOUT = 30

# API Endpoints
SITE_FEATURE_MIGRATION_ENDPOINT = "/proxy/network/v2/api/site/default/site-feature-migration"
FIREWALL_POLICIES_ENDPOINT = "/proxy/network/v2/api/site/default/firewall-policies"
FIREWALL_POLICIES_DELETE_ENDPOINT = "/proxy/network/v2/api/site/default/firewall-policies/batch-delete"
TRAFFIC_ROUTES_ENDPOINT = "/proxy/network/v2/api/site/default/trafficroutes"
LEGACY_FIREWALL_RULES_ENDPOINT = "/proxy/network/api/s/default/rest/firewallrule"
LEGACY_TRAFFIC_RULES_ENDPOINT = "/proxy/network/v2/api/site/default/trafficrules"
FIREWALL_ZONE_MATRIX_ENDPOINT = "/proxy/network/v2/api/site/default/firewall/zone-matrix"
FIREWALL_POLICY_TOGGLE_ENDPOINT = "/proxy/network/v2/api/site/default/firewall-policies/batch"
AUTH_LOGIN_ENDPOINT = "/api/auth/login"
PORT_FORWARD_ENDPOINT = "/proxy/network/api/s/default/rest/portforward"

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