# Arduino Uno R3 台架适配

本目录用于首阶段 HLS3950 真机验证，不作为最终完整控制器实现。

如果飞特驱动板本身是 USB 转总线型号，优先使用电脑和 `FTServo_Python` 直接测试；Uno
仅用于离线控制、对照验证或后续本地安全控制实验。

## 选用库

- 官方仓库：<https://github.com/ftservo/FTServo_Arduino>
- 固定版本：`release-v2.0.0`
- HLS3950 应用类：`HLSCL`
- 不使用：`SMS_STS`、`SCSCL`

最小初始化形式：

```cpp
#include <HLSCL.h>

HLSCL hls;

void setup() {
    Serial.begin(1000000);
    hls.pSerial = &Serial;
}
```

实际测试程序还必须加入输出限幅、超时、扭矩关闭和错误处理，不能直接把示例中的高输出值用于已装配夹爪。

## 资源限制

Uno R3 只有一个 USART 和 2KB SRAM。硬件 `Serial` 连接舵机总线后，USB 串口不能再作为独立、可靠的上位机通道。因此本适配只覆盖：

1. 单机扫描和只读反馈；
2. 单机低输出位置/恒力测试；
3. 双机同步命令与反馈频率测试。

完整夹爪控制器应迁移到具有独立 USB 和额外硬件串口的平台。

## 待确认

- 飞特驱动板型号和控制侧引脚定义；
- 驱动板是否包含半双工方向控制；
- 驱动板动力通道的持续和峰值载流能力；
- 1 Mbps 下的可靠收发时序。
