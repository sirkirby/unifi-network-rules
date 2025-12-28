"""API endpoint constants for UniFi Network Rules."""

from __future__ import annotations

from typing import Final

# API Endpoints
API_ENDPOINT_SITE_FEATURE_MIGRATION: Final = "/site-feature-migration"
API_ENDPOINT_FIREWALL_POLICIES: Final = "/firewall-policies"
API_ENDPOINT_FIREWALL_POLICIES_BATCH_UPDATE: Final = "/proxy/network/v2/api/site/{site}/firewall-policies/batch"
API_ENDPOINT_FIREWALL_POLICIES_BATCH_DELETE: Final = "/firewall-policies/batch-delete"
API_ENDPOINT_TRAFFIC_ROUTES: Final = "/proxy/network/v2/api/site/{site}/trafficroutes"
API_ENDPOINT_TRAFFIC_ROUTES_DETAIL: Final = "/proxy/network/v2/api/site/{site}/trafficroutes/{route_id}"
API_ENDPOINT_LEGACY_TRAFFIC_RULES: Final = "/proxy/network/v2/api/site/{site}/trafficrules"
API_ENDPOINT_LEGACY_TRAFFIC_RULES_DETAIL: Final = "/proxy/network/v2/api/site/{site}/trafficrules/{rule_id}"
API_ENDPOINT_LEGACY_FIREWALL_RULES: Final = "/proxy/network/api/s/{site}/rest/firewallrule"
API_ENDPOINT_LEGACY_FIREWALL_RULES_DETAIL: Final = "/proxy/network/api/s/{site}/rest/firewallrule/{rule_id}"
API_ENDPOINT_FIREWALL_ZONES: Final = "/proxy/network/v2/api/site/{site}/firewall/zones"
API_ENDPOINT_WLANS: Final = "/proxy/network/api/s/{site}/rest/wlanconf"
API_ENDPOINT_WLAN_DETAIL: Final = "/proxy/network/api/s/{site}/rest/wlanconf/{wlan_id}"
API_ENDPOINT_FIREWALL_ZONE_MATRIX: Final = "/proxy/network/v2/api/site/{site}/firewall/zone-matrix"
API_ENDPOINT_PORT_FORWARD: Final = "/proxy/network/api/s/{site}/rest/portforward"
API_ENDPOINT_PORT_FORWARD_DETAIL: Final = "/proxy/network/api/s/{site}/rest/portforward/{forward_id}"
API_ENDPOINT_QOS_RULES: Final = "/proxy/network/v2/api/site/{site}/qos-rules"
API_ENDPOINT_QOS_RULE_DETAIL: Final = "/proxy/network/v2/api/site/{site}/qos-rules/{rule_id}"
API_ENDPOINT_QOS_RULES_BATCH: Final = "/proxy/network/v2/api/site/{site}/qos-rules/batch"
API_ENDPOINT_NETWORK_CONF: Final = "/proxy/network/api/s/{site}/rest/networkconf"
API_ENDPOINT_NETWORK_CONF_DETAIL: Final = "/proxy/network/api/s/{site}/rest/networkconf/{network_id}"
API_ENDPOINT_NAT_RULES: Final = "/proxy/network/v2/api/site/{site}/nat"
API_ENDPOINT_NAT_RULE_DETAIL: Final = "/proxy/network/v2/api/site/{site}/nat/{rule_id}"
API_ENDPOINT_OON_POLICIES: Final = (
    "/proxy/network/v2/api/site/{site}/object-oriented-network-configs"  # GET uses plural
)
API_ENDPOINT_OON_POLICY_DETAIL: Final = (
    "/proxy/network/v2/api/site/{site}/object-oriented-network-config/{policy_id}"  # PUT/DELETE use singular
)
API_ENDPOINT_OON_POLICY: Final = (
    "/proxy/network/v2/api/site/{site}/object-oriented-network-config"  # POST uses singular
)

# Static Routes (V1 API)
API_ENDPOINT_STATIC_ROUTES: Final = "/proxy/network/api/s/{site}/rest/routing"
API_ENDPOINT_STATIC_ROUTE_DETAIL: Final = "/proxy/network/api/s/{site}/rest/routing/{route_id}"

