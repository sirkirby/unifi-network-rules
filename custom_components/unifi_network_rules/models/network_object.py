"""Network Object models for UniFi Network Rules integration.

Represents v2 Objects (addresses, address-groups, ports, etc.).
"""
from __future__ import annotations

from typing import Any, Literal, TypedDict

from aiounifi.models.api import ApiItem


class TypedObjectMember(TypedDict):
    type: Literal[
        "ipv4-address",
        "ipv6-address",
        "ipv4-subnet",
        "ipv6-subnet",
        "port",
    ]
    value: str


class TypedNetworkObject(TypedDict, total=False):
    _id: str
    name: str
    description: str
    type: Literal[
        "address",
        "address-group",
        "ipv6-address-group",
        "port-group",
    ]
    members: list[TypedObjectMember]
    site_id: str


"""Typed representation of an object-like firewall group."""


class NetworkObject(ApiItem):
    raw: TypedNetworkObject

    @property
    def id(self) -> str:
        return self.raw.get("_id", "")

    @property
    def name(self) -> str:
        return self.raw.get("name", "")

    @property
    def type(self) -> str:
        return self.raw.get("type", "")

    @property
    def members(self) -> list[TypedObjectMember]:
        return self.raw.get("members", [])

    def to_dict(self) -> dict[str, Any]:
        return dict(self.raw)


