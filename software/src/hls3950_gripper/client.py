from __future__ import annotations

from typing import Any

from .models import GripperStatus
from .transport import Transport


class GripperClient:
    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    def initialize(self) -> GripperStatus:
        return self._request_status({"command": "initialize"})

    def enable(self) -> GripperStatus:
        return self._request_status({"command": "enable"})

    def disable(self) -> GripperStatus:
        return self._request_status({"command": "disable"})

    def command_position(self, left: float, right: float) -> GripperStatus:
        if not 0.0 <= left <= 1.0 or not 0.0 <= right <= 1.0:
            raise ValueError("归一化位置必须在 0.0 到 1.0 之间")
        return self._request_status({"command": "position", "left": left, "right": right})

    def status(self) -> GripperStatus:
        return self._request_status({"command": "status"})

    def _request_status(self, payload: dict[str, Any]) -> GripperStatus:
        response = self._transport.request(payload)
        if not response.get("ok"):
            raise RuntimeError(str(response.get("error", "controller_error")))
        status = response.get("status")
        if not isinstance(status, dict):
            raise ValueError("控制器响应缺少 status 对象")
        return GripperStatus.from_payload(status)
