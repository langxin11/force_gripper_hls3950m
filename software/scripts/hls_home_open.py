#!/usr/bin/env python3
# Copyright 2026
# SPDX-License-Identifier: Apache-2.0
#
# File: hls_home_open.py
# Purpose: Command one HLS3950 servo directly to the software open reference
# position, monitor the move, and print the recommended YAML calibration value.

"""Direct single-servo open homing helper for HLS3950 bench calibration.

The script does not reset the servo's internal counter and does not write
EEPROM. It commands one servo to a software open reference position, monitors
current and timeout, and reports the final position that should be recorded as
``open_position`` in ``software/config/hls_gripper.yaml``.
"""

from __future__ import annotations

import argparse
import sys
import time

try:
    import scservo_sdk as scs

    from hls3950_gripper.bus import (
        ServoSnapshot,
        open_bus,
        read_snapshot,
        require_success,
        resolve_port,
    )
except ImportError as exc:  # pragma: no cover - depends on live hardware setup
    raise SystemExit(
        "缺少真机调试依赖。请先执行: uv sync --project software --extra hardware"
    ) from exc


DEFAULT_OPEN_POSITION = 0


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser.

    Returns:
        Configured parser for the direct open homing command.
    """

    parser = argparse.ArgumentParser(description="HLS3950 单机 open 位置直达标定脚本")
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
        "--open-position",
        type=int,
        default=DEFAULT_OPEN_POSITION,
        help="软件 open 参考位置，默认 0",
    )
    parser.add_argument(
        "--speed",
        type=int,
        default=80,
        help="目标速度参数，默认 80",
    )
    parser.add_argument(
        "--acc",
        type=int,
        default=5,
        help="目标加速度参数，默认 5",
    )
    parser.add_argument(
        "--torque",
        type=int,
        default=100,
        help="目标力矩限制参数，默认 100",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=3.0,
        help="等待舵机停止的超时时间，默认 3.0 秒",
    )
    parser.add_argument(
        "--current-limit",
        type=int,
        default=300,
        help="电流绝对值达到该阈值时停止，默认 300",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=0.1,
        help="轮询运动状态的间隔秒数，默认 0.1",
    )
    parser.add_argument(
        "--config-side",
        choices=("left", "right"),
        help="输出 YAML 建议时使用的舵机侧名称，例如 left 或 right",
    )
    return parser


def ensure_torque_enabled(packet_handler: scs.hls, servo_id: int) -> None:
    """Enable servo torque before sending the open command.

    Args:
        packet_handler: Initialized HLS packet handler.
        servo_id: Servo ID to modify.
    """

    torque_enabled, comm_result, error = packet_handler.read1ByteTxRx(
        servo_id, scs.HLS_TORQUE_ENABLE
    )
    require_success("读取使能状态", packet_handler, comm_result, error)
    if torque_enabled != 0:
        print("[INFO] 舵机扭矩已使能。")
        return

    print("[INFO] 舵机当前未使能，写入 torque_enable=1 ...")
    comm_result, error = packet_handler.write1ByteTxRx(servo_id, scs.HLS_TORQUE_ENABLE, 1)
    require_success("使能扭矩", packet_handler, comm_result, error)


def command_position(
    packet_handler: scs.hls,
    servo_id: int,
    target_position: int,
    speed: int,
    acc: int,
    torque: int,
) -> None:
    """Send one target position command.

    Args:
        packet_handler: Initialized HLS packet handler.
        servo_id: Servo ID to command.
        target_position: Target position.
        speed: Servo speed parameter.
        acc: Servo acceleration parameter.
        torque: Servo torque limit parameter.
    """

    comm_result, error = packet_handler.WritePosEx(
        servo_id,
        target_position,
        speed,
        acc,
        torque,
    )
    require_success("写入目标位置", packet_handler, comm_result, error)


def hold_current_position(
    packet_handler: scs.hls,
    servo_id: int,
    snapshot: ServoSnapshot,
    speed: int,
    acc: int,
    torque: int,
) -> None:
    """Command the current position to avoid continuing into the end stop.

    Args:
        packet_handler: Initialized HLS packet handler.
        servo_id: Servo ID to command.
        snapshot: Current telemetry snapshot.
        speed: Servo speed parameter.
        acc: Servo acceleration parameter.
        torque: Servo torque limit parameter.
    """

    print(f"[STOP] 写入当前位置目标，position={snapshot.position}")
    command_position(packet_handler, servo_id, snapshot.position, speed, acc, torque)


def wait_for_open_result(
    packet_handler: scs.hls,
    servo_id: int,
    target_position: int,
    timeout: float,
    current_limit: int,
    poll_interval: float,
    speed: int,
    acc: int,
    torque: int,
) -> tuple[ServoSnapshot, str]:
    """Wait until the open command finishes, times out, or hits current limit.

    Args:
        packet_handler: Initialized HLS packet handler.
        servo_id: Servo ID to poll.
        target_position: Commanded open target position.
        timeout: Maximum wait time in seconds.
        current_limit: Absolute current threshold.
        poll_interval: Polling interval in seconds.
        speed: Servo speed parameter.
        acc: Servo acceleration parameter.
        torque: Servo torque limit parameter.

    Returns:
        Final snapshot and stop reason.
    """

    deadline = time.monotonic() + timeout
    while True:
        snapshot = read_snapshot(packet_handler, servo_id)
        position_error = snapshot.position - target_position
        print(
            "[POLL] "
            f"pos={snapshot.position} target={target_position} error={position_error} "
            f"current={snapshot.current_signed} temp={snapshot.temperature_celsius}C "
            f"moving={'yes' if snapshot.moving else 'no'}"
        )

        if abs(snapshot.current_signed) >= current_limit:
            hold_current_position(packet_handler, servo_id, snapshot, speed, acc, torque)
            return read_snapshot(packet_handler, servo_id), "current_limit"
        if not snapshot.moving:
            return snapshot, "stopped"
        if time.monotonic() >= deadline:
            hold_current_position(packet_handler, servo_id, snapshot, speed, acc, torque)
            return read_snapshot(packet_handler, servo_id), "timeout"

        time.sleep(poll_interval)


def print_snapshot(label: str, snapshot: ServoSnapshot) -> None:
    """Print one compact telemetry snapshot.

    Args:
        label: Terminal label.
        snapshot: Snapshot to render.
    """

    print(f"[{label}] {snapshot.format_summary()}")


def print_yaml_hint(
    config_side: str | None,
    servo_id: int,
    open_position: int,
    reason: str,
    moving: bool,
) -> None:
    """Print the suggested YAML calibration value.

    Args:
        config_side: Optional YAML side name.
        servo_id: Current servo ID.
        open_position: Suggested open position.
        reason: Stop reason returned by the monitor loop.
        moving: Whether the servo still reports moving at the final snapshot.
    """

    if reason != "stopped" or moving:
        print("[WARN] 本次 open 直达没有正常到达目标停止，以下位置只能作为候选标定值。")
        print("[WARN] 请结合现场机械状态确认是否已经全开，再写入 YAML。")

    if config_side is None:
        print("[HINT] 候选标定值：")
        print(f"  servo_id={servo_id} open_position={open_position}")
        return

    print("[HINT] 候选写入 software/config/hls_gripper.yaml：")
    print("servos:")
    print(f"  {config_side}:")
    print(f"    id: {servo_id}")
    print(f"    open_position: {open_position}")


def validate_args(args: argparse.Namespace) -> None:
    """Validate CLI arguments before opening the bus.

    Args:
        args: Parsed command-line arguments.
    """

    if not 0 <= args.open_position <= 4095:
        raise SystemExit("open-position 必须在 0 到 4095 之间")
    if args.timeout <= 0:
        raise SystemExit("timeout 必须大于 0")
    if args.current_limit <= 0:
        raise SystemExit("current-limit 必须大于 0")
    if args.poll_interval <= 0:
        raise SystemExit("poll-interval 必须大于 0")


def main() -> int:
    """Run the command-line entry point.

    Returns:
        Process exit code. ``0`` means the command completed and printed a
        calibration recommendation.
    """

    args = build_parser().parse_args()
    validate_args(args)
    port = resolve_port(args.port)

    print("=== HLS3950 单机 open 位置直达标定 ===")
    print("[WARN] 本脚本会直接命令舵机到 open_position，请保持空载并随时准备断电。")
    print("[WARN] 本脚本不会改 EEPROM，不会重置舵机内部位置计数，也不会自动写 YAML。")
    print(f"[INFO] serial_port   = {port}")
    print(f"[INFO] baudrate      = {args.baudrate}")
    print(f"[INFO] servo_id      = {args.servo_id}")
    print(f"[INFO] open_position = {args.open_position}")
    print(f"[INFO] speed         = {args.speed}")
    print(f"[INFO] acc           = {args.acc}")
    print(f"[INFO] torque        = {args.torque}")
    print(f"[INFO] timeout       = {args.timeout}")
    print(f"[INFO] current_limit = {args.current_limit}")

    port_handler: scs.PortHandler | None = None
    try:
        print("[INFO] 打开串口并初始化 HLS 协议处理器...")
        port_handler, packet_handler = open_bus(port, args.baudrate)

        initial_snapshot = read_snapshot(packet_handler, args.servo_id)
        print_snapshot("START", initial_snapshot)

        ensure_torque_enabled(packet_handler, args.servo_id)

        print(f"[STEP] 写入 open_position={args.open_position} ...")
        command_position(
            packet_handler=packet_handler,
            servo_id=args.servo_id,
            target_position=args.open_position,
            speed=args.speed,
            acc=args.acc,
            torque=args.torque,
        )

        final_snapshot, reason = wait_for_open_result(
            packet_handler=packet_handler,
            servo_id=args.servo_id,
            target_position=args.open_position,
            timeout=args.timeout,
            current_limit=args.current_limit,
            poll_interval=args.poll_interval,
            speed=args.speed,
            acc=args.acc,
            torque=args.torque,
        )

        print_snapshot("FINAL", final_snapshot)
        print(f"[DONE] open 直达结束: reason={reason}")
        print_yaml_hint(
            args.config_side,
            args.servo_id,
            final_snapshot.position,
            reason,
            final_snapshot.moving,
        )
        return 0
    except Exception as exc:  # pragma: no cover - depends on live hardware
        print(f"[FAIL] open 直达失败: {exc}", file=sys.stderr)
        return 1
    finally:
        if port_handler is not None and port_handler.is_open:
            port_handler.closePort()
            print("[INFO] 串口已关闭。")


if __name__ == "__main__":
    raise SystemExit(main())
