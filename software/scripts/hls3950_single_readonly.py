#!/usr/bin/env python3
# Copyright 2026
# SPDX-License-Identifier: Apache-2.0
#
# File: hls3950_single_readonly.py
# Purpose: Perform a read-only ping and telemetry snapshot for one HLS3950
# servo through a URT-1/URT-2 style serial adapter. This script intentionally
# avoids torque enable, motion commands, EEPROM writes, and phase changes.

"""Read-only ping and status tool for a single HLS3950 servo.

The script talks to the HLS protocol directly through ``scservo_sdk.hls`` so it
can remain read-only. It does not use ``ServoController.connect()`` because the
high-level controller normalizes servo phase during connect, which is a write
operation and unsuitable for first-pass bench checks.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

try:
    import scservo_sdk as scs
    from vassar_feetech_servo_sdk import find_servo_port
except ImportError as exc:  # pragma: no cover - depends on local hardware setup
    raise SystemExit(
        "缺少真机调试依赖。请先执行: uv sync --project software --extra hardware"
    ) from exc


HLS_PHASE_ADDR = 18
DEFAULT_SCAN_BAUDRATES = [1_000_000, 500_000, 250_000, 128_000, 115_200, 57_600, 38_400]


@dataclass(frozen=True, slots=True)
class ServoSnapshot:
    """A read-only telemetry snapshot captured from one servo.

    Attributes:
        servo_id: Target servo ID on the TTL bus.
        model_number: Model number returned by ``ping``.
        position: Present position register value.
        voltage_volts: Present voltage in volts.
        temperature_celsius: Present temperature in Celsius.
        current_raw: Unsigned current register value from the servo.
        current_signed: Signed interpretation of the current register.
        phase: Present phase register value.
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

    def format_lines(self) -> list[str]:
        """Render terminal-friendly output lines for the snapshot.

        Returns:
            Human-readable lines that can be printed directly to the terminal.
        """

        return [
            f"[PASS] ID {self.servo_id} ping 成功",
            f"  model_number : {self.model_number}",
            f"  position     : {self.position}",
            f"  voltage      : {self.voltage_volts:.1f} V",
            f"  temperature  : {self.temperature_celsius} C",
            f"  current_raw  : {self.current_raw}",
            f"  current      : {self.current_signed}",
            f"  phase        : {self.phase}",
            f"  moving       : {'yes' if self.moving else 'no'}",
        ]


@dataclass(frozen=True, slots=True)
class PingResult:
    """A successful read-only ping result.

    Attributes:
        servo_id: Servo ID that replied.
        baudrate: Baudrate used for the successful ping.
        model_number: Model number returned by the servo.
    """

    servo_id: int
    baudrate: int
    model_number: int


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser.

    Returns:
        Configured parser for the single-servo read-only diagnostic command.
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


def resolve_port(port: str | None) -> str:
    """Resolve the serial port to use for the diagnostic.

    Args:
        port: User-supplied serial port or ``None`` for auto-detection.

    Returns:
        A concrete serial port path.
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


def parse_baudrates(value: str) -> list[int]:
    """Parse a comma-separated baudrate list.

    Args:
        value: Comma-separated baudrate string.

    Returns:
        Parsed baudrate list without duplicates while preserving order.
    """

    seen: set[int] = set()
    baudrates: list[int] = []
    for item in value.split(","):
        baudrate = int(item.strip())
        if baudrate not in seen:
            seen.add(baudrate)
            baudrates.append(baudrate)
    return baudrates


def open_bus(port: str, baudrate: int) -> tuple[scs.PortHandler, scs.hls]:
    """Open the serial bus and create an HLS packet handler.

    Args:
        port: Serial port path.
        baudrate: Requested baudrate.

    Returns:
        Tuple of the opened port handler and HLS packet handler.

    Raises:
        RuntimeError: Raised when the port cannot be opened or configured.
    """

    port_handler = scs.PortHandler(port)
    if not port_handler.openPort():
        raise RuntimeError(f"无法打开串口: {port}")
    if not port_handler.setBaudRate(baudrate):
        port_handler.closePort()
        raise RuntimeError(f"无法设置波特率: {baudrate}")
    return port_handler, scs.hls(port_handler)


def try_ping(packet_handler: scs.hls, servo_id: int) -> PingResult | None:
    """Try a read-only ping without raising on timeout.

    Args:
        packet_handler: Initialized HLS packet handler.
        servo_id: Servo ID to query.

    Returns:
        Successful ping result, or ``None`` when the servo does not reply.

    Raises:
        RuntimeError: Raised when the servo replies with an error packet.
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


def read_snapshot(packet_handler: scs.hls, servo_id: int) -> ServoSnapshot:
    """Read a single read-only telemetry snapshot from one HLS3950 servo.

    Args:
        packet_handler: Initialized HLS packet handler.
        servo_id: Servo ID to query.

    Returns:
        Snapshot populated from read-only ping and status registers.
    """

    model_number, comm_result, error = packet_handler.ping(servo_id)
    require_success("ping", packet_handler, comm_result, error)

    position, comm_result, error = packet_handler.ReadPos(servo_id)
    require_success("读取位置", packet_handler, comm_result, error)

    voltage_raw, comm_result, error = packet_handler.read1ByteTxRx(
        servo_id, scs.HLS_PRESENT_VOLTAGE
    )
    require_success("读取电压", packet_handler, comm_result, error)

    temperature_celsius, comm_result, error = packet_handler.read1ByteTxRx(
        servo_id, scs.HLS_PRESENT_TEMPERATURE
    )
    require_success("读取温度", packet_handler, comm_result, error)

    current_raw, comm_result, error = packet_handler.read2ByteTxRx(
        servo_id, scs.HLS_PRESENT_CURRENT_L
    )
    require_success("读取电流", packet_handler, comm_result, error)

    phase, comm_result, error = packet_handler.read1ByteTxRx(servo_id, HLS_PHASE_ADDR)
    require_success("读取相位", packet_handler, comm_result, error)

    moving_raw, comm_result, error = packet_handler.ReadMoving(servo_id)
    require_success("读取运动状态", packet_handler, comm_result, error)

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


def scan_bus(
    port: str,
    baudrates: list[int],
    servo_id_min: int,
    servo_id_max: int,
) -> list[PingResult]:
    """Perform a read-only scan across baudrates and servo IDs.

    Args:
        port: Serial port path.
        baudrates: Baudrates to probe.
        servo_id_min: Inclusive lower bound for the ID sweep.
        servo_id_max: Inclusive upper bound for the ID sweep.

    Returns:
        All successful ping results discovered during the scan.
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
    """Print targeted troubleshooting hints for ping timeout cases.

    Args:
        port: Serial port used for the failed probe.
        baudrate: Baudrate used for the failed probe.
        servo_id: Servo ID used for the failed probe.
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
    """Run the command-line entry point.

    Returns:
        Process exit code. ``0`` means the read-only check succeeded.
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
    except Exception as exc:  # pragma: no cover - depends on live hardware
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
