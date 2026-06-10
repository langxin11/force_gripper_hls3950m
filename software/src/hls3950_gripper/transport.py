from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, cast


class Transport(ABC):
    @abstractmethod
    def request(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Send one command and return one response."""


class SerialTransport(Transport):
    def __init__(self, port: str, baudrate: int = 115_200, timeout: float = 0.5) -> None:
        try:
            import serial
        except ImportError as exc:  # pragma: no cover - depends on optional runtime environment
            raise RuntimeError("串口模式需要安装 pyserial") from exc

        self._serial = serial.Serial(port=port, baudrate=baudrate, timeout=timeout)

    def request(self, payload: dict[str, Any]) -> dict[str, Any]:
        encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        self._serial.write(encoded + b"\n")
        response = self._serial.readline()
        if not response:
            raise TimeoutError("控制器未在超时时间内返回数据")
        decoded: object = json.loads(response)
        if not isinstance(decoded, dict):
            raise ValueError("控制器响应必须是 JSON 对象")
        return cast(dict[str, Any], decoded)

    def close(self) -> None:
        self._serial.close()


class SimulatedTransport(Transport):
    def __init__(self) -> None:
        self._enabled = False
        self._left_position = 0
        self._right_position = 0

    def request(self, payload: dict[str, Any]) -> dict[str, Any]:
        command = payload.get("command")
        if command == "enable":
            self._enabled = True
        elif command == "disable":
            self._enabled = False
        elif command == "position":
            if not self._enabled:
                return {"ok": False, "error": "controller_disabled"}
            self._left_position = round(float(payload["left"]) * 4095)
            self._right_position = round(float(payload["right"]) * 4095)
        elif command not in {"status", "initialize"}:
            return {"ok": False, "error": "unknown_command"}

        return {
            "ok": True,
            "status": {
                "initialized": True,
                "enabled": self._enabled,
                "fault": None,
                "left_position": self._left_position,
                "right_position": self._right_position,
            },
        }
