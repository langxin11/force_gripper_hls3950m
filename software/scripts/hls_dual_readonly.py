#!/usr/bin/env python3
# Copyright 2026
# SPDX-License-Identifier: Apache-2.0
#
# File: hls_dual_readonly.py
# Purpose: 对同一条 TTL 总线上的两台 HLS3950 舵机执行只读轮询。
#           脚本故意回避了运动命令、力矩写入、相位写入或任何配置更改。

"""HLS3950 台架验证的双机只读轮询工具。

本脚本适用于 ID 分配后的阶段，此时两台 HLS3950 舵机共享一条 TTL 总线，
需要在修改任何舵机状态的情况下持续轮询。
"""

from __future__ import annotations

import argparse
import sys
import time

try:
    import scservo_sdk as scs

    from hls3950_gripper.bus import open_bus, read_snapshot, resolve_port
except ImportError as exc:  # pragma: no cover - 依赖真机环境
    raise SystemExit(
        "缺少真机调试依赖。请先执行: uv sync --project software --extra hardware"
    ) from exc


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器。

    Returns:
        配置好的双机只读轮询命令解析器。
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


def main() -> int:
    """命令行入口。

    Returns:
        进程退出码。``0`` 表示所有轮询轮次成功。
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
    except Exception as exc:  # pragma: no cover - 依赖真机环境
        print(f"[FAIL] 双机只读轮询失败: {exc}", file=sys.stderr)
        return 1
    finally:
        if port_handler is not None and port_handler.is_open:
            port_handler.closePort()
            print("[INFO] 串口已关闭。")


if __name__ == "__main__":
    raise SystemExit(main())
