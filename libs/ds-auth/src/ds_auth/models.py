"""Data models for parsed JWT claims."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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
    type: str | None = None
    attributes: dict[str, list[str]] = field(default_factory=dict)
    # The groups held *within this organisation*.
    #
    # `extract_groups` flattens realm groups and every organisation's groups into
    # one list, which is right for "may this caller do X at all" and useless for
    # "may this caller do X **to this owner's** data". That provenance used to be
    # discarded here, so the second question could not be asked at any call site —
    # a caller who was a viewer in one organisation and an administrator in
    # another appeared, correctly flattened, to be an administrator.
    #
    # See :meth:`ds_auth.Principal.grants_in`.
    groups: tuple[str, ...] = ()

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
        groups: tuple[str, ...] = ()

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
                    k: v if isinstance(v, list) else [v] for k, v in raw_attrs.items()
                }

            raw_groups = data.get("groups")
            if isinstance(raw_groups, list):
                # Leading slashes stripped to match `extract_groups`, so the same
                # name compares equal whichever path it arrived by.
                groups = tuple(
                    g.lstrip("/")
                    for g in raw_groups
                    if isinstance(g, str) and g.strip()
                )

        return cls(alias=alias, type=org_type, attributes=attributes, groups=groups)
