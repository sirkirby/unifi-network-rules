"""Mixins for various UniFi Profiles (Port, WLAN Rate, RADIUS, WAN SLA)."""

from __future__ import annotations

from typing import Any, Optional

from ..const import (
    LOGGER,
    API_PATH_PORT_PROFILES,
    API_PATH_PORT_PROFILE_DETAIL,
    API_PATH_WLAN_RATE_PROFILES,
    API_PATH_WLAN_RATE_PROFILE_DETAIL,
    API_PATH_RADIUS_PROFILES,
    API_PATH_RADIUS_PROFILE_DETAIL,
    API_PATH_WAN_SLA_PROFILES,
    API_PATH_WAN_SLA_PROFILE_DETAIL,
)


class PortProfilesMixin:
    async def get_port_profiles(self) -> list[dict[str, Any]]:
        try:
            request = self.create_api_request("GET", API_PATH_PORT_PROFILES)
            data = await self.controller.request(request)
            return data.get("data", []) if isinstance(data, dict) else (data or [])
        except Exception as err:
            LOGGER.error("Failed to get port profiles: %s", str(err))
            return []

    async def add_port_profile(self, payload: dict[str, Any]) -> Optional[dict[str, Any]]:
        try:
            request = self.create_api_request("POST", API_PATH_PORT_PROFILES, data=payload)
            data = await self.controller.request(request)
            return data.get("data") if isinstance(data, dict) else data
        except Exception as err:
            LOGGER.error("Failed to add port profile: %s", str(err))
            return None

    async def update_port_profile(self, payload: dict[str, Any]) -> bool:
        try:
            profile_id = payload.get("_id") or payload.get("id")
            path = API_PATH_PORT_PROFILE_DETAIL.format(profile_id=profile_id)
            request = self.create_api_request("PUT", path, data=payload)
            await self.controller.request(request)
            return True
        except Exception as err:
            LOGGER.error("Failed to update port profile: %s", str(err))
            return False

    async def remove_port_profile(self, profile_id: str) -> bool:
        try:
            path = API_PATH_PORT_PROFILE_DETAIL.format(profile_id=profile_id)
            request = self.create_api_request("DELETE", path)
            await self.controller.request(request)
            return True
        except Exception as err:
            LOGGER.error("Failed to remove port profile %s: %s", profile_id, str(err))
            return False


class WlanRateProfilesMixin:
    async def get_wlan_rate_profiles(self) -> list[dict[str, Any]]:
        try:
            request = self.create_api_request("GET", API_PATH_WLAN_RATE_PROFILES, is_v2=True)
            data = await self.controller.request(request)
            return data.get("data", []) if isinstance(data, dict) else (data or [])
        except Exception as err:
            LOGGER.error("Failed to get WLAN rate profiles: %s", str(err))
            return []

    async def add_wlan_rate_profile(self, payload: dict[str, Any]) -> Optional[dict[str, Any]]:
        try:
            request = self.create_api_request("POST", API_PATH_WLAN_RATE_PROFILES, data=payload, is_v2=True)
            data = await self.controller.request(request)
            return data.get("data") if isinstance(data, dict) else data
        except Exception as err:
            LOGGER.error("Failed to add WLAN rate profile: %s", str(err))
            return None

    async def update_wlan_rate_profile(self, payload: dict[str, Any]) -> bool:
        try:
            profile_id = payload.get("_id") or payload.get("id")
            path = API_PATH_WLAN_RATE_PROFILE_DETAIL.format(profile_id=profile_id)
            request = self.create_api_request("PUT", path, data=payload, is_v2=True)
            await self.controller.request(request)
            return True
        except Exception as err:
            LOGGER.error("Failed to update WLAN rate profile: %s", str(err))
            return False

    async def remove_wlan_rate_profile(self, profile_id: str) -> bool:
        try:
            path = API_PATH_WLAN_RATE_PROFILE_DETAIL.format(profile_id=profile_id)
            request = self.create_api_request("DELETE", path, is_v2=True)
            await self.controller.request(request)
            return True
        except Exception as err:
            LOGGER.error("Failed to remove WLAN rate profile %s: %s", profile_id, str(err))
            return False


class RadiusProfilesMixin:
    async def get_radius_profiles(self) -> list[dict[str, Any]]:
        try:
            request = self.create_api_request("GET", API_PATH_RADIUS_PROFILES)
            data = await self.controller.request(request)
            return data.get("data", []) if isinstance(data, dict) else (data or [])
        except Exception as err:
            LOGGER.error("Failed to get RADIUS profiles: %s", str(err))
            return []

    async def add_radius_profile(self, payload: dict[str, Any]) -> Optional[dict[str, Any]]:
        try:
            request = self.create_api_request("POST", API_PATH_RADIUS_PROFILES, data=payload)
            data = await self.controller.request(request)
            return data.get("data") if isinstance(data, dict) else data
        except Exception as err:
            LOGGER.error("Failed to add RADIUS profile: %s", str(err))
            return None

    async def update_radius_profile(self, payload: dict[str, Any]) -> bool:
        try:
            profile_id = payload.get("_id") or payload.get("id")
            path = API_PATH_RADIUS_PROFILE_DETAIL.format(profile_id=profile_id)
            request = self.create_api_request("PUT", path, data=payload)
            await self.controller.request(request)
            return True
        except Exception as err:
            LOGGER.error("Failed to update RADIUS profile: %s", str(err))
            return False

    async def remove_radius_profile(self, profile_id: str) -> bool:
        try:
            path = API_PATH_RADIUS_PROFILE_DETAIL.format(profile_id=profile_id)
            request = self.create_api_request("DELETE", path)
            await self.controller.request(request)
            return True
        except Exception as err:
            LOGGER.error("Failed to remove RADIUS profile %s: %s", profile_id, str(err))
            return False


class WanSlaProfilesMixin:
    async def get_wan_sla_profiles(self) -> list[dict[str, Any]]:
        try:
            request = self.create_api_request("GET", API_PATH_WAN_SLA_PROFILES, is_v2=True)
            data = await self.controller.request(request)
            return data.get("data", []) if isinstance(data, dict) else (data or [])
        except Exception as err:
            LOGGER.error("Failed to get WAN SLA profiles: %s", str(err))
            return []

    async def add_wan_sla_profile(self, payload: dict[str, Any]) -> Optional[dict[str, Any]]:
        try:
            request = self.create_api_request("POST", API_PATH_WAN_SLA_PROFILES, data=payload, is_v2=True)
            data = await self.controller.request(request)
            return data.get("data") if isinstance(data, dict) else data
        except Exception as err:
            LOGGER.error("Failed to add WAN SLA profile: %s", str(err))
            return None

    async def update_wan_sla_profile(self, payload: dict[str, Any]) -> bool:
        try:
            profile_id = payload.get("_id") or payload.get("id")
            path = API_PATH_WAN_SLA_PROFILE_DETAIL.format(profile_id=profile_id)
            request = self.create_api_request("PUT", path, data=payload, is_v2=True)
            await self.controller.request(request)
            return True
        except Exception as err:
            LOGGER.error("Failed to update WAN SLA profile: %s", str(err))
            return False

    async def remove_wan_sla_profile(self, profile_id: str) -> bool:
        try:
            path = API_PATH_WAN_SLA_PROFILE_DETAIL.format(profile_id=profile_id)
            request = self.create_api_request("DELETE", path, is_v2=True)
            await self.controller.request(request)
            return True
        except Exception as err:
            LOGGER.error("Failed to remove WAN SLA profile %s: %s", profile_id, str(err))
            return False


