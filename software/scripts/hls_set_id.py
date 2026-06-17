#!/usr/bin/env python3
# Copyright 2026
# SPDX-License-Identifier: Apache-2.0
#
# File: hls_set_id.py
# Purpose: Safely change one HLS3950 servo ID over a direct URT-1/URT-2 TTL
# link. The script only touches the ID register and EEPROM lock state. It does
# not write phase, torque, position, speed, or any motion-related setting.

"""Safely change a single HLS3950 servo ID.

This script is intended for the exact bench workflow where only one servo is
connected to the TTL bus. It reads the old ID, unlocks EEPROM, writes the new
ID, locks EEPROM again, and verifies that the servo responds on the new ID.
"""

from __future__ import annotations

import argparse
import sys
import time

try:
    import scservo_sdk as scs
    from vassar_feetech_servo_sdk import find_servo_port
except ImportError as exc:  # pragma: no cover - depends on local hardware setup
    raise SystemExit(
        "缺少真机调试依赖。请先执行: uv sync --project software --extra hardware"
    ) from exc


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser.

    Returns:
        Configured parser for the HLS3950 ID change command.
    """

    parser = argparse.ArgumentParser(description="HLS3950 单机安全改 ID 脚本")
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
        "--old-id",
        type=int,
        required=True,
        help="当前舵机 ID，例如 1",
    )
    parser.add_argument(
        "--new-id",
        type=int,
        required=True,
        help="目标舵机 ID，例如 2",
    )
    return parser


def resolve_port(port: str | None) -> str:
    """Resolve the serial port to use.

    Args:
        port: User-specified port or ``None`` for auto-detection.

    Returns:
        Concrete serial port path.
    """

    if port:
        return port
    return find_servo_port()


def validate_ids(old_id: int, new_id: int) -> None:
    """Validate source and target IDs.

    Args:
        old_id: Current servo ID.
        new_id: Target servo ID.

    Raises:
        ValueError: Raised when either ID is invalid for the Feetech protocol.
    """

    if not 0 <= old_id <= scs.MAX_ID:
        raise ValueError(f"旧 ID 超出范围: {old_id}，允许范围为 0 到 {scs.MAX_ID}")
    if not 0 <= new_id <= scs.MAX_ID:
        raise ValueError(f"新 ID 超出范围: {new_id}，允许范围为 0 到 {scs.MAX_ID}")
    if old_id == new_id:
        raise ValueError("旧 ID 和新 ID 相同，无需修改")


def require_success(
    operation: str,
    packet_handler: scs.hls,
    comm_result: int,
    error: int,
) -> None:
    """Raise a descriptive error for failed servo communication.

    Args:
        operation: Human-readable operation name.
        packet_handler: Active HLS packet handler.
        comm_result: SDK communication result.
        error: Servo status error bitfield.

    Raises:
        RuntimeError: Raised when the operation fails.
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


def ping_or_raise(packet_handler: scs.hls, servo_id: int) -> int:
    """Ping one servo and return its model number.

    Args:
        packet_handler: Active HLS packet handler.
        servo_id: Target servo ID.

    Returns:
        Model number returned by the servo.
    """

    model_number, comm_result, error = packet_handler.ping(servo_id)
    require_success("ping", packet_handler, comm_result, error)
    return model_number


def write_new_id(packet_handler: scs.hls, old_id: int, new_id: int) -> None:
    """Unlock EEPROM, change ID, and lock EEPROM again.

    Args:
        packet_handler: Active HLS packet handler.
        old_id: Current servo ID.
        new_id: Target servo ID.
    """

    comm_result, error = packet_handler.unLockEprom(old_id)
    require_success("解锁 EEPROM", packet_handler, comm_result, error)

    try:
        comm_result, error = packet_handler.write1ByteTxRx(old_id, scs.HLS_ID, new_id)
        require_success("写入新 ID", packet_handler, comm_result, error)
        time.sleep(0.05)

        comm_result, error = packet_handler.LockEprom(new_id)
        require_success("锁定 EEPROM", packet_handler, comm_result, error)
    except Exception:
        try:
            packet_handler.LockEprom(old_id)
        except Exception:
            pass
        raise


def main() -> int:
    """Run the command-line entry point.

    Returns:
        Process exit code. ``0`` means the ID change succeeded.
    """

    args = build_parser().parse_args()
    validate_ids(args.old_id, args.new_id)
    port = resolve_port(args.port)

    print("=== HLS3950 单机安全改 ID ===")
    print("[WARN] 改 ID 时总线上只能连接这一台舵机。")
    print("[WARN] 本脚本只改 ID 和 EEPROM 锁状态，不会改相位或发送运动命令。")
    print(f"[INFO] serial_port = {port}")
    print(f"[INFO] baudrate    = {args.baudrate}")
    print(f"[INFO] old_id      = {args.old_id}")
    print(f"[INFO] new_id      = {args.new_id}")

    port_handler: scs.PortHandler | None = None
    try:
        print("[INFO] 打开串口并初始化 HLS 协议处理器...")
        port_handler, packet_handler = open_bus(port, args.baudrate)

        print(f"[INFO] 先确认旧 ID {args.old_id} 可响应...")
        model_number = ping_or_raise(packet_handler, args.old_id)
        print(f"[PASS] 旧 ID {args.old_id} 在线，model_number={model_number}")

        print(f"[INFO] 写入新 ID {args.new_id}...")
        write_new_id(packet_handler, args.old_id, args.new_id)

        print(f"[INFO] 校验旧 ID {args.old_id} 不再响应...")
        old_model_number, old_comm_result, old_error = packet_handler.ping(args.old_id)
        if old_comm_result == scs.COMM_SUCCESS and old_error == 0:
            raise RuntimeError(f"旧 ID {args.old_id} 仍然响应，改 ID 未生效")
        print(f"[PASS] 旧 ID {args.old_id} 已不再响应")

        print(f"[INFO] 校验新 ID {args.new_id} 可响应...")
        new_model_number = ping_or_raise(packet_handler, args.new_id)
        print(f"[PASS] 新 ID {args.new_id} 在线，model_number={new_model_number}")
        print("[DONE] ID 修改完成。建议断电重上电后再次只读确认。")
        return 0
    except Exception as exc:  # pragma: no cover - depends on live hardware
        print(f"[FAIL] 改 ID 失败: {exc}", file=sys.stderr)
        return 1
    finally:
        if port_handler is not None and port_handler.is_open:
            port_handler.closePort()
            print("[INFO] 串口已关闭。")


if __name__ == "__main__":
    raise SystemExit(main())
