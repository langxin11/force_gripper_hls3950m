"""HLS3950 诊断脚本的串口总线工具集。"""

from __future__ import annotations

from dataclasses import dataclass

try:
    import scservo_sdk as scs
    from vassar_feetech_servo_sdk import find_servo_port
except ImportError as exc:  # pragma: no cover - 依赖真机环境
    raise SystemExit(
        "缺少真机调试依赖。请先执行: uv sync --project software --extra hardware"
    ) from exc


HLS_PHASE_ADDR = 18


@dataclass(frozen=True, slots=True)
class ServoSnapshot:
    """从一台 HLS3950 舵机捕获的遥测快照。

    Attributes:
        servo_id: TTL 总线上的目标舵机 ID。
        model_number: ``ping`` 返回的型号值。
        position: 当前位置寄存器值。
        voltage_volts: 当前电压（伏特）。
        temperature_celsius: 当前温度（摄氏度）。
        current_raw: 舵机电流寄存器的无符号值。
        current_signed: 电流寄存器的有符号解读。
        phase: 当前相位寄存器值。
        moving: 舵机是否报告运动状态。
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
        """生成终端友好格式的多行输出。

        Returns:
            可直接打印到终端的多行可读文本。
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

    def format_summary(self) -> str:
        """生成紧凑的单行摘要。

        Returns:
            当前舵机状态的一行可读文本。
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


def resolve_port(port: str | None) -> str:
    """确定要使用的串口。

    Args:
        port: 用户指定的串口，或 ``None`` 表示自动探测。

    Returns:
        具体的串口路径。
    """

    if port:
        return port
    return str(find_servo_port())


def require_success(
    operation: str,
    packet_handler: scs.hls,
    comm_result: int,
    error: int,
) -> None:
    """舵机通信失败时抛出描述性异常。

    Args:
        operation: 操作名称（用于错误消息）。
        packet_handler: 当前 HLS 数据包处理器。
        comm_result: SDK 通信状态码。
        error: 舵机状态错误位域。

    Raises:
        RuntimeError: 通信或舵机状态异常时抛出。
    """

    if comm_result != scs.COMM_SUCCESS:
        raise RuntimeError(f"{operation} 失败: {packet_handler.getTxRxResult(comm_result)}")
    if error != 0:
        raise RuntimeError(f"{operation} 返回舵机错误: {packet_handler.getRxPacketError(error)}")


def open_bus(port: str, baudrate: int) -> tuple[scs.PortHandler, scs.hls]:
    """打开串口总线并创建 HLS 数据包处理器。

    Args:
        port: 串口路径。
        baudrate: 请求波特率。

    Returns:
        已打开的端口处理器和 HLS 数据包处理器。

    Raises:
        RuntimeError: 无法打开端口或设置波特率时抛出。
    """

    port_handler = scs.PortHandler(port)
    if not port_handler.openPort():
        raise RuntimeError(f"无法打开串口: {port}")
    if not port_handler.setBaudRate(baudrate):
        port_handler.closePort()
        raise RuntimeError(f"无法设置波特率: {baudrate}")
    return port_handler, scs.hls(port_handler)


def read_snapshot(packet_handler: scs.hls, servo_id: int) -> ServoSnapshot:
    """读取一台 HLS3950 舵机的遥测快照。

    Args:
        packet_handler: 已初始化的 HLS 数据包处理器。
        servo_id: 要查询的舵机 ID。

    Returns:
        从 ping 和状态寄存器填充的快照。
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
