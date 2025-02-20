"""Config flow for UniFi Network Rules."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
import asyncio

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    LOGGER
)
from .udm_api import CannotConnect, InvalidAuth

from aiounifi.errors import (
    AiounifiException,
    LoginRequired,
    RequestError,
    ResponseError,
    Unauthorized,
)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(
            CONF_UPDATE_INTERVAL, 
            default=DEFAULT_UPDATE_INTERVAL
        ): int,
    }
)

async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> None:
    """Validate the user input allows us to connect."""
    from .udm_api import UDMAPI

    api = UDMAPI(
        data[CONF_HOST],
        data[CONF_USERNAME],
        data[CONF_PASSWORD]
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
                await validate_input(self.hass, user_input)

                await self.async_set_unique_id(f"unifi_rules_{user_input[CONF_HOST]}")
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"UniFi Network Rules ({user_input[CONF_HOST]})",
                    data=user_input
                )

            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception as err:  # pylint: disable=broad-except
                LOGGER.exception("Unexpected exception during setup: %s", str(err))
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )