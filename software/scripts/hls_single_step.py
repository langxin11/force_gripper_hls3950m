#!/usr/bin/env python3
# Copyright 2026
# SPDX-License-Identifier: Apache-2.0
#
# File: hls_single_step.py
# Purpose: 对单台 HLS3950 舵机执行保守的单机运动冒烟测试。
#           脚本读取当前位置和已配置的角度限位，发送一个小步进位置命令，
#           等待舵机停止，并打印台架验证的测试前后遥测数据。

"""HLS3950 台架调试的低风险单机步进运动测试。

本脚本是只读验证后的下一步。刻意使用一个小步进位置命令而非大幅运动序列，
以便在较低机械风险下验证方向、基本运动健康度和安全行程范围。
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
except ImportError as exc:  # pragma: no cover - 依赖真机环境
    raise SystemExit(
        "缺少真机调试依赖。请先执行: uv sync --project software --extra hardware"
    ) from exc


DEFAULT_SAFE_DELTA = 50
MAX_RECOMMENDED_DELTA = 100
DEFAULT_POSITION_MIN = 0
DEFAULT_POSITION_MAX = 4095


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器。

    Returns:
        配置好的单机步进运动命令解析器。
    """

    parser = argparse.ArgumentParser(description="HLS3950 单机低风险小步进运动脚本")
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
        "--delta",
        type=int,
        default=DEFAULT_SAFE_DELTA,
        help="相对当前位置的小步进增量，可为负数，默认 50",
    )
    parser.add_argument(
        "--target",
        type=int,
        help="绝对目标位置；提供后将忽略 --delta",
    )
    parser.add_argument(
        "--speed",
        type=int,
        default=100,
        help="目标速度参数，默认 100",
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
        "--poll-interval",
        type=float,
        default=0.1,
        help="轮询运动状态的间隔秒数，默认 0.1",
    )
    parser.add_argument(
        "--tolerance",
        type=int,
        default=20,
        help="最终位置允许误差，默认 20",
    )
    parser.add_argument(
        "--position-min",
        type=int,
        default=DEFAULT_POSITION_MIN,
        help="角度限位未配置时使用的保守最小位置，默认 0",
    )
    parser.add_argument(
        "--position-max",
        type=int,
        default=DEFAULT_POSITION_MAX,
        help="角度限位未配置时使用的保守最大位置，默认 4095",
    )
    parser.add_argument(
        "--return-to-start",
        action="store_true",
        help="到达目标后再返回起始位置，适合空载单机验证",
    )
    parser.add_argument(
        "--allow-large-delta",
        action="store_true",
        help="允许 |delta| 大于 100；默认关闭以限制风险",
    )
    return parser


def read_angle_limits(packet_handler: scs.hls, servo_id: int) -> tuple[int, int]:
    """读取已配置的最小和最大角度限位。

    Args:
        packet_handler: 已初始化的 HLS 数据包处理器。
        servo_id: 要查询的舵机 ID。

    Returns:
        ``(min_position, max_position)`` 元组。
    """

    min_raw, comm_result, error = packet_handler.read2ByteTxRx(servo_id, scs.HLS_MIN_ANGLE_LIMIT_L)
    require_success("读取最小角度限位", packet_handler, comm_result, error)

    max_raw, comm_result, error = packet_handler.read2ByteTxRx(servo_id, scs.HLS_MAX_ANGLE_LIMIT_L)
    require_success("读取最大角度限位", packet_handler, comm_result, error)

    return packet_handler.scs_tohost(min_raw, 15), packet_handler.scs_tohost(max_raw, 15)


def resolve_position_bounds(
    raw_min_position: int,
    raw_max_position: int,
    fallback_min_position: int,
    fallback_max_position: int,
) -> tuple[int, int]:
    """解析用于目标位置校验的有效位置边界。

    Args:
        raw_min_position: 从舵机 EEPROM 读到的最小角度限位。
        raw_max_position: 从舵机 EEPROM 读到的最大角度限位。
        fallback_min_position: 限位未配置时使用的脚本最小位置。
        fallback_max_position: 限位未配置时使用的脚本最大位置。

    Returns:
        ``(min_position, max_position)`` 有效位置边界。

    Raises:
        ValueError: 舵机限位异常且无法安全降级时抛出。
    """

    if raw_max_position > raw_min_position:
        return raw_min_position, raw_max_position

    if raw_min_position == 0 and raw_max_position == 0:
        print(
            "[WARN] 舵机角度限位寄存器为 [0, 0]，按未配置限位处理。",
            file=sys.stderr,
        )
        print(
            f"[WARN] 本次目标位置校验改用脚本边界 [{fallback_min_position}, {fallback_max_position}]。",
            file=sys.stderr,
        )
        return fallback_min_position, fallback_max_position

    raise ValueError(
        f"角度限位异常: min={raw_min_position}, max={raw_max_position}。请先检查舵机模式和参数。"
    )


def ensure_torque_enabled(packet_handler: scs.hls, servo_id: int) -> None:
    """在发送位置命令前使能舵机扭矩。

    Args:
        packet_handler: 已初始化的 HLS 数据包处理器。
        servo_id: 要修改的舵机 ID。
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


def compute_target_position(
    current_position: int,
    requested_target: int | None,
    delta: int,
    min_position: int,
    max_position: int,
) -> int:
    """计算并校验小步进运动的目标位置。

    Args:
        current_position: 当前舵机位置。
        requested_target: 可选的绝对目标位置。
        delta: 相对当前位置的请求步进量。
        min_position: 已配置的最小角度限位。
        max_position: 已配置的最大角度限位。

    Returns:
        校验通过的绝对目标位置。
    """

    target_position = requested_target if requested_target is not None else current_position + delta
    if not min_position <= target_position <= max_position:
        raise ValueError(
            f"目标位置越界: target={target_position}, allowed=[{min_position}, {max_position}]"
        )
    return target_position


def command_position_step(
    packet_handler: scs.hls,
    servo_id: int,
    target_position: int,
    speed: int,
    acc: int,
    torque: int,
) -> None:
    """发送一条保守的目标位置命令。

    Args:
        packet_handler: 已初始化的 HLS 数据包处理器。
        servo_id: 要命令的舵机 ID。
        target_position: 绝对目标位置。
        speed: 舵机速度参数。
        acc: 舵机加速度参数。
        torque: 舵机力矩限制参数。
    """

    comm_result, error = packet_handler.WritePosEx(
        servo_id,
        target_position,
        speed,
        acc,
        torque,
    )
    require_success("写入目标位置", packet_handler, comm_result, error)


def wait_until_stop(
    packet_handler: scs.hls,
    servo_id: int,
    timeout: float,
    poll_interval: float,
) -> ServoSnapshot:
    """轮询舵机直至其报告停止或超时。

    Args:
        packet_handler: 已初始化的 HLS 数据包处理器。
        servo_id: 要轮询的舵机 ID。
        timeout: 最长等待时间（秒）。
        poll_interval: 轮询间隔（秒）。

    Returns:
        运动停止时的最终遥测快照。

    Raises:
        TimeoutError: 舵机在 ``timeout`` 内未停止时抛出。
    """

    deadline = time.monotonic() + timeout
    while True:
        snapshot = read_snapshot(packet_handler, servo_id)
        print(
            "[POLL] "
            f"pos={snapshot.position} current={snapshot.current_signed} "
            f"temp={snapshot.temperature_celsius}C moving={'yes' if snapshot.moving else 'no'}"
        )
        if not snapshot.moving:
            return snapshot
        if time.monotonic() >= deadline:
            raise TimeoutError(f"等待舵机停止超时: timeout={timeout:.2f}s")
        time.sleep(poll_interval)


def print_snapshot(label: str, snapshot: ServoSnapshot) -> None:
    """打印一条快照的紧凑终端摘要。

    Args:
        label: 终端中显示的快照标签。
        snapshot: 要渲染的快照。
    """

    print(f"[{label}] model={snapshot.model_number}")
    print(f"  position    : {snapshot.position}")
    print(f"  voltage     : {snapshot.voltage_volts:.1f} V")
    print(f"  temperature : {snapshot.temperature_celsius} C")
    print(f"  current     : {snapshot.current_signed}")
    print(f"  phase       : {snapshot.phase}")
    print(f"  moving      : {'yes' if snapshot.moving else 'no'}")


def run_motion_stage(
    packet_handler: scs.hls,
    servo_id: int,
    start_position: int,
    target_position: int,
    speed: int,
    acc: int,
    torque: int,
    timeout: float,
    poll_interval: float,
    tolerance: int,
    stage_name: str,
) -> ServoSnapshot:
    """执行一段运动阶段并验证最终位置。

    Args:
        packet_handler: 已初始化的 HLS 数据包处理器。
        servo_id: 要命令的舵机 ID。
        start_position: 用于报告的起始位置。
        target_position: 绝对目标位置。
        speed: 舵机速度参数。
        acc: 舵机加速度参数。
        torque: 舵机力矩限制参数。
        timeout: 最长等待时间（秒）。
        poll_interval: 轮询间隔（秒）。
        tolerance: 允许的最终位置误差。
        stage_name: 人读的阶段名称。

    Returns:
        该阶段结束后的最终遥测快照。
    """

    delta = target_position - start_position
    print(f"[STEP] {stage_name}: start={start_position} target={target_position} delta={delta}")
    command_position_step(packet_handler, servo_id, target_position, speed, acc, torque)
    final_snapshot = wait_until_stop(packet_handler, servo_id, timeout, poll_interval)
    position_error = final_snapshot.position - target_position
    print(f"[PASS] {stage_name} 完成: final={final_snapshot.position} error={position_error}")
    if abs(position_error) > tolerance:
        raise RuntimeError(
            f"{stage_name} 最终位置超出容差: final={final_snapshot.position}, "
            f"target={target_position}, tolerance={tolerance}"
        )
    return final_snapshot


def validate_args(args: argparse.Namespace) -> None:
    """在打开总线前校验 CLI 参数。

    Args:
        args: 已解析的命令行参数。
    """

    if (
        args.target is None
        and abs(args.delta) > MAX_RECOMMENDED_DELTA
        and not args.allow_large_delta
    ):
        raise SystemExit(
            "当前脚本默认只允许 |delta| <= 100。若确认空载且风险可控，请添加 --allow-large-delta。"
        )
    if args.timeout <= 0:
        raise SystemExit("timeout 必须大于 0")
    if args.poll_interval <= 0:
        raise SystemExit("poll-interval 必须大于 0")
    if args.tolerance < 0:
        raise SystemExit("tolerance 不能小于 0")
    if args.position_max <= args.position_min:
        raise SystemExit("position-max 必须大于 position-min")


def main() -> int:
    """命令行入口。

    Returns:
        进程退出码。``0`` 表示低风险运动测试成功。
    """

    args = build_parser().parse_args()
    validate_args(args)
    port = resolve_port(args.port)

    print("=== HLS3950 单机低风险小步进运动 ===")
    print("[WARN] 请只连接这一台舵机，并优先断开传动机构或保证夹爪空载。")
    print("[WARN] 本脚本会写入 torque_enable 和目标位置，不会改 EEPROM、相位或 ID。")
    print(f"[INFO] serial_port  = {port}")
    print(f"[INFO] baudrate     = {args.baudrate}")
    print(f"[INFO] servo_id     = {args.servo_id}")
    print(f"[INFO] delta        = {args.delta}")
    if args.target is not None:
        print(f"[INFO] target       = {args.target}")
    print(f"[INFO] speed        = {args.speed}")
    print(f"[INFO] acc          = {args.acc}")
    print(f"[INFO] torque       = {args.torque}")
    print(f"[INFO] timeout      = {args.timeout}")
    print(f"[INFO] tolerance    = {args.tolerance}")
    print(f"[INFO] return_start = {'yes' if args.return_to_start else 'no'}")

    port_handler: scs.PortHandler | None = None
    try:
        print("[INFO] 打开串口并初始化 HLS 协议处理器...")
        port_handler, packet_handler = open_bus(port, args.baudrate)

        initial_snapshot = read_snapshot(packet_handler, args.servo_id)
        print_snapshot("BEFORE", initial_snapshot)
        if initial_snapshot.moving:
            raise RuntimeError("舵机当前处于 moving 状态，请先等待停止后再执行小步进测试")

        min_position, max_position = read_angle_limits(packet_handler, args.servo_id)
        print(f"[INFO] angle_limit  = [{min_position}, {max_position}]")
        min_position, max_position = resolve_position_bounds(
            raw_min_position=min_position,
            raw_max_position=max_position,
            fallback_min_position=args.position_min,
            fallback_max_position=args.position_max,
        )
        print(f"[INFO] safe_range   = [{min_position}, {max_position}]")

        target_position = compute_target_position(
            current_position=initial_snapshot.position,
            requested_target=args.target,
            delta=args.delta,
            min_position=min_position,
            max_position=max_position,
        )
        ensure_torque_enabled(packet_handler, args.servo_id)

        after_step = run_motion_stage(
            packet_handler=packet_handler,
            servo_id=args.servo_id,
            start_position=initial_snapshot.position,
            target_position=target_position,
            speed=args.speed,
            acc=args.acc,
            torque=args.torque,
            timeout=args.timeout,
            poll_interval=args.poll_interval,
            tolerance=args.tolerance,
            stage_name="step_out",
        )
        print_snapshot("AFTER", after_step)

        if args.return_to_start:
            print("[INFO] 执行返回起始位置验证...")
            returned_snapshot = run_motion_stage(
                packet_handler=packet_handler,
                servo_id=args.servo_id,
                start_position=after_step.position,
                target_position=initial_snapshot.position,
                speed=args.speed,
                acc=args.acc,
                torque=args.torque,
                timeout=args.timeout,
                poll_interval=args.poll_interval,
                tolerance=args.tolerance,
                stage_name="return_back",
            )
            print_snapshot("RETURN", returned_snapshot)

        print("[DONE] 单机低风险小步进运动测试完成。")
        return 0
    except Exception as exc:  # pragma: no cover - 依赖真机环境
        print(f"[FAIL] 单机小步进运动测试失败: {exc}", file=sys.stderr)
        return 1
    finally:
        if port_handler is not None and port_handler.is_open:
            port_handler.closePort()
            print("[INFO] 串口已关闭。")


if __name__ == "__main__":
    raise SystemExit(main())
