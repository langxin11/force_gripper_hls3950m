#!/usr/bin/env python3
# Copyright 2026
# SPDX-License-Identifier: Apache-2.0
#
# File: hls_single_readonly.py
# Purpose: 通过 URT-1/URT-2 串口适配器对单台 HLS3950 舵机执行只读 ping 和遥测快照。
#           脚本故意回避了力矩使能、运动指令、EEPROM 写入和相位更改。

"""单台 HLS3950 舵机只读 ping 和状态读取工具。

脚本通过 ``scservo_sdk.hls`` 直接与 HLS 协议通信，确保只读操作。
不使用 ``ServoController.connect()``，因为高层控制器在连接时会将舵机相位归零，
这是写操作，不适合首轮台架检查。
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

try:
    import scservo_sdk as scs

    from hls3950_gripper.bus import open_bus, read_snapshot, require_success, resolve_port
except ImportError as exc:  # pragma: no cover - 依赖真机环境
    raise SystemExit(
        "缺少真机调试依赖。请先执行: uv sync --project software --extra hardware"
    ) from exc


DEFAULT_SCAN_BAUDRATES = [1_000_000, 500_000, 250_000, 128_000, 115_200, 57_600, 38_400]


@dataclass(frozen=True, slots=True)
class PingResult:
    """一次成功的只读 ping 结果。

    Attributes:
        servo_id: 响应回复的舵机 ID。
        baudrate: 成功 ping 所使用的波特率。
        model_number: 舵机返回的型号值。
    """

    servo_id: int
    baudrate: int
    model_number: int


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器。

    Returns:
        配置好的单机只读诊断命令解析器。
    """

    parser = argparse.ArgumentParser(description="HLS3950 单机只读 ping/状态读取脚本")
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
    parser.add_argument(
        "--scan",
        action="store_true",
        help="只读扫描常见波特率和 ID，用于排查 ping 超时",
    )
    parser.add_argument(
        "--scan-id-min",
        type=int,
        default=1,
        help="扫描起始 ID，默认 1",
    )
    parser.add_argument(
        "--scan-id-max",
        type=int,
        default=8,
        help="扫描结束 ID，默认 8",
    )
    parser.add_argument(
        "--scan-baudrates",
        default=",".join(str(baudrate) for baudrate in DEFAULT_SCAN_BAUDRATES),
        help="扫描波特率列表，逗号分隔",
    )
    return parser


def parse_baudrates(value: str) -> list[int]:
    """解析逗号分隔的波特率列表。

    Args:
        value: 逗号分隔的波特率字符串。

    Returns:
        去重且保持顺序的波特率列表。
    """

    seen: set[int] = set()
    baudrates: list[int] = []
    for item in value.split(","):
        baudrate = int(item.strip())
        if baudrate not in seen:
            seen.add(baudrate)
            baudrates.append(baudrate)
    return baudrates


def try_ping(packet_handler: scs.hls, servo_id: int) -> PingResult | None:
    """尝试只读 ping，超时不报异常。

    Args:
        packet_handler: 已初始化的 HLS 数据包处理器。
        servo_id: 要查询的舵机 ID。

    Returns:
        ping 成功的结果，舵机无回应时返回 ``None``。

    Raises:
        RuntimeError: 舵机回复错误包时抛出。
    """

    model_number, comm_result, error = packet_handler.ping(servo_id)
    if comm_result == scs.COMM_RX_TIMEOUT:
        return None
    require_success("ping", packet_handler, comm_result, error)
    return PingResult(
        servo_id=servo_id,
        baudrate=packet_handler.portHandler.getBaudRate(),
        model_number=model_number,
    )


def scan_bus(
    port: str,
    baudrates: list[int],
    servo_id_min: int,
    servo_id_max: int,
) -> list[PingResult]:
    """跨波特率和 ID 执行只读扫描。

    Args:
        port: 串口路径。
        baudrates: 要探测的波特率列表。
        servo_id_min: ID 扫描的下界（含）。
        servo_id_max: ID 扫描的上界（含）。

    Returns:
        扫描过程中发现的所有成功 ping 结果。
    """

    found: list[PingResult] = []
    for baudrate in baudrates:
        print(f"[SCAN] baudrate={baudrate}")
        port_handler: scs.PortHandler | None = None
        try:
            port_handler, packet_handler = open_bus(port, baudrate)
            for servo_id in range(servo_id_min, servo_id_max + 1):
                result = try_ping(packet_handler, servo_id)
                if result is None:
                    print(f"  - ID {servo_id}: no response")
                    continue
                print(f"  - ID {servo_id}: reply, model={result.model_number}")
                found.append(result)
        except RuntimeError as exc:
            print(f"  - skip: {exc}")
        finally:
            if port_handler is not None and port_handler.is_open:
                port_handler.closePort()
    return found


