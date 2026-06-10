from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class GripperStatus:
    initialized: bool
    enabled: bool
    fault: str | None
    left_position: int
    right_position: int

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> GripperStatus:
        return cls(
            initialized=bool(payload["initialized"]),
            enabled=bool(payload["enabled"]),
            fault=payload.get("fault"),
            left_position=int(payload["left_position"]),
            right_position=int(payload["right_position"]),
        )
