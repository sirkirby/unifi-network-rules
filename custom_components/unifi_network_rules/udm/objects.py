"""Mixin for UniFi v2 Network Objects (address groups, FQDNs, etc.)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..const import (
    LOGGER,
    API_PATH_FIREWALL_GROUPS,
    API_PATH_FIREWALL_GROUP_DETAIL,
)
from ..models.network_object import NetworkObject


class ObjectsMixin:
    async def get_objects(self) -> List[NetworkObject]:
        """List firewall groups as network objects (primary path)."""
        try:
            req = self.create_api_request("GET", API_PATH_FIREWALL_GROUPS)
            data = await self.controller.request(req)
            items: List[NetworkObject] = []
            if isinstance(data, dict) and "data" in data:
                for grp in data["data"]:
                    grp_type = grp.get("group_type", "address-group")
                    mapped_type = (
                        "port-group" if grp_type == "port-group" else
                        "ipv6-address-group" if grp_type == "ipv6-address-group" else
                        "address-group"
                    )
                    member_type = (
                        "port" if mapped_type == "port-group" else
                        "ipv6-address" if mapped_type == "ipv6-address-group" else
                        "ipv4-address"
                    )
                    mapped = {
                        "_id": grp.get("_id"),
                        "name": grp.get("name"),
                        "description": grp.get("name", ""),
                        "type": mapped_type,
                        "members": [
                            {"type": member_type, "value": str(m)}
                            for m in grp.get("group_members", [])
                        ],
                    }
                    items.append(NetworkObject(mapped))
            return items
        except Exception as err:
            LOGGER.error("Failed to get firewall groups: %s", err)
            return []

    async def add_object(self, payload: Dict[str, Any]) -> Optional[NetworkObject]:
        """Create a firewall group from a network object payload."""
        try:
            obj_type = payload.get("type", "address-group")
            group_type = (
                "port-group" if obj_type == "port-group" else
                "ipv6-address-group" if obj_type == "ipv6-address-group" else
                "address-group"
            )
            # normalize members to strings (ports may be ints/ranges encoded as strings)
            group_members = [str(m.get("value")) for m in payload.get("members", []) if isinstance(m, dict)]
            group_payload = {
                "name": payload.get("name"),
                "group_type": group_type,
                "group_members": group_members,
            }
            req = self.create_api_request("POST", API_PATH_FIREWALL_GROUPS, data=group_payload)
            data = await self.controller.request(req)
            if isinstance(data, dict):
                items = data.get("data") or data
                if isinstance(items, list) and items:
                    created = items[0]
                    mapped = {
                        "_id": created.get("_id"),
                        "name": created.get("name"),
                        "description": created.get("name", ""),
                        "type": "address-group",
                        "members": [
                            {"type": "ipv4-address", "value": m}
                            for m in created.get("group_members", [])
                        ],
                    }
                    return NetworkObject(mapped)
            return None
        except Exception as err:
            LOGGER.error("Failed to add firewall group: %s", err)
            return None

    async def update_object(self, obj: NetworkObject | Dict[str, Any]) -> bool:
        """Update a firewall group from a network object payload."""
        try:
            payload = obj.to_dict() if isinstance(obj, NetworkObject) else obj
            object_id = payload.get("_id") or payload.get("id")
            obj_type = payload.get("type", "address-group")
            group_type = (
                "port-group" if obj_type == "port-group" else
                "ipv6-address-group" if obj_type == "ipv6-address-group" else
                "address-group"
            )
            group_members = [str(m.get("value")) for m in payload.get("members", []) if isinstance(m, dict)]
            group_payload = {
                "_id": object_id,
                "name": payload.get("name"),
                "group_type": group_type,
                "group_members": group_members,
            }
            path = API_PATH_FIREWALL_GROUP_DETAIL.format(group_id=object_id)
            req = self.create_api_request("PUT", path, data=group_payload)
            await self.controller.request(req)
            return True
        except Exception as err:
            LOGGER.error("Failed to update firewall group: %s", err)
            return False

    async def remove_object(self, object_id: str) -> bool:
        """Delete a network object (v2)."""
        try:
            path = API_PATH_FIREWALL_GROUP_DETAIL.format(group_id=object_id)
            req = self.create_api_request("DELETE", path)
            await self.controller.request(req)
            return True
        except Exception as err:
            LOGGER.error("Failed to remove firewall group %s: %s", object_id, err)
            return False