def print_timeout_hints(port: str, baudrate: int, servo_id: int) -> None:
    """打印 ping 超时场景的针对性排查提示。

    Args:
        port: 失败探测使用的串口。
        baudrate: 失败探测使用的波特率。
        servo_id: 失败探测使用的舵机 ID。
    """

    print("[HINT] 当前故障是串口打开成功，但目标舵机没有返回状态包。", file=sys.stderr)
    print(
        "[HINT] 先核对 URT-1 是否接在 TTL 口 `G/S/V`，不要接 RS485 口 `G/V2/B/A`。",
        file=sys.stderr,
    )
    print(
        "[HINT] 核对接线是否为 `G->GND`、`S->Signal`、`V->Vcc`，不要只按线色接线。",
        file=sys.stderr,
    )
    print(
        "[HINT] 核对 12V 是否接在 URT-1 的 TTL 供电端 `DC6V-9V` / `V1`，且 `3V3/5V` 开关在 5V。",
        file=sys.stderr,
    )
    print(
        f"[HINT] 当前脚本使用 port={port} baudrate={baudrate} id={servo_id}；默认应为 1 Mbps、ID 1。",
        file=sys.stderr,
    )
    print(
        "[HINT] 如果舵机曾被改过 ID 或波特率，请运行带 `--scan` 的只读扫描。",
        file=sys.stderr,
    )
    print(
        "[HINT] 如果当前总线上挂了两台舵机，先断开其中一台；两台默认同 ID 时会发生回包冲突。",
        file=sys.stderr,
    )
    print(
        "[HINT] 若仍无响应，先断开传动机构，仅保留单机 + 12V + URT-1，再重试。",
        file=sys.stderr,
    )


def main() -> int:
    """命令行入口。

    Returns:
        进程退出码。``0`` 表示只读检查成功。
    """

    args = build_parser().parse_args()
    port = resolve_port(args.port)
    scan_baudrates = parse_baudrates(args.scan_baudrates)

    print("=== HLS3950 单机只读检查 ===")
    print("[INFO] 本脚本只执行 ping 和寄存器读取，不会发送运动或写配置命令。")
    print(f"[INFO] serial_port = {port}")
    print(f"[INFO] baudrate    = {args.baudrate}")
    print(f"[INFO] servo_id    = {args.servo_id}")
    if args.scan:
        print(f"[INFO] scan_ids    = {args.scan_id_min}-{args.scan_id_max}")
        print(f"[INFO] scan_bauds  = {scan_baudrates}")

    port_handler: scs.PortHandler | None = None
    try:
        if args.scan:
            print("[INFO] 执行只读扫描...")
            found = scan_bus(port, scan_baudrates, args.scan_id_min, args.scan_id_max)
            if not found:
                print("[FAIL] 扫描结束，未发现任何在线舵机。", file=sys.stderr)
                print_timeout_hints(port, args.baudrate, args.servo_id)
                return 1
            print("[DONE] 扫描完成，发现以下在线舵机：")
            for result in found:
                print(
                    f"  - baudrate={result.baudrate} id={result.servo_id} model={result.model_number}"
                )
            return 0

        print("[INFO] 打开串口并初始化 HLS 协议处理器...")
        port_handler, packet_handler = open_bus(port, args.baudrate)

        print("[INFO] 发送 ping，并读取位置/电压/温度/电流/相位/运动状态...")
        snapshot = read_snapshot(packet_handler, args.servo_id)

        for line in snapshot.format_lines():
            print(line)
        print("[DONE] 单机只读检查完成。")
        return 0
    except Exception as exc:  # pragma: no cover - 依赖真机环境
        print(f"[FAIL] 单机只读检查失败: {exc}", file=sys.stderr)
        if "There is no status packet" in str(exc):
            print_timeout_hints(port, args.baudrate, args.servo_id)
        return 1
    finally:
        if port_handler is not None and port_handler.is_open:
            port_handler.closePort()
            print("[INFO] 串口已关闭。")


if __name__ == "__main__":
    raise SystemExit(main())
