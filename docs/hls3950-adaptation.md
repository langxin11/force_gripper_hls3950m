# HLS3950 适配清单

## 官方库选择

当前台架控制器使用 Arduino Uno R3 和飞特驱动板，因此采用飞特官方
[`FTServo_Arduino`](https://github.com/ftservo/FTServo_Arduino) 库，并固定到
`release-v2.0.0`。HLS3950 属于 HLS 系列，应用层必须使用 `HLSCL`，不能使用
面向 SMS/STS 系列的 `SMS_STS` 类。

官方 `HLSCL` 已提供本项目需要的基础接口：

- `ServoMode()`、`WheelMode()` 和 `EleMode()`：切换角度、恒速和恒力模式；
- `WritePosEx()` 和 `SyncWritePosEx()`：单机和双机位置命令；
- `WriteEle()`：恒力模式目标扭矩命令；
- `EnableTorque()`：输出使能；
- `ReadPos()`、`ReadSpeed()`、`ReadCurrent()` 和 `FeedBack()`：状态反馈。

库的硬件接口通过公开的 `HardwareSerial *pSerial` 绑定串口。Uno R3 只有一个 USART，
因此首阶段把硬件 `Serial`（D0/RX、D1/TX）专用于飞特驱动板和舵机总线。此时 USB
串口与舵机总线共享同一 UART，不能同时作为稳定的上位机命令通道。

其他官方库的定位如下：

| 使用场景 | 官方库 | 本项目是否采用 |
| --- | --- | --- |
| Arduino Uno R3 台架验证 | `FTServo_Arduino` | 是，使用 `HLSCL` |
| PC 通过飞特 USB 转接板直接控制 | `FTServo_Python` | 驱动板支持 USB 时作为优先路线 |
| Linux C++ 进程直接控制 | `FTServo_Linux` | 否 |
| STM32Cube HAL 裸机项目 | `FTServo_stm32HAL` | 否 |

## 电脑直接控制

如果现有飞特驱动板是 URT 或其他“USB 转飞特总线”型号，连接电脑后能够出现
`/dev/ttyUSB*`、`/dev/ttyACM*` 或 Windows COM 端口，则可以不经过 Uno，直接采用：

```text
电脑 -> USB -> 飞特驱动板/URT -> HLS3950 总线
                    |
                 外部 12V 电源
```

这种方案更适合当前项目的上位机、数据记录和 ROS 集成，避免 Uno R3 单串口和 2KB SRAM
的限制。官方 `FTServo_Python` 仓库已经包含 `hls` 类以及 `hls/ping.py`、
`hls/read_write.py` 示例，官方示例默认设备也是 `/dev/ttyUSB0`。

需要注意：PyPI 的 `ftservo-python-sdk==2.0.0` wheel 发布于 HLS 模块加入之前，实际不包含
`scservo_sdk/hls.py`。本项目不能只声明该 PyPI 包；应固定飞特 GitHub 中包含 HLS 的提交，
或把经过许可证审查的 HLS SDK 代码作为受控依赖引入。

当前 Python `hls` 类已封装位置、速度和同步写入，但没有像 Arduino `HLSCL` 那样提供完整的
`EleMode()`、`WriteEle()` 和 `ReadCurrent()` 便捷方法。底层通用读写 API 仍可访问模式地址
`33`、目标扭矩地址 `44` 和当前电流地址 `69`，这些方法应集中实现在本仓库的
`FeetechHlsTransport` 中，不能散落在业务代码里。

电脑直控适合位置控制、测试和非硬实时的低频力控。Linux/USB 串口不是硬实时系统，最终力控
频率必须实测；急停建议采用独立的动力切断装置，而不是只依赖 Python 进程。

## Uno R3 的定位

Uno R3 适合完成以下工作：

- 扫描 ID、修改 ID 和确认 1 Mbps 通信；
- 单机位置、恒力模式和反馈读取测试；
- 双机同步位置命令与轮询频率测试；
- 验证飞特驱动板的接线、供电和半双工收发。

Uno R3 不适合作为本项目最终完整控制器，原因是官方规格只有一个 USART 和 2KB SRAM。
`FTServo_Arduino` 的 `SCSerial` 直接使用 `HardwareSerial`，所以硬件串口被舵机总线占用；
再使用 JSON、USB 上位机通信、双机反馈缓存和力控状态机会让内存和时序余量过小。

最终控制器优先选择具有“原生 USB CDC + 独立硬件 UART”或至少两个硬件 UART 的平台。
Uno 上验证通过的 `HLSCL` 适配层可以保留，控制核心无需重写。

## Uno 与飞特驱动板接线原则

在没有确认驱动板具体型号前，只确定以下原则，不在文档中猜测端子顺序：

- Uno `D1/TX`、`D0/RX` 和 GND 连接到驱动板的控制侧接口；
- HLS3950 的 12V 动力电源从驱动板的外部电源端进入，不从 Uno 的 5V、VIN 或 USB 取电；
- Uno、驱动板和 12V 电源负极必须共地；
- 驱动板动力回路需要能承受两台舵机的实测峰值电流；不能仅凭“可驱动舵机”判断载流能力；
- 上传程序时如出现串口冲突，应断开驱动板的 D0/D1，再上传后恢复连接；
- 运行舵机总线时不要通过 USB 串口监视器发送数据，避免与总线争用。

飞特驱动板的准确型号、接口照片和说明书仍需记录。若它是 USB 转总线型号，可直接使用
`FTServo_Python` 做 PC 台架测试，Uno 可以暂时不参与；若它是 TTL 半双工接口板，则使用
`FTServo_Arduino`。

## 必须取得的资料

1. HLS3950 对应硬件版本的官方用户手册。
2. 串口总线协议、寄存器表和错误码说明。
3. 接口电平、连接器引脚定义和半双工收发电路要求。
4. 位置、速度、电流和温度反馈的单位与符号定义。
5. 恒流、力矩或连续旋转模式的进入条件和保护限制。

## 电气验证

- HLS3950 官方额定输入范围为 9V 至 12.6V，本项目以稳定 12V 为设计点。
- 测量单机空载、启动、堵转保护触发前的峰值电流。
- 两台舵机电源独立于 Uno 的 USB、5V 和 VIN，并保证信号地共地。
- 两台 HLS3950 官方堵转电流合计约 4.8A，电源和驱动板动力回路必须按实测峰值留余量。
- 电源、线束、连接器和保险保护按实测峰值留出余量。
- 使用示波器检查双机启动时母线压降和总线信号完整性。

## 固件验证顺序

1. 单机只读：扫描 ID，读取型号、位置、电压和温度。
2. 单机低输出：验证扭矩开关、方向、单位和限幅。
3. 单机保护：验证超时、断线、过流和过温行为。
4. 双机通信：验证轮询频率、总线冲突和最坏响应时间。
5. 脱离传动机构完成连续运行测试。
6. 接入皮带后从 10% 输出开始标定开合方向和行程。

## 机械接口

完整范围见[机械改造清单](mechanical-changes.md)。核心原则是把电机座、25T 花键连接件
和 HTD3M 皮带轮拆成独立参数化零件，并增加机械限位和动力配电安装位。

## 已确认能力

- HLS3950 官方参数给出 0 至 4096 对应 360 度、25T/OD5.9mm 花键和 9V 至 12.6V 输入。
- 官方产品页明确给出恒流模式、位置/速度/电流/温度反馈和地址 44 目标扭矩。
- 官方 `HLSCL` 提供双机同步位置写入，因此位置模式不需要依赖两次独立串口写入。

## 未决问题

- HLS3950 是否能在所需频率下同时返回位置和电流。
- 恒流模式能否稳定用于低速夹持，而非仅作为电机内部限制值。
- 现有飞特驱动板的具体型号、接口定义和持续载流能力。
- Uno R3 在 1 Mbps 下通过该驱动板切换收发的稳定性和最大反馈频率。

## 官方资料

- [飞特 HLS3950 产品页与规格书入口](https://www.feetechrc.com/563788.html)
- [飞特 FTServo_Arduino](https://github.com/ftservo/FTServo_Arduino)
- [HLSCL 头文件和寄存器定义](https://github.com/ftservo/FTServo_Arduino/blob/main/src/HLSCL.h)
- [OpenRB-150 官方规格](https://emanual.robotis.com/docs/en/parts/controller/openrb-150/)
- [Arduino Uno R3 官方资料](https://docs.arduino.cc/hardware/uno-rev3/)
