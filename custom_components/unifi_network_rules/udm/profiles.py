"""Mixins for various UniFi Profiles (Port, WLAN Rate, RADIUS, WAN SLA)."""

from __future__ import annotations

from typing import Any

from ..const import (
    API_PATH_PORT_PROFILE_DETAIL,
    API_PATH_PORT_PROFILES,
    API_PATH_RADIUS_PROFILE_DETAIL,
    API_PATH_RADIUS_PROFILES,
    API_PATH_WAN_SLA_PROFILE_DETAIL,
    API_PATH_WAN_SLA_PROFILES,
    API_PATH_WLAN_RATE_PROFILE_DETAIL,
    API_PATH_WLAN_RATE_PROFILES,
    LOGGER,
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

    async def add_port_profile(self, payload: dict[str, Any]) -> dict[str, Any] | None:
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

    async def toggle_port_profile(
        self,
        profile: dict[str, Any] | Any,
        native_networkconf_id: str | None,
        target_state: bool,
    ) -> bool:
        """Enable/disable a port profile by setting native network assignment.

        Behavior follows sub-issue #99 example payloads: enabling ensures
        native_networkconf_id is set and tagged_vlan_mgmt not blocking; disabling
        clears native_networkconf_id and sets tagged_vlan_mgmt to block_all.

        Args:
            profile: The port profile dict or object to modify
            native_networkconf_id: Network ID to use when enabling (optional)
            target_state: The desired state (True=enabled, False=disabled)

        Returns:
            bool: True if the operation was successful, False otherwise
        """
        try:
            if not isinstance(profile, dict):
                # Allow passing a typed wrapper that exposes raw
                profile = getattr(profile, "raw", None) or {}
            if not profile:
                return False

            payload = dict(profile)
            profile_id = payload.get("_id") or payload.get("id")
            if not profile_id:
                return False

            LOGGER.debug("Setting port profile %s to %s", profile_id, target_state)

            if not target_state:
                # Disable: clear native and block mgmt VLAN tagging (matches example)
                payload["port_security_enabled"] = True
                payload["native_networkconf_id"] = ""
                payload["tagged_vlan_mgmt"] = "block_all"
            else:
                # Enable: keep existing native if present or leave as-is; minimally set fields
                payload["port_security_enabled"] = False
                # Determine the native network id to set
                desired_native = payload.get("native_networkconf_id") or native_networkconf_id
                if not desired_native:
                    # As a fallback, retrieve networks and prefer the default LAN/corporate
                    try:
                        networks = await self.get_networks()
                        # Prefer LAN/corporate
                        preferred = next((n for n in networks if getattr(n, "purpose", "") == "corporate"), None)
                        if not preferred:
                            preferred = next(
                                (n for n in networks if getattr(n, "name", "").upper() in {"LAN", "DEFAULT"}), None
                            )
                        if preferred:
                            desired_native = preferred.id
                    except Exception:
                        desired_native = None
                if not desired_native:
                    # Cannot enable without a network id
                    LOGGER.error("Cannot enable port profile %s - missing native_networkconf_id", profile_id)
                    return False
                payload["native_networkconf_id"] = desired_native
                payload["tagged_vlan_mgmt"] = "auto"

            path = API_PATH_PORT_PROFILE_DETAIL.format(profile_id=profile_id)
            request = self.create_api_request("PUT", path, data=payload)
            await self.controller.request(request)
            return True
        except Exception as err:
            LOGGER.error("Failed to set port profile state: %s", str(err))
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

    async def add_wlan_rate_profile(self, payload: dict[str, Any]) -> dict[str, Any] | None:
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

    async def add_radius_profile(self, payload: dict[str, Any]) -> dict[str, Any] | None:
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

    async def add_wan_sla_profile(self, payload: dict[str, Any]) -> dict[str, Any] | None:
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
