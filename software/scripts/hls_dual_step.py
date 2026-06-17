#!/usr/bin/env python3
# Copyright 2026
# SPDX-License-Identifier: Apache-2.0
#
# File: hls_dual_step.py
# Purpose: 对两台 HLS3950 舵机执行保守的同步小步进运动测试。
#           脚本先读取双机状态和位置边界，再用 reg-write/action 同步触发
#           一次 open 或 close 小步进，并打印运动前后的台架遥测数据。

"""HLS3950 台架调试的低风险双机同步步进运动测试。

本脚本用于单机方向验证完成后的第一轮双机联动。当前机械映射为：
``open`` 对两台舵机都发送负向位置增量，``close`` 对两台舵机都发送
正向位置增量。
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass

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


DEFAULT_SAFE_DELTA = 30
MAX_RECOMMENDED_DELTA = 100
DEFAULT_POSITION_MIN = 0
DEFAULT_POSITION_MAX = 4095


@dataclass(frozen=True, slots=True)
class ServoPlan:
    """一台舵机在当前双机步进中的运动计划。

    Attributes:
        label: 终端显示标签，例如 ``left`` 或 ``right``。
        servo_id: 目标舵机 ID。
        start_position: 运动前位置。
        target_position: 目标位置。
        min_position: 本次校验使用的最小位置。
        max_position: 本次校验使用的最大位置。
    """

    label: str
    servo_id: int
    start_position: int
    target_position: int
    min_position: int
    max_position: int


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器。

    Returns:
        配置好的双机同步步进命令解析器。
    """

    parser = argparse.ArgumentParser(description="HLS3950 双机低风险同步小步进脚本")
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
        help="左侧或第一台舵机 ID，默认 1",
    )
    parser.add_argument(
        "--right-id",
        type=int,
        default=2,
        help="右侧或第二台舵机 ID，默认 2",
    )
    parser.add_argument(
        "--action",
        choices=("open", "close"),
        required=True,
        help="动作方向：open 为双机负向步进，close 为双机正向步进",
    )
    parser.add_argument(
        "--delta",
        type=int,
        default=DEFAULT_SAFE_DELTA,
        help="同步小步进大小，方向由 --action 决定，默认 30",
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
        help="等待双机停止的超时时间，默认 3.0 秒",
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
        "--allow-large-delta",
        action="store_true",
        help="允许 delta 大于 100；默认关闭以限制风险",
    )
    return parser


def read_angle_limits(packet_handler: scs.hls, servo_id: int) -> tuple[int, int]:
    """读取一台舵机已配置的最小和最大角度限位。

    Args:
        packet_handler: 已初始化的 HLS 数据包处理器。
        servo_id: 要查询的舵机 ID。

    Returns:
        ``(min_position, max_position)`` 元组。
    """

    min_raw, comm_result, error = packet_handler.read2ByteTxRx(servo_id, scs.HLS_MIN_ANGLE_LIMIT_L)
    require_success(f"ID {servo_id} 读取最小角度限位", packet_handler, comm_result, error)

    max_raw, comm_result, error = packet_handler.read2ByteTxRx(servo_id, scs.HLS_MAX_ANGLE_LIMIT_L)
    require_success(f"ID {servo_id} 读取最大角度限位", packet_handler, comm_result, error)

    return packet_handler.scs_tohost(min_raw, 15), packet_handler.scs_tohost(max_raw, 15)


def resolve_position_bounds(
    servo_id: int,
    raw_min_position: int,
    raw_max_position: int,
    fallback_min_position: int,
    fallback_max_position: int,
) -> tuple[int, int]:
    """解析用于目标位置校验的有效位置边界。

    Args:
        servo_id: 用于终端提示的舵机 ID。
        raw_min_position: 从舵机 EEPROM 读到的最小角度限位。
        raw_max_position: 从舵机 EEPROM 读到的最大角度限位。
        fallback_min_position: 限位未配置时使用的脚本最小位置。
        fallback_max_position: 限位未配置时使用的脚本最大位置。

    Returns:
        ``(min_position, max_position)`` 有效位置边界。
    """

    if raw_max_position > raw_min_position:
        return raw_min_position, raw_max_position

    if raw_min_position == 0 and raw_max_position == 0:
        print(
            f"[WARN] ID {servo_id} 角度限位寄存器为 [0, 0]，按未配置限位处理。",
            file=sys.stderr,
        )
        print(
            f"[WARN] ID {servo_id} 本次校验改用脚本边界 "
            f"[{fallback_min_position}, {fallback_max_position}]。",
            file=sys.stderr,
        )
        return fallback_min_position, fallback_max_position

    raise ValueError(f"ID {servo_id} 角度限位异常: min={raw_min_position}, max={raw_max_position}")


