# 飞特 Python SDK 依赖说明

电脑通过飞特 USB 驱动板直接控制 HLS3950 时，应使用官方
<https://github.com/ftservo/FTServo_Python> 的 HLS 实现。

截至 2026-06-10，PyPI 包 `ftservo-python-sdk==2.0.0` 的 wheel 经文件清单核验，不包含
`scservo_sdk/hls.py`；官方 GitHub 当前主分支则包含 HLS 类和 HLS 示例。接入实现时应固定
一个具体 Git 提交，不直接跟随浮动的 `main`。

本项目计划实现 `FeetechHlsTransport`，统一封装：

- 串口打开、波特率和超时；
- ID 扫描与型号校验；
- 双机同步位置写入；
- 恒力模式、目标扭矩和当前电流读写；
- 通信错误转换、失联停机和状态统计。
