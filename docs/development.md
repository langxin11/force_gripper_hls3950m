# 开发与测试

## 固件核心

控制核心只依赖标准 C++17，可以在没有控制板和舵机的电脑上编译测试：

```bash
cmake -S firmware -B build/firmware
cmake --build build/firmware
ctest --test-dir build/firmware --output-on-failure
```

新增控制逻辑时，应先使用 `FakeServoBus` 覆盖正常、断线和部分写入失败场景，再接入后续真实总线实现。

## Python 上位机

零依赖测试和仿真命令：

```bash
uv run --project software --extra dev pytest software/tests -v
PYTHONPATH=software/src python3 -m hls3950_gripper.cli --simulate status
```
pytest 兼容 unittest.TestCase，无需改写已有测试。

```bash
```

开发环境安装：

```bash
uv venv
uv pip install -e 'software[dev,docs]'
```

## 提交前检查

首次安装 Git 提交钩子：

```bash
uv run --project software --extra dev pre-commit install
```

钩子会在提交时检查基础文件格式、YAML 和 Python Ruff 规则。也可以手动检查仓库中的全部文件：

```bash
make hooks
```

完整检查包括固件与上位机测试、静态检查和文档严格构建：

```bash
make check
```

依赖下载需要网络；基础 C++ 和 Python 单元测试不需要下载第三方依赖。

## 参见

- [总体架构](architecture.md)：控制核心的分层设计和安全边界。
- [主机通信协议](host-protocol.md)：命令格式和错误语义。
- [HLS3950 通信适配](hls3950-adaptation.md)：真机 SDK 安装和台架验证顺序。