# Objects and Profiles
API_ENDPOINT_OBJECTS: Final = "/proxy/network/v2/api/site/{site}/objects"
API_ENDPOINT_OBJECT_DETAIL: Final = "/proxy/network/v2/api/site/{site}/objects/{object_id}"
API_ENDPOINT_PORT_PROFILES: Final = "/proxy/network/api/s/{site}/rest/portconf"
API_ENDPOINT_PORT_PROFILE_DETAIL: Final = "/proxy/network/api/s/{site}/rest/portconf/{profile_id}"
API_ENDPOINT_WLAN_RATE_PROFILES: Final = "/proxy/network/v2/api/site/{site}/profiles/wlanrate"
API_ENDPOINT_WLAN_RATE_PROFILE_DETAIL: Final = "/proxy/network/v2/api/site/{site}/profiles/wlanrate/{profile_id}"
API_ENDPOINT_RADIUS_PROFILES: Final = "/proxy/network/api/s/{site}/rest/radiusprofile"
API_ENDPOINT_RADIUS_PROFILE_DETAIL: Final = "/proxy/network/api/s/{site}/rest/radiusprofile/{profile_id}"
API_ENDPOINT_WAN_SLA_PROFILES: Final = "/proxy/network/v2/api/site/{site}/profiles/wansla"
API_ENDPOINT_WAN_SLA_PROFILE_DETAIL: Final = "/proxy/network/v2/api/site/{site}/profiles/wansla/{profile_id}"

# API Paths used for aiounifi API Requests
API_PATH_FIREWALL_POLICIES: Final = "/firewall-policies"
API_PATH_FIREWALL_POLICIES_BATCH_DELETE: Final = "/firewall-policies/batch-delete"
API_PATH_FIREWALL_POLICIES_BATCH_UPDATE: Final = "/firewall-policies/batch"
API_PATH_LEGACY_TRAFFIC_RULES: Final = "/trafficrules"
API_PATH_LEGACY_TRAFFIC_RULE_DETAIL: Final = "/trafficrules/{rule_id}"
API_PATH_LEGACY_FIREWALL_RULES: Final = "/firewallrule"
API_PATH_LEGACY_FIREWALL_RULE_DETAIL: Final = "/firewallrule/{rule_id}"
API_PATH_TRAFFIC_ROUTES: Final = "/trafficroutes"
API_PATH_TRAFFIC_ROUTE_DETAIL: Final = "/trafficroutes/{route_id}"
API_PATH_PORT_FORWARDS: Final = "/portforward"
API_PATH_PORT_FORWARD_DETAIL: Final = "/portforward/{forward_id}"
API_PATH_FIREWALL_ZONES: Final = "/firewall/zones"
API_PATH_FIREWALL_ZONE_MATRIX: Final = "/firewall/zone-matrix"
API_PATH_WLANS: Final = "/wlanconf"
API_PATH_WLAN_DETAIL: Final = "/wlanconf/{wlan_id}"
API_PATH_SITE_FEATURE_MIGRATION: Final = "/site-feature-migration"
API_PATH_QOS_RULES: Final = "/qos-rules"
API_PATH_QOS_RULE_DETAIL: Final = "/qos-rules/{rule_id}"
API_PATH_QOS_RULES_BATCH: Final = "/qos-rules/batch"
API_PATH_QOS_RULES_BATCH_DELETE: Final = "/qos-rules/batch-delete"
API_PATH_NETWORK_CONF: Final = "/rest/networkconf"
API_PATH_NETWORK_CONF_DETAIL: Final = "/rest/networkconf/{network_id}"
API_PATH_NAT_RULES: Final = "/nat"
API_PATH_NAT_RULE_DETAIL: Final = "/nat/{rule_id}"
API_PATH_OON_POLICIES: Final = "/object-oriented-network-configs"  # GET uses plural
API_PATH_OON_POLICY_DETAIL: Final = "/object-oriented-network-config/{policy_id}"  # PUT/DELETE use singular
API_PATH_OON_POLICY: Final = "/object-oriented-network-config"  # POST uses singular

# Static Routes (aiounifi path fragments - V1 API)
API_PATH_STATIC_ROUTES: Final = "/rest/routing"
API_PATH_STATIC_ROUTE_DETAIL: Final = "/rest/routing/{route_id}"

# Objects and Profiles (aiounifi path fragments)
API_PATH_PORT_PROFILES: Final = "/rest/portconf"
API_PATH_PORT_PROFILE_DETAIL: Final = "/rest/portconf/{profile_id}"
API_PATH_WLAN_RATE_PROFILES: Final = "/profiles/wlanrate"
API_PATH_WLAN_RATE_PROFILE_DETAIL: Final = "/profiles/wlanrate/{profile_id}"
API_PATH_RADIUS_PROFILES: Final = "/rest/radiusprofile"
API_PATH_RADIUS_PROFILE_DETAIL: Final = "/rest/radiusprofile/{profile_id}"
API_PATH_WAN_SLA_PROFILES: Final = "/profiles/wansla"
API_PATH_WAN_SLA_PROFILE_DETAIL: Final = "/profiles/wansla/{profile_id}"
API_PATH_FIREWALL_GROUPS: Final = "/rest/firewallgroup"
API_PATH_FIREWALL_GROUP_DETAIL: Final = "/rest/firewallgroup/{group_id}"

# Detection endpoints
API_ENDPOINT_SDN_STATUS: Final = "/proxy/network/api/s/{site}/stat/sdn"
API_ENDPOINT_AUTH_LOGIN: Final = "/api/auth/login"
