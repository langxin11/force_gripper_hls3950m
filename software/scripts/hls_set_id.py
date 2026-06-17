#!/usr/bin/env python3
# Copyright 2026
# SPDX-License-Identifier: Apache-2.0
#
# File: hls_set_id.py
# Purpose: 通过 URT-1/URT-2 TTL 直连，安全修改单台 HLS3950 舵机 ID。
#           脚本仅操作 ID 寄存器和 EEPROM 锁状态，不写入相位、力矩、
#           位置、速度或任何运动相关配置。

"""单台 HLS3950 舵机安全改 ID 工具。

要求总线上仅连接一台舵机。流程：读取旧 ID → 解锁 EEPROM → 写入新 ID →
锁定 EEPROM → 校验旧 ID 不再响应、新 ID 可响应。
"""

from __future__ import annotations

import argparse
import sys
import time

try:
    import scservo_sdk as scs

    from hls3950_gripper.bus import open_bus, require_success, resolve_port
except ImportError as exc:  # pragma: no cover - 依赖真机环境
    raise SystemExit(
        "缺少真机调试依赖。请先执行: uv sync --project software --extra hardware"
    ) from exc


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器。

    Returns:
        配置好的 HLS3950 改 ID 命令解析器。
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


def validate_ids(old_id: int, new_id: int) -> None:
    """校验新旧 ID 的合法性。

    Args:
        old_id: 当前舵机 ID。
        new_id: 目标舵机 ID。

    Raises:
        ValueError: ID 超出 Feetech 协议允许范围时抛出。
    """

    if not 0 <= old_id <= scs.MAX_ID:
        raise ValueError(f"旧 ID 超出范围: {old_id}，允许范围为 0 到 {scs.MAX_ID}")
    if not 0 <= new_id <= scs.MAX_ID:
        raise ValueError(f"新 ID 超出范围: {new_id}，允许范围为 0 到 {scs.MAX_ID}")
    if old_id == new_id:
        raise ValueError("旧 ID 和新 ID 相同，无需修改")


def ping_or_raise(packet_handler: scs.hls, servo_id: int) -> int:
    """Ping 一台舵机并返回其型号。

    Args:
        packet_handler: 已初始化的 HLS 数据包处理器。
        servo_id: 目标舵机 ID。

    Returns:
        舵机返回的型号值。
    """

    model_number, comm_result, error = packet_handler.ping(servo_id)
    require_success("ping", packet_handler, comm_result, error)
    return model_number


def write_new_id(packet_handler: scs.hls, old_id: int, new_id: int) -> None:
    """解锁 EEPROM，写入新 ID，重新锁定 EEPROM。

    Args:
        packet_handler: 已初始化的 HLS 数据包处理器。
        old_id: 当前舵机 ID。
        new_id: 目标舵机 ID。
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
    """命令行入口。

    Returns:
        进程退出码。``0`` 表示改 ID 成功。
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
    except Exception as exc:  # pragma: no cover - 依赖真机环境
        print(f"[FAIL] 改 ID 失败: {exc}", file=sys.stderr)
        return 1
    finally:
        if port_handler is not None and port_handler.is_open:
            port_handler.closePort()
            print("[INFO] 串口已关闭。")


if __name__ == "__main__":
    raise SystemExit(main())
