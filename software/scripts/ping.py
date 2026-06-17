#!/usr/bin/env python3
# Copyright 2026
# SPDX-License-Identifier: Apache-2.0
#
# File: ping.py
# Purpose: 单台 HLS3950 舵机最简 ping 示例——回答"舵机是否在线"的最快检查。
#           如需完整遥测读取请使用 hls_single_readonly.py。

"""单台 HLS3950 舵机最简 ping 工具。

这是台架初始化的最简入口：打开总线 → ping 一台舵机 → 上报型号 → 关闭。
故意不读取其他寄存器，输出聚焦在最基础的连通性检查上。
"""

from __future__ import annotations

import argparse
import sys

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
        配置好的最简 ping 命令解析器。
    """

    parser = argparse.ArgumentParser(description="HLS3950 最简 ping 工具")
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
        "--id",
        dest="servo_id",
        type=int,
        default=1,
        help="目标舵机 ID，默认 1",
    )
    return parser


def main() -> int:
    """命令行入口。

    Returns:
        进程退出码。``0`` 表示 ping 成功。
    """

    args = build_parser().parse_args()
    port = resolve_port(args.port)

    print("=== HLS3950 Ping ===")
    print(f"[INFO] serial_port = {port}")
    print(f"[INFO] baudrate    = {args.baudrate}")
    print(f"[INFO] servo_id    = {args.servo_id}")

    port_handler: scs.PortHandler | None = None
    try:
        print("[INFO] 打开串口并初始化 HLS 协议处理器...")
        port_handler, packet_handler = open_bus(port, args.baudrate)

        print(f"[INFO] 发送 ping 到 ID {args.servo_id}...")
        model_number, comm_result, error = packet_handler.ping(args.servo_id)
        require_success("ping", packet_handler, comm_result, error)

        print(f"[PASS] ID {args.servo_id} 在线，model_number = {model_number}")
        return 0
    except Exception as exc:  # pragma: no cover - 依赖真机环境
        print(f"[FAIL] ping 失败: {exc}", file=sys.stderr)
        return 1
    finally:
        if port_handler is not None and port_handler.is_open:
            port_handler.closePort()
            print("[INFO] 串口已关闭。")


if __name__ == "__main__":
    raise SystemExit(main())
