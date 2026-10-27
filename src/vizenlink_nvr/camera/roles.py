# mirrors: mobile_app/packages/camera_api/lib/src/camera_role.dart@403a2de6c777
"""Camera user privilege roles matching camera_api and ONVIF specifications."""

from enum import IntEnum
from typing import Self


class CameraRole(IntEnum):
    """Privilege hierarchy for camera user accounts."""

    USER = 1
    OPERATOR = 2
    ADMINISTRATOR = 3

    @classmethod
    def from_wire(cls, value: str) -> Self:
        """Parse wire representation ("User", "Operator", "Administrator")."""
        clean = value.strip().lower()
        if clean == "administrator":
            return cls.ADMINISTRATOR
        if clean == "operator":
            return cls.OPERATOR
        if clean == "user":
            return cls.USER
        raise ValueError(f"Unknown camera role wire value: {value}")

    def at_least(self, other: "CameraRole") -> bool:
        """Return True if this role has at least the privilege of other."""
        return self.value >= other.value
