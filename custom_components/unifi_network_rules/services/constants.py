"""Constants for UniFi Network Rules services."""

# Service names
SERVICE_REFRESH = "refresh"
SERVICE_BACKUP = "backup_rules"
SERVICE_RESTORE = "restore_rules"
SERVICE_BULK_UPDATE = "bulk_update_rules"
SERVICE_DELETE_RULE = "delete_rule"
SERVICE_APPLY_TEMPLATE = "apply_template"
SERVICE_SAVE_TEMPLATE = "save_template"
SERVICE_FORCE_CLEANUP = "force_cleanup"
SERVICE_FORCE_REMOVE_STALE = "force_remove_stale"
SERVICE_RESET_RATE_LIMIT = "reset_rate_limit"
SERVICE_WEBSOCKET_DIAGNOSTICS = "websocket_diagnostics"
SERVICE_TOGGLE_RULE = "toggle_rule"
SERVICE_REFRESH_DATA = "refresh_data"

# Schema fields
CONF_FILENAME = "filename"
CONF_RULE_IDS = "rule_ids"
CONF_NAME_FILTER = "name_filter"
CONF_RULE_TYPES = "rule_types"
CONF_TEMPLATE_ID = "template_id"
CONF_TEMPLATE = "template"
CONF_VARIABLES = "variables"
CONF_STATE = "state"
CONF_RULE_ID = "rule_id"
CONF_RULE_TYPE = "rule_type"

# Signal for entity cleanup
SIGNAL_ENTITIES_CLEANUP = "unifi_network_rules_cleanup" 