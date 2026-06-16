# HLS3950 Gripper Python SDK

HLS3950 力控夹爪的 Python 上位机 SDK 和命令行工具。

## 目录结构

```text
src/hls3950_gripper/    SDK 包（client、transport、cli）
tests/                   单元测试
```

## 快速开始

零依赖仿真测试：

```bash
make test-software
PYTHONPATH=software/src python3 -m hls3950_gripper.cli --simulate status
```

真机台架依赖（需要 HLS3950 和 URT-1）：

```bash
uv sync --extra hardware
```

## 文档

完整设计、协议和开发流程见[项目文档](../docs/index.md)。
