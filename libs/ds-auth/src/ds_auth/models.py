"""Data models for parsed JWT claims."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class Organization:
    """Organization membership parsed from the JWT ``organization`` claim.

    KC 26 ``oidc-organization-membership-mapper`` produces per-org entries
    with optional ``type`` and ``attributes``::

        "organization": {
            "example-org": {
                "type": ["dso"],
                "attributes": {"region": ["EU"]}
            }
        }
    """

    alias: str
    type: Optional[str] = None
    attributes: dict[str, list[str]] = field(default_factory=dict)

    def is_type(self, type: str) -> bool:
        return type == self.type

    def get_attribute(self, name: str) -> list[str]:
        return self.attributes.get(name, [])

    def has_attribute(self, name: str, value: str) -> bool:
        return value in self.get_attribute(name)

    @classmethod
    def _from_claim(cls, alias: str, data: Any) -> Organization:
        attributes: dict[str, list[str]] = {}
        org_type: str | None = None

        if isinstance(data, dict):
            raw_type = data.get("type")
            org_type = (
                raw_type[0]
                if isinstance(raw_type, list) and len(raw_type) > 0
                else None
            )

            raw_attrs = data.get("attributes", {})
            if isinstance(raw_attrs, dict):
                attributes = {
                    k: v if isinstance(v, list) else [v]
                    for k, v in raw_attrs.items()
                }

        return cls(alias=alias, type=org_type, attributes=attributes)
