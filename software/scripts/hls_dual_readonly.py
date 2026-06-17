#!/usr/bin/env python3
# Copyright 2026
# SPDX-License-Identifier: Apache-2.0
#
# File: hls_dual_readonly.py
# Purpose: Perform read-only polling for two HLS3950 servos on the same TTL
# bus. The script intentionally avoids any motion command, torque write, phase
# write, or other configuration update.

"""Read-only dual-servo polling tool for HLS3950 bench validation.

This script is intended for the post-ID-assignment stage where two HLS3950
servos share one TTL bus and need to be polled repeatedly without modifying any
servo state.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass

try:
    import scservo_sdk as scs
    from vassar_feetech_servo_sdk import find_servo_port
except ImportError as exc:  # pragma: no cover - depends on local hardware setup
    raise SystemExit(
        "缺少真机调试依赖。请先执行: uv sync --project software --extra hardware"
    ) from exc


HLS_PHASE_ADDR = 18


@dataclass(frozen=True, slots=True)
class ServoSnapshot:
    """A read-only telemetry snapshot for one HLS3950 servo.

    Attributes:
        servo_id: Target servo ID.
        model_number: Model number returned by ``ping``.
        position: Present position register value.
        voltage_volts: Present voltage in volts.
        temperature_celsius: Present temperature in Celsius.
        current_raw: Unsigned current register value.
        current_signed: Signed interpretation of the current register.
        phase: Current phase register value.
        moving: Whether the servo reports a moving state.
    """

    servo_id: int
    model_number: int
    position: int
    voltage_volts: float
    temperature_celsius: int
    current_raw: int
    current_signed: int
    phase: int
    moving: bool

    def format_summary(self) -> str:
        """Format one compact terminal summary line.

        Returns:
            Human-readable one-line status for the current servo.
        """

        return (
            f"ID {self.servo_id}: "
            f"model={self.model_number} "
            f"pos={self.position} "
            f"volt={self.voltage_volts:.1f}V "
            f"temp={self.temperature_celsius}C "
            f"current={self.current_signed} "
            f"phase={self.phase} "
            f"moving={'yes' if self.moving else 'no'}"
        )


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser.

    Returns:
        Configured parser for dual-servo read-only polling.
    """

    parser = argparse.ArgumentParser(description="HLS3950 双机只读轮询脚本")
    parser.add_argument(
        "--port",
        help="串口设备，例如 /dev/ttyUSB0 或 /dev/ttyACM0；省略时自动探测",
    )
    parser.add_argument(
        "--baudrate",
        type=int,
        default=1_000_000,
        help="串口波特率，HLS3950 默认 1000000",
    )
    parser.add_argument(
        "--left-id",
        type=int,
        default=1,
        help="第一台舵机 ID，默认 1",
    )
    parser.add_argument(
        "--right-id",
        type=int,
        default=2,
        help="第二台舵机 ID，默认 2",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=1,
        help="轮询次数，默认 1；例如 20 表示连续读 20 轮",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.2,
        help="轮询间隔秒数，默认 0.2",
    )
    return parser


def resolve_port(port: str | None) -> str:
    """Resolve the serial port to use.

    Args:
        port: User-supplied port or ``None`` for auto-detection.

    Returns:
        Concrete serial port path.
    """

    if port:
        return port
    return find_servo_port()


def require_success(
    operation: str,
    packet_handler: scs.hls,
    comm_result: int,
    error: int,
) -> None:
    """Raise a descriptive error when a servo transaction fails.

    Args:
        operation: Human-readable operation name.
        packet_handler: Active HLS packet handler.
        comm_result: SDK communication status code.
        error: Servo status error bitfield.

    Raises:
        RuntimeError: Raised when the communication or servo status is invalid.
    """

    if comm_result != scs.COMM_SUCCESS:
        raise RuntimeError(f"{operation} 失败: {packet_handler.getTxRxResult(comm_result)}")
    if error != 0:
        raise RuntimeError(f"{operation} 返回舵机错误: {packet_handler.getRxPacketError(error)}")


def open_bus(port: str, baudrate: int) -> tuple[scs.PortHandler, scs.hls]:
    """Open the serial bus and create an HLS packet handler.

    Args:
        port: Serial port path.
        baudrate: Requested baudrate.

    Returns:
        Tuple of the opened port handler and HLS packet handler.
    """

    port_handler = scs.PortHandler(port)
    if not port_handler.openPort():
        raise RuntimeError(f"无法打开串口: {port}")
    if not port_handler.setBaudRate(baudrate):
        port_handler.closePort()
        raise RuntimeError(f"无法设置波特率: {baudrate}")
    return port_handler, scs.hls(port_handler)


