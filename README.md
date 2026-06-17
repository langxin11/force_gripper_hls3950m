# 基于飞特 HLS3950 的双指力控夹爪

面向飞特 HLS3950 总线舵机的双指力控夹爪项目，包含可测试控制核心、Python 上位机和机械适配资料。当前 CAD 和台架验证以 `HLS3950M-C001` 为基准，官网商品页也写作 `HL-3950-C001`；外形尺寸为 `45.22 mm × 24.72 mm × 35 mm` 且安装、输出轴、通信和供电接口匹配的飞特舵机也可作为候选，例如 `ST-3250-C001`、`ST-3235-C001` 和 `HL-3930-C001`。

> 当前状态：架构与可测试控制骨架已建立，HLS3950 机械适配 CAD 已基本完成；下一阶段使用电脑、飞特 URT-1 和 `vassar-feetech-servo-sdk==1.5.0` 完成尺寸复核、样机装配与真机台架验证。

## 项目来源

本项目基于 [`Shua-Kang/force_gripper_hardware`](https://github.com/Shua-Kang/force_gripper_hardware)
改造而来，当前重点是将原机械结构适配到飞特 HLS3950 及同尺寸候选舵机，并补充控制软件、接线说明和装配文档。
原参考仓库未见明确 `LICENSE` 文件，相关 STEP、STL 和图片资料的使用限制见 [hardware/README.md](hardware/README.md)。

## 仓库结构

```text
firmware/   可移植 C++ 控制核心与单元测试
software/   Python SDK、命令行工具和上位机测试
hardware/   CAD、打印件、接线图和 BOM
docs/       中文架构、适配、装配与开发文档
```

## 快速验证

```bash
cmake -S firmware -B build/firmware
cmake --build build/firmware
ctest --test-dir build/firmware --output-on-failure
uv run --project software --extra dev pytest software/tests -v
```

如果只验证 Python 上位机：

```bash
uv run --project software --extra dev pytest software/tests -v
```

更多开发命令（包括文档构建、静态检查）见[开发与测试](docs/development.md)。

## 文档

- [项目文档首页](docs/index.md)
- [主机通信协议](docs/host-protocol.md)
- [HLS3950 通信适配](docs/hls3950-adaptation.md)
- [机械设计与装配](docs/mechanical.md)
- [URT-1 接线](docs/urt1-wiring.md)
- [开发与测试](docs/development.md)

严格构建文档或启动本地预览：

```bash
uv run --project software --extra docs mkdocs build --strict
uv run --project software --extra docs mkdocs serve
```

## 开源许可

本仓库原创代码、文档和新增设计说明采用 [Apache License 2.0](LICENSE) 发布。
来自 `Shua-Kang/force_gripper_hardware` 的参考 STEP、STL 和图片资料，以及飞特官网图片/PDF 等第三方资料不自动纳入本仓库 Apache-2.0 许可；这些资料的使用限制以其来源说明为准。
