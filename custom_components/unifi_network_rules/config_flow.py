import voluptuous as vol
from homeassistant import config_entries, core, exceptions
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
import homeassistant.helpers.config_validation as cv
from .const import DOMAIN, CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
from .udm_api import UDMAPI
import logging
from homeassistant.helpers.entity import EntityDescription
from ipaddress import ip_address
import re

_LOGGER = logging.getLogger(__name__)

# Define entity descriptions for entities used in this integration
ENTITY_DESCRIPTIONS = {
    "update_interval": EntityDescription(
        key="update_interval",
        name="Update Interval",
        icon="mdi:update",
        entity_category="config",
    )
}

# Define a schema for configuration, adding basic validation
DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_HOST): cv.string,
    vol.Required(CONF_USERNAME): cv.string,
    vol.Required(CONF_PASSWORD): cv.string,
    vol.Optional(CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
})

async def validate_input(hass: core.HomeAssistant, data: dict):
    """
    Validate the user input allows us to connect.

    Data has the keys from DATA_SCHEMA with values provided by the user.
    """
    api = UDMAPI(
        host=data[CONF_HOST],
        username=data[CONF_USERNAME],
        password=data[CONF_PASSWORD]
    )

    # Try to authenticate first
    auth_success, auth_error = await api.ensure_authenticated()
    if not auth_success:
        _LOGGER.error("Authentication failed: %s", auth_error)
        raise InvalidAuth

    # If authentication succeeds, try to detect capabilities
    capabilities_success = await api.detect_capabilities()
    if not capabilities_success:
        _LOGGER.error(
            "Failed to detect any capabilities. Check device status and permissions."
        )
        raise NoCapabilities

    # Ensure at least one capability was detected
    if not any([
        api.capabilities.traffic_routes,
        api.capabilities.zone_based_firewall,
        api.capabilities.legacy_firewall
    ]):
        _LOGGER.error("No supported capabilities found on the device")
        raise NoCapabilities

    _LOGGER.info(
        "Validated device with capabilities - Traffic Routes: %s, Zone-based Firewall: %s, Legacy Firewall: %s",
        api.capabilities.traffic_routes,
        api.capabilities.zone_based_firewall,
        api.capabilities.legacy_firewall
    )

    await api.cleanup()

    # Return info that you want to store in the config entry.
    return {"title": f"UniFi Rules ({data[CONF_HOST]})"}

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """
    Handle a config flow for Unifi Network Rule Manager.
    """
    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    async def async_step_user(self, user_input=None):
        """
        Handle the initial step of the config flow.
        """
        errors = {}
        if user_input is not None:
            try:
                if CONF_UPDATE_INTERVAL in user_input:
                    update_interval = user_input[CONF_UPDATE_INTERVAL]
                    if not isinstance(update_interval, int) or update_interval < 1 or update_interval > 1440:
                        raise InvalidUpdateInterval
                info = await validate_input(self.hass, user_input)
                return self.async_create_entry(title=info["title"], data=user_input)
            except InvalidAuth:
                errors["base"] = "auth"
            except NoCapabilities:
                errors["base"] = "no_capabilities"
            except CannotConnect:
                errors["base"] = "connect"
            except InvalidUpdateInterval:
                errors["base"] = "invalid_update_interval"
            except InvalidHost:
                errors["base"] = "invalid_host"
            except vol.Invalid as vol_error:
                _LOGGER.error("Validation error: %s", vol_error)
                errors["base"] = "invalid_format"
            except Exception: 
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )

class CannotConnect(exceptions.HomeAssistantError):
    """
    Error to indicate we cannot connect.
    """
    pass

class InvalidAuth(exceptions.HomeAssistantError):
    """
    Error to indicate there is invalid auth.
    """
    pass

class InvalidHost(exceptions.HomeAssistantError):
    """
    Error to indicate there is invalid host address.
    """
    pass

class InvalidUpdateInterval(exceptions.HomeAssistantError):
    """
    Error to indicate the update interval is invalid.
    """
    pass

class NoCapabilities(exceptions.HomeAssistantError):
    """
    Error to indicate no supported capabilities were found.
    """
    pass