def read_snapshot(packet_handler: scs.hls, servo_id: int) -> ServoSnapshot:
    """Read one read-only snapshot from a single HLS3950 servo.

    Args:
        packet_handler: Initialized HLS packet handler.
        servo_id: Servo ID to query.

    Returns:
        Snapshot populated from ping and status registers.
    """

    model_number, comm_result, error = packet_handler.ping(servo_id)
    require_success(f"ID {servo_id} ping", packet_handler, comm_result, error)

    position, comm_result, error = packet_handler.ReadPos(servo_id)
    require_success(f"ID {servo_id} 读取位置", packet_handler, comm_result, error)

    voltage_raw, comm_result, error = packet_handler.read1ByteTxRx(
        servo_id, scs.HLS_PRESENT_VOLTAGE
    )
    require_success(f"ID {servo_id} 读取电压", packet_handler, comm_result, error)

    temperature_celsius, comm_result, error = packet_handler.read1ByteTxRx(
        servo_id, scs.HLS_PRESENT_TEMPERATURE
    )
    require_success(f"ID {servo_id} 读取温度", packet_handler, comm_result, error)

    current_raw, comm_result, error = packet_handler.read2ByteTxRx(
        servo_id, scs.HLS_PRESENT_CURRENT_L
    )
    require_success(f"ID {servo_id} 读取电流", packet_handler, comm_result, error)

    phase, comm_result, error = packet_handler.read1ByteTxRx(servo_id, HLS_PHASE_ADDR)
    require_success(f"ID {servo_id} 读取相位", packet_handler, comm_result, error)

    moving_raw, comm_result, error = packet_handler.ReadMoving(servo_id)
    require_success(f"ID {servo_id} 读取运动状态", packet_handler, comm_result, error)

    return ServoSnapshot(
        servo_id=servo_id,
        model_number=model_number,
        position=position,
        voltage_volts=voltage_raw * 0.1,
        temperature_celsius=temperature_celsius,
        current_raw=current_raw,
        current_signed=packet_handler.scs_tohost(current_raw, 15),
        phase=phase,
        moving=bool(moving_raw),
    )


def main() -> int:
    """Run the command-line entry point.

    Returns:
        Process exit code. ``0`` means all polling rounds succeeded.
    """

    args = build_parser().parse_args()
    if args.left_id == args.right_id:
        raise SystemExit("left-id 和 right-id 不能相同")
    if args.count <= 0:
        raise SystemExit("count 必须大于 0")
    if args.interval < 0:
        raise SystemExit("interval 不能小于 0")

    port = resolve_port(args.port)
    print("=== HLS3950 双机只读轮询 ===")
    print("[INFO] 本脚本只执行 ping 和寄存器读取，不会发送运动或写配置命令。")
    print(f"[INFO] serial_port = {port}")
    print(f"[INFO] baudrate    = {args.baudrate}")
    print(f"[INFO] left_id     = {args.left_id}")
    print(f"[INFO] right_id    = {args.right_id}")
    print(f"[INFO] count       = {args.count}")
    print(f"[INFO] interval    = {args.interval}")

    port_handler: scs.PortHandler | None = None
    try:
        print("[INFO] 打开串口并初始化 HLS 协议处理器...")
        port_handler, packet_handler = open_bus(port, args.baudrate)

        for index in range(1, args.count + 1):
            print(f"[POLL] round={index}")
            left_snapshot = read_snapshot(packet_handler, args.left_id)
            right_snapshot = read_snapshot(packet_handler, args.right_id)
            print(f"  {left_snapshot.format_summary()}")
            print(f"  {right_snapshot.format_summary()}")
            if index < args.count and args.interval > 0:
                time.sleep(args.interval)

        print("[DONE] 双机只读轮询完成。")
        return 0
    except Exception as exc:  # pragma: no cover - depends on live hardware
        print(f"[FAIL] 双机只读轮询失败: {exc}", file=sys.stderr)
        return 1
    finally:
        if port_handler is not None and port_handler.is_open:
            port_handler.closePort()
            print("[INFO] 串口已关闭。")


if __name__ == "__main__":
    raise SystemExit(main())
