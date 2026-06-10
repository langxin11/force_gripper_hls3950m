# HLS3950 力控夹爪

面向飞特 HLS3950 总线舵机的双指力控夹爪项目。本仓库从通信、控制、机械和上位机四个层面重新设计，目标是保留原力控夹爪的研究能力，同时解除对 DYNAMIXEL 协议和特定机械尺寸的依赖。

> 当前状态：架构与可测试控制骨架已建立；首阶段使用电脑、飞特 URT-1 和固定版本的 `FTServo_Python` 完成真机台架验证。

## 设计原则

- 控制算法不直接依赖 Arduino、串口库或具体舵机协议。
- HLS3950 通信封装在 `ServoBus` 适配层，便于仿真和单元测试。
- 上位机只使用稳定的高层命令，不感知舵机寄存器。
- 失联、部分写入失败和急停都进入可观察的故障状态。
- 关键设计、装配和调试文档默认使用中文。

## 仓库结构

```text
firmware/   可移植 C++ 控制核心、硬件适配层和单元测试
software/   Python SDK、命令行工具和上位机测试
hardware/   CAD、打印件、接线图和 BOM
docs/       中文架构、适配、开发与决策记录
```

## 快速验证

验证固件控制核心：

```bash
cmake -S firmware -B build/firmware
cmake --build build/firmware
ctest --test-dir build/firmware --output-on-failure
```

验证 Python 上位机：

```bash
PYTHONPATH=software/src python -m unittest discover -s software/tests -v
PYTHONPATH=software/src python -m hls3950_gripper.cli --simulate status
```

## 文档

- [总体架构](docs/architecture.md)
- [HLS3950 适配清单](docs/hls3950-adaptation.md)
- [开发与测试](docs/development.md)
- [实施路线图](docs/roadmap.md)

严格构建文档或启动本地预览：

```bash
make docs
make docs-serve
```

## 开源许可

许可证尚未确定。在添加明确的 `LICENSE` 文件前，不应假定本仓库代码可按某种开源许可证再分发。