def ensure_torque_enabled(packet_handler: scs.hls, servo_id: int) -> None:
    """在发送位置命令前使能舵机扭矩。

    Args:
        packet_handler: 已初始化的 HLS 数据包处理器。
        servo_id: 要修改的舵机 ID。
    """

    torque_enabled, comm_result, error = packet_handler.read1ByteTxRx(
        servo_id, scs.HLS_TORQUE_ENABLE
    )
    require_success(f"ID {servo_id} 读取使能状态", packet_handler, comm_result, error)
    if torque_enabled != 0:
        print(f"[INFO] ID {servo_id} 舵机扭矩已使能。")
        return

    print(f"[INFO] ID {servo_id} 舵机当前未使能，写入 torque_enable=1 ...")
    comm_result, error = packet_handler.write1ByteTxRx(servo_id, scs.HLS_TORQUE_ENABLE, 1)
    require_success(f"ID {servo_id} 使能扭矩", packet_handler, comm_result, error)


def compute_signed_delta(action: str, delta: int) -> int:
    """根据动作名称计算带符号的位置增量。

    Args:
        action: ``open`` 或 ``close``。
        delta: 正数步长大小。

    Returns:
        带符号的位置增量。
    """

    magnitude = abs(delta)
    if action == "open":
        return -magnitude
    return magnitude


def build_servo_plan(
    label: str,
    servo_id: int,
    start_position: int,
    signed_delta: int,
    min_position: int,
    max_position: int,
) -> ServoPlan:
    """构建并校验单台舵机的本次运动计划。

    Args:
        label: 终端显示标签。
        servo_id: 目标舵机 ID。
        start_position: 当前舵机位置。
        signed_delta: 带符号的位置增量。
        min_position: 本次校验最小位置。
        max_position: 本次校验最大位置。

    Returns:
        校验通过的运动计划。
    """

    target_position = start_position + signed_delta
    if not min_position <= target_position <= max_position:
        raise ValueError(
            f"{label} ID {servo_id} 目标位置越界: target={target_position}, "
            f"allowed=[{min_position}, {max_position}]"
        )
    return ServoPlan(
        label=label,
        servo_id=servo_id,
        start_position=start_position,
        target_position=target_position,
        min_position=min_position,
        max_position=max_position,
    )


def reg_write_position(
    packet_handler: scs.hls,
    plan: ServoPlan,
    speed: int,
    acc: int,
    torque: int,
) -> None:
    """用 reg-write 写入一台舵机的待执行目标位置。

    Args:
        packet_handler: 已初始化的 HLS 数据包处理器。
        plan: 单台舵机运动计划。
        speed: 舵机速度参数。
        acc: 舵机加速度参数。
        torque: 舵机力矩限制参数。
    """

    comm_result, error = packet_handler.RegWritePosEx(
        plan.servo_id,
        plan.target_position,
        speed,
        acc,
        torque,
    )
    require_success(
        f"{plan.label} ID {plan.servo_id} 暂存目标位置", packet_handler, comm_result, error
    )


def action_or_raise(packet_handler: scs.hls) -> None:
    """广播 action 指令，同步触发已暂存的双机目标。

    Args:
        packet_handler: 已初始化的 HLS 数据包处理器。
    """

    comm_result = packet_handler.RegAction()
    if comm_result != scs.COMM_SUCCESS:
        raise RuntimeError(f"同步触发失败: {packet_handler.getTxRxResult(comm_result)}")


def command_dual_step(
    packet_handler: scs.hls,
    left_plan: ServoPlan,
    right_plan: ServoPlan,
    speed: int,
    acc: int,
    torque: int,
) -> None:
    """暂存双机目标位置并同步触发。

    Args:
        packet_handler: 已初始化的 HLS 数据包处理器。
        left_plan: 左侧舵机运动计划。
        right_plan: 右侧舵机运动计划。
        speed: 舵机速度参数。
        acc: 舵机加速度参数。
        torque: 舵机力矩限制参数。
    """

    reg_write_position(packet_handler, left_plan, speed, acc, torque)
    reg_write_position(packet_handler, right_plan, speed, acc, torque)
    action_or_raise(packet_handler)


