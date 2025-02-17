"""Config flow for UniFi Network Rules."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries, core, exceptions
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DOMAIN,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    LOGGER
)
from .udm_api import UDMAPI

class UnifiNetworkRulesConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for UniFi Network Rules."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            try:
                # Create API instance
                api = UDMAPI(
                    user_input[CONF_HOST],
                    user_input[CONF_USERNAME],
                    user_input[CONF_PASSWORD]
                )

                # Test authentication
                auth_success, auth_error = await api.authenticate_session()
                if not auth_success:
                    raise InvalidAuth(f"Authentication failed: {auth_error}")

                # Test capabilities detection
                try:
                    capabilities_detected = await api.detect_capabilities()
                    if not capabilities_detected:
                        raise CannotConnect("Failed to detect UDM capabilities")
                    
                    # Log detected capabilities
                    LOGGER.info(
                        "Detected capabilities - Zone Firewall: %s, Legacy Firewall: %s, Traffic Routes: %s",
                        api.capabilities.zone_based_firewall,
                        api.capabilities.legacy_firewall,
                        api.capabilities.traffic_routes
                    )

                    # Test websocket capability detection
                    try:
                        await api._detect_websocket_capabilities()
                        
                        # Log websocket support for different features
                        LOGGER.info("WebSocket Support:")
                        for feature, supported in api._websocket_capabilities.items():
                            LOGGER.info("  %s: %s", feature, "Supported" if supported else "Not supported")
                            
                    except Exception as ws_err:
                        LOGGER.warning(
                            "WebSocket capability detection failed (will fall back to REST API): %s",
                            str(ws_err)
                        )

                except Exception as cap_err:
                    raise CannotConnect(f"Capability detection failed: {str(cap_err)}")

                # Verify we have at least one working capability
                if not any([
                    api.capabilities.zone_based_firewall,
                    api.capabilities.legacy_firewall,
                    api.capabilities.traffic_routes
                ]):
                    raise CannotConnect("No supported firewall capabilities detected")

                await self.async_set_unique_id(f"unifi_rules_{user_input[CONF_HOST]}")
                self._abort_if_unique_id_configured()

                # Clean up API instance
                await api.cleanup()

                return self.async_create_entry(
                    title=f"UniFi Network Rules ({user_input[CONF_HOST]})",
                    data={
                        CONF_HOST: user_input[CONF_HOST],
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_UPDATE_INTERVAL: user_input.get(
                            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
                        ),
                    },
                )

            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            finally:
                if 'api' in locals():
                    await api.cleanup()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                    vol.Optional(
                        CONF_UPDATE_INTERVAL, 
                        default=DEFAULT_UPDATE_INTERVAL
                    ): int,
                }
            ),
            errors=errors,
        )

class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate we cannot connect."""

class InvalidAuth(exceptions.HomeAssistantError):
    """Error to indicate there is invalid auth."""