"""Diagnostics support for UniFi Network Rules."""
from __future__ import annotations

from typing import Any, Dict

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .utils.diagnostics import async_get_config_entry_diagnostics as _async_get_config_entry_diagnostics


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> Dict[str, Any]:
    """Return diagnostics for a config entry."""
    return await _async_get_config_entry_diagnostics(hass, entry)