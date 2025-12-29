"""System services for UniFi Network Rules integration."""

from __future__ import annotations

import re

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from ..const import DOMAIN, LOGGER
from ..utils.remote_lists import parse_curated_text
from .constants import (
    SERVICE_REFRESH,
    SERVICE_REFRESH_DATA,
    SERVICE_SYNC_REMOTE_CURATED,
)

# Schema for refresh service
REFRESH_DATA_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): cv.string,
    }
)


async def async_refresh_service(hass: HomeAssistant, coordinators: dict, call: ServiceCall) -> None:
    """Service to refresh UniFi data."""
    # Refresh all coordinators
    for coordinator in coordinators.values():
        await coordinator.async_refresh()


async def async_refresh_data(hass: HomeAssistant, coordinators: dict, call: ServiceCall) -> None:
    """Handle the refresh service call."""
    entry_id = call.data.get("entry_id")

    if entry_id:
        # Refresh specific coordinator
        if entry_id in coordinators:
            LOGGER.info("Manually refreshing data for entry %s", entry_id)
            await coordinators[entry_id].async_refresh()
        else:
            raise HomeAssistantError(f"No coordinator found for entry_id {entry_id}")
    else:
        # Refresh all coordinators
        LOGGER.info("Manually refreshing data for all coordinators")
        for entry_id, coordinator in coordinators.items():
            LOGGER.debug("Refreshing coordinator for entry %s", entry_id)
            await coordinator.async_refresh()


async def async_setup_system_services(hass: HomeAssistant, coordinators: dict) -> None:
    """Set up system-related services."""

    # Handle the refresh service
    async def handle_refresh(call: ServiceCall) -> None:
        await async_refresh_service(hass, coordinators, call)

    # Handle the refresh data service
    async def handle_refresh_data(call: ServiceCall) -> None:
        await async_refresh_data(hass, coordinators, call)

    # Register services
    hass.services.async_register(DOMAIN, SERVICE_REFRESH, handle_refresh, schema=REFRESH_DATA_SCHEMA)

    hass.services.async_register(DOMAIN, SERVICE_REFRESH_DATA, handle_refresh_data, schema=REFRESH_DATA_SCHEMA)

    # Remote curated file sync
    async def handle_sync_remote_curated(call: ServiceCall) -> None:
        entry_id = call.data.get("entry_id")
        urls_input = call.data.get("urls")
        url_list: list[str] = []
        if isinstance(urls_input, list):
            # Flatten any strings that might contain multiple URLs
            for item in urls_input:
                if isinstance(item, str):
                    found = re.findall(r"https?://\S+", item)
                    url_list.extend(found if found else [item])
        elif isinstance(urls_input, str):
            # Extract all http(s) URLs from the string (handles spaces, newlines)
            url_list = re.findall(r"https?://\S+", urls_input)
        if not url_list:
            raise HomeAssistantError("'urls' must contain at least one valid http(s) URL")

        targets = {entry_id: coordinators.get(entry_id)} if entry_id and entry_id in coordinators else coordinators
        for _entry, coord in targets.items():
            if not coord:
                continue
            api = getattr(coord, "api", None) or getattr(coord, "_api", None)
            if not api:
                continue
            for raw_url in url_list:
                try:
                    session = async_get_clientsession(hass)
                    async with session.get(raw_url) as resp:
                        if resp.status != 200:
                            raise HomeAssistantError(
                                f"Failed to fetch remote list '{raw_url}': {resp.status} {await resp.text()}"
                            )
                        content = await resp.text()

                    payload = parse_curated_text(content)
                    # Enforce type-specific members
                    obj_type = payload.get("type", "address-group")
                    if obj_type == "port-group":
                        filtered = [m for m in payload.get("members", []) if m.get("type") == "port"]
                    elif obj_type == "ipv6-address-group":
                        filtered = [m for m in payload.get("members", []) if m.get("type", "").startswith("ipv6")]
                    else:
                        filtered = [m for m in payload.get("members", []) if m.get("type", "").startswith("ipv4")]
                    payload = {**payload, "members": filtered}

                    existing = await api.get_objects()
                    existing_by_name = {o.name: o for o in existing}
                    name = payload.get("name")
                    if name in existing_by_name:
                        obj = existing_by_name[name]
                        to_update = obj.to_dict()
                        to_update.update(
                            {
                                "description": payload.get("description", to_update.get("description")),
                                "type": obj_type,
                                "members": payload.get("members", to_update.get("members", [])),
                            }
                        )
                        await api.update_object(to_update)
                    else:
                        await api.add_object(payload)
                except Exception as err:
                    LOGGER.error("Remote curated sync failed for '%s': %s", raw_url, err)

    hass.services.async_register(
        DOMAIN,
        SERVICE_SYNC_REMOTE_CURATED,
        handle_sync_remote_curated,
        schema=vol.Schema(
            {
                vol.Optional("entry_id"): cv.string,
                vol.Required("urls"): vol.Any(cv.ensure_list(cv.string), cv.string),
            }
        ),
    )
