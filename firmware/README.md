# 固件控制核心

可移植 C++17 夹爪控制核心，通过抽象 `ServoBus` 接口与舵机层解耦。

## 结构

```text
core/include/    公开头文件（GripperController、ServoBus 接口）
core/src/        控制核心实现
tests/           单元测试（含 FakeServoBus）
```

## 编译与测试

```bash
cmake -S firmware -B build/firmware
cmake --build build/firmware
ctest --test-dir build/firmware --output-on-failure
```

不依赖硬件，可在任何 C++17 环境编译运行。

## 文档

架构设计见[总体架构](../docs/architecture.md)，开发流程见[开发与测试](../docs/development.md)。
