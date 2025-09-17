"""Config flow for UniFi Network Rules."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
import asyncio

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, CONF_VERIFY_SSL
from homeassistant.data_entry_flow import FlowResult
from homeassistant.core import HomeAssistant, callback

from .const import (
    DOMAIN,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    CONF_SITE,
    DEFAULT_SITE,
    LOGGER,
    CONF_SMART_POLLING_BASE_INTERVAL,
    CONF_SMART_POLLING_ACTIVE_INTERVAL,
    CONF_SMART_POLLING_REALTIME_INTERVAL,
    CONF_SMART_POLLING_ACTIVITY_TIMEOUT,
    CONF_SMART_POLLING_DEBOUNCE_SECONDS,
    CONF_SMART_POLLING_OPTIMISTIC_TIMEOUT,
)
from .udm import CannotConnect, InvalidAuth, UDMAPI

from aiounifi.errors import (
    LoginRequired,
    RequestError,
    ResponseError,
    Unauthorized,
)

# Display the update interval in minutes for better UX
DEFAULT_UPDATE_INTERVAL_MINUTES = DEFAULT_UPDATE_INTERVAL // 60

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(
            CONF_SITE, 
            default=DEFAULT_SITE
        ): str,
        vol.Optional(
            CONF_UPDATE_INTERVAL, 
            default=DEFAULT_UPDATE_INTERVAL_MINUTES,
            description="Update interval in minutes"
        ): int,
        vol.Optional(
            CONF_VERIFY_SSL,
            default=False,
            description="Enable SSL certificate verification"
        ): bool,
    }
)

async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> None:
    """Validate the user input allows us to connect."""
    api = UDMAPI(
        data[CONF_HOST],
        data[CONF_USERNAME],
        data[CONF_PASSWORD],
        site=data.get(CONF_SITE, DEFAULT_SITE),
        verify_ssl=data.get(CONF_VERIFY_SSL, False)
    )

    try:
        async with asyncio.timeout(10):
            await api.async_init(hass)
    except (ResponseError, RequestError) as err:
        raise CannotConnect from err
    except (LoginRequired, Unauthorized) as err:
        raise InvalidAuth from err
    except Exception as err:
        LOGGER.exception("Unexpected exception: %s", str(err))
        raise
    finally:
        await api.cleanup()


class UnifiNetworkRulesConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for UniFi Network Rules."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            try:
                # Convert update interval from minutes to seconds
                if CONF_UPDATE_INTERVAL in user_input:
                    user_input[CONF_UPDATE_INTERVAL] = user_input[CONF_UPDATE_INTERVAL] * 60
                
                await validate_input(self.hass, user_input)
                
                await self.async_set_unique_id(f"unifi_rules_{user_input[CONF_HOST]}")
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"UniFi Network Rules ({user_input[CONF_HOST]})",
                    data=user_input,
                )
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow."""
        return UnifiNetworkRulesOptionsFlowHandler(config_entry)


class UnifiNetworkRulesOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for UniFi Network Rules."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Handle options flow."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # Get current options with defaults
        options = self.config_entry.options
        
        # Smart polling configuration schema
        options_schema = vol.Schema({
            vol.Optional(
                CONF_SMART_POLLING_BASE_INTERVAL,
                default=options.get(CONF_SMART_POLLING_BASE_INTERVAL, 300),
                description="Base polling interval when idle (seconds)"
            ): vol.All(int, vol.Range(min=30, max=3600)),
            
            vol.Optional(
                CONF_SMART_POLLING_ACTIVE_INTERVAL,
                default=options.get(CONF_SMART_POLLING_ACTIVE_INTERVAL, 30),
                description="Active polling interval during user activity (seconds)"
            ): vol.All(int, vol.Range(min=10, max=300)),
            
            vol.Optional(
                CONF_SMART_POLLING_REALTIME_INTERVAL,
                default=options.get(CONF_SMART_POLLING_REALTIME_INTERVAL, 10),
                description="Real-time polling interval during changes (seconds)"
            ): vol.All(int, vol.Range(min=5, max=60)),
            
            vol.Optional(
                CONF_SMART_POLLING_ACTIVITY_TIMEOUT,
                default=options.get(CONF_SMART_POLLING_ACTIVITY_TIMEOUT, 120),
                description="Time to return to base interval after activity (seconds)"
            ): vol.All(int, vol.Range(min=60, max=600)),
            
            vol.Optional(
                CONF_SMART_POLLING_DEBOUNCE_SECONDS,
                default=options.get(CONF_SMART_POLLING_DEBOUNCE_SECONDS, 10),
                description="Debounce window for rapid changes (seconds)"
            ): vol.All(int, vol.Range(min=5, max=60)),
            
            vol.Optional(
                CONF_SMART_POLLING_OPTIMISTIC_TIMEOUT,
                default=options.get(CONF_SMART_POLLING_OPTIMISTIC_TIMEOUT, 15),
                description="Maximum optimistic state duration (seconds)"
            ): vol.All(int, vol.Range(min=10, max=60)),
        })

        return self.async_show_form(
            step_id="init",
            data_schema=options_schema,
            description_placeholders={
                "name": self.config_entry.title
            }
        )
