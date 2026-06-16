# HLS3950 通信适配

## 当前路线

电脑通过 `URT-1` 直接连接两台 HLS3950，当前选用社区维护的
[`vassar-feetech-servo-sdk==1.5.0`](https://github.com/vassar-robotics/feetech-servo-sdk)。
该版本同时提供高层 `ServoController` 和底层 `scservo_sdk.hls`。

安装真机依赖：

```bash
uv sync --project software --extra hardware
```

截至 2026-06-15，依赖来源的核对结果如下：

| 来源 | HLS 支持 | 结论 |
| --- | --- | --- |
| 官方 GitHub `FTServo_Python` | 包含 `scservo_sdk/hls.py` 和 `hls/` 示例 | 用于核对底层实现 |
| 官方 PyPI `ftservo-python-sdk==2.0.0` | wheel 和 sdist 均缺少 `scservo_sdk/hls.py` | 不能用于 HLS3950 |
| 社区 PyPI `vassar-feetech-servo-sdk==1.5.0` | wheel 和 sdist 均包含 HLS | 本项目当前选型 |

社区包内置的整个 `scservo_sdk` 目录与飞特官方提交
`a203373036723e0d98c6c49b67cf09a9ee299220` 逐文件一致，可以替代 Git 依赖。
它同样安装顶层 `scservo_sdk` 包，不应与 `ftservo-python-sdk` 同时安装。

当前直接使用社区包的 `ServoController` 开展台架验证，不额外实现包装层。使用时必须明确其行为：

- `connect()` 会检查各舵机相位，并把非零相位改为 `0`。
- `write_position()` 和 `write_torque()` 会按需切换工作模式并使能扭矩。
- `disconnect()` 会关闭所有已配置舵机的扭矩。
- 电流单位、扭矩方向和保护行为仍需使用 HLS3950 实物验证。

```text
电脑 -> USB -> 飞特驱动板/URT -> HLS3950 总线
                    |
                 外部 12V 电源
```

完整供电和引脚要求见 [URT-1 接线](urt1-wiring.md)。USB 串口不保证硬实时，控制频率和急停策略必须通过实测确定。

## 已确认信息

| 项目 | 当前结论 |
| --- | --- |
| 接口 | 三线 TTL，`5264-3P`，GND/Vcc/Signal |
| 电压 | 9V 至 12.6V，正式系统按 12V 设计 |
| 位置范围 | 0 至 4096 对应 360 度 |
| 输出接口 | 25T，外径约 5.9mm |
| SDK 能力 | 位置、速度和同步位置写入 |
| 底层地址 | 模式 33、目标扭矩 44、当前电流 69，仍需按手册和实机核对单位与行为 |

## 软件使用边界

当前仓库尚未实现 HLS3950 专用传输类。台架程序可以直接调用 `ServoController`；夹爪级的双机协调、行程限制、故障联停和力控逻辑仍属于本项目，不由通用舵机 SDK 代替。

## 台架验证顺序

1. 单机只读：扫描 ID，读取型号、位置、电压和温度。
2. 单机低输出：验证扭矩开关、方向、单位和限幅。
3. 单机保护：验证超时、断线、过流和过温行为。
4. 双机通信：验证轮询频率、总线冲突和最坏响应时间。
5. 脱离传动机构完成连续运行测试。
6. 接入皮带后从 10% 输出开始标定开合方向和行程。

## 未决问题

- 寄存器、错误码、反馈单位和符号需与对应硬件版本手册逐项核对。
- HLS3950 是否能以目标频率同时返回位置和电流。
- 恒流模式能否稳定用于低速夹持。
- URT-1 的动力通道持续载流能力，尤其是双机堵转附近的温升。
- URT-1 在双机 1 Mbps 下的稳定性和最大反馈频率。

## 官方资料

- [飞特 HLS3950 产品页与规格书入口](https://www.feetechrc.com/563788.html)
- [飞特 FTServo_Python](https://github.com/ftservo/FTServo_Python)
- [FTServo_Python HLS 模块](https://github.com/ftservo/FTServo_Python/blob/a203373036723e0d98c6c49b67cf09a9ee299220/scservo_sdk/hls.py)
- [官方 PyPI：ftservo-python-sdk](https://pypi.org/project/ftservo-python-sdk/)
- [社区 SDK：vassar-feetech-servo-sdk](https://github.com/vassar-robotics/feetech-servo-sdk)
