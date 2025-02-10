import voluptuous as vol
from homeassistant import config_entries, core, exceptions
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
import homeassistant.helpers.config_validation as cv
from .const import DOMAIN, CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
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
    host = data[CONF_HOST]
    username = data[CONF_USERNAME]
    password = data[CONF_PASSWORD]

    # Validate host (IP address or domain name)
    try:
        ip_address(host)
    except ValueError:
        # If it's not a valid IP address, check if it's a valid domain name
        if not re.match(r'^[a-zA-Z0-9-]+(\.[a-zA-Z0-9-]+)*\.[a-zA-Z]{2,}$', host):
            raise InvalidHost

    return {"title": f"Unifi Device ({host})"}

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
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidUpdateInterval:
                errors["base"] = "invalid_update_interval"
            except InvalidHost:
                errors["base"] = "invalid_host"
            except vol.Invalid as vol_error:
                _LOGGER.error("Validation error: %s", vol_error)
                errors["base"] = "invalid_format"
            except Exception:  # pylint: disable=broad-except
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