def wait_until_both_stop(
    packet_handler: scs.hls,
    left_id: int,
    right_id: int,
    timeout: float,
    poll_interval: float,
) -> tuple[ServoSnapshot, ServoSnapshot]:
    """轮询两台舵机直至都报告停止或超时。

    Args:
        packet_handler: 已初始化的 HLS 数据包处理器。
        left_id: 左侧舵机 ID。
        right_id: 右侧舵机 ID。
        timeout: 最长等待时间（秒）。
        poll_interval: 轮询间隔（秒）。

    Returns:
        两台舵机的最终遥测快照。
    """

    deadline = time.monotonic() + timeout
    while True:
        left_snapshot = read_snapshot(packet_handler, left_id)
        right_snapshot = read_snapshot(packet_handler, right_id)
        print(
            "[POLL] "
            f"left_pos={left_snapshot.position} left_current={left_snapshot.current_signed} "
            f"left_moving={'yes' if left_snapshot.moving else 'no'} | "
            f"right_pos={right_snapshot.position} right_current={right_snapshot.current_signed} "
            f"right_moving={'yes' if right_snapshot.moving else 'no'}"
        )
        if not left_snapshot.moving and not right_snapshot.moving:
            return left_snapshot, right_snapshot
        if time.monotonic() >= deadline:
            raise TimeoutError(f"等待双机停止超时: timeout={timeout:.2f}s")
        time.sleep(poll_interval)


def print_snapshot_pair(
    label: str,
    left_snapshot: ServoSnapshot,
    right_snapshot: ServoSnapshot,
) -> None:
    """打印双机快照摘要。

    Args:
        label: 终端显示标签。
        left_snapshot: 左侧舵机快照。
        right_snapshot: 右侧舵机快照。
    """

    print(f"[{label}] left  {left_snapshot.format_summary()}")
    print(f"[{label}] right {right_snapshot.format_summary()}")


def print_plan(plan: ServoPlan) -> None:
    """打印单台舵机的运动计划。

    Args:
        plan: 要打印的运动计划。
    """

    delta = plan.target_position - plan.start_position
    print(
        f"[PLAN] {plan.label} ID {plan.servo_id}: "
        f"start={plan.start_position} target={plan.target_position} "
        f"delta={delta} safe_range=[{plan.min_position}, {plan.max_position}]"
    )


def verify_final_position(plan: ServoPlan, snapshot: ServoSnapshot, tolerance: int) -> None:
    """校验最终位置是否落在允许误差内。

    Args:
        plan: 单台舵机运动计划。
        snapshot: 运动后的最终快照。
        tolerance: 允许的最终位置误差。
    """

    position_error = snapshot.position - plan.target_position
    print(
        f"[CHECK] {plan.label} ID {plan.servo_id}: "
        f"final={snapshot.position} target={plan.target_position} error={position_error}"
    )
    if abs(position_error) > tolerance:
        raise RuntimeError(
            f"{plan.label} ID {plan.servo_id} 最终位置超出容差: "
            f"final={snapshot.position}, target={plan.target_position}, tolerance={tolerance}"
        )


def validate_args(args: argparse.Namespace) -> None:
    """在打开总线前校验 CLI 参数。

    Args:
        args: 已解析的命令行参数。
    """

    if args.left_id == args.right_id:
        raise SystemExit("left-id 和 right-id 不能相同")
    if args.delta <= 0:
        raise SystemExit("delta 必须大于 0，方向由 --action open/close 决定")
    if args.delta > MAX_RECOMMENDED_DELTA and not args.allow_large_delta:
        raise SystemExit(
            "当前脚本默认只允许 delta <= 100。若确认空载且风险可控，请添加 --allow-large-delta。"
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
        进程退出码。``0`` 表示双机同步小步进测试成功。
    """

    args = build_parser().parse_args()
    validate_args(args)
    port = resolve_port(args.port)
    signed_delta = compute_signed_delta(args.action, args.delta)

    print("=== HLS3950 双机低风险同步小步进 ===")
    print("[WARN] 请确认两台舵机 ID 已分配完成，并保证夹爪空载或无硬限位风险。")
    print("[WARN] 本脚本会写入 torque_enable 和目标位置，不会改 EEPROM、相位或 ID。")
    print("[INFO] 当前方向映射: open -> 双机负向步进，close -> 双机正向步进。")
    print(f"[INFO] serial_port = {port}")
    print(f"[INFO] baudrate    = {args.baudrate}")
    print(f"[INFO] left_id     = {args.left_id}")
    print(f"[INFO] right_id    = {args.right_id}")
    print(f"[INFO] action      = {args.action}")
    print(f"[INFO] delta       = {args.delta}")
    print(f"[INFO] signed_delta= {signed_delta}")
    print(f"[INFO] speed       = {args.speed}")
    print(f"[INFO] acc         = {args.acc}")
    print(f"[INFO] torque      = {args.torque}")
    print(f"[INFO] timeout     = {args.timeout}")
    print(f"[INFO] tolerance   = {args.tolerance}")

    port_handler: scs.PortHandler | None = None
    try:
        print("[INFO] 打开串口并初始化 HLS 协议处理器...")
        port_handler, packet_handler = open_bus(port, args.baudrate)

        left_before = read_snapshot(packet_handler, args.left_id)
        right_before = read_snapshot(packet_handler, args.right_id)
        print_snapshot_pair("BEFORE", left_before, right_before)
        if left_before.moving or right_before.moving:
            raise RuntimeError("至少一台舵机当前处于 moving 状态，请先等待停止后再执行")

        left_raw_min, left_raw_max = read_angle_limits(packet_handler, args.left_id)
        right_raw_min, right_raw_max = read_angle_limits(packet_handler, args.right_id)
        print(f"[INFO] left_angle_limit  = [{left_raw_min}, {left_raw_max}]")
        print(f"[INFO] right_angle_limit = [{right_raw_min}, {right_raw_max}]")

        left_min, left_max = resolve_position_bounds(
            servo_id=args.left_id,
            raw_min_position=left_raw_min,
            raw_max_position=left_raw_max,
            fallback_min_position=args.position_min,
            fallback_max_position=args.position_max,
        )
        right_min, right_max = resolve_position_bounds(
            servo_id=args.right_id,
            raw_min_position=right_raw_min,
            raw_max_position=right_raw_max,
            fallback_min_position=args.position_min,
            fallback_max_position=args.position_max,
        )

        left_plan = build_servo_plan(
            label="left",
            servo_id=args.left_id,
            start_position=left_before.position,
            signed_delta=signed_delta,
            min_position=left_min,
            max_position=left_max,
        )
        right_plan = build_servo_plan(
            label="right",
            servo_id=args.right_id,
            start_position=right_before.position,
            signed_delta=signed_delta,
            min_position=right_min,
            max_position=right_max,
        )
        print_plan(left_plan)
        print_plan(right_plan)

        ensure_torque_enabled(packet_handler, args.left_id)
        ensure_torque_enabled(packet_handler, args.right_id)

        print("[STEP] 暂存双机目标位置并同步触发...")
        command_dual_step(
            packet_handler=packet_handler,
            left_plan=left_plan,
            right_plan=right_plan,
            speed=args.speed,
            acc=args.acc,
            torque=args.torque,
        )

        left_after, right_after = wait_until_both_stop(
            packet_handler=packet_handler,
            left_id=args.left_id,
            right_id=args.right_id,
            timeout=args.timeout,
            poll_interval=args.poll_interval,
        )
        print_snapshot_pair("AFTER", left_after, right_after)
        verify_final_position(left_plan, left_after, args.tolerance)
        verify_final_position(right_plan, right_after, args.tolerance)

        print("[DONE] 双机低风险同步小步进测试完成。")
        return 0
    except Exception as exc:  # pragma: no cover - 依赖真机环境
        print(f"[FAIL] 双机同步小步进测试失败: {exc}", file=sys.stderr)
        return 1
    finally:
        if port_handler is not None and port_handler.is_open:
            port_handler.closePort()
            print("[INFO] 串口已关闭。")


if __name__ == "__main__":
    raise SystemExit(main())
