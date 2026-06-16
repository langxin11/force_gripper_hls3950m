# 硬件目录

本目录用于存放 HLS3950 版本的机械和电气设计。

- `cad/`：参数化源文件和中性格式 STEP 文件。
- `print_parts/`：经过版本标记的 STL/3MF 打印文件。
- [`BOM.md`](BOM.md)：HLS3950 版本首版样机物料清单。
- `cad/force_gripper_xl430.step`：导入 Onshape 的原 XL430 夹爪装配参考模型。
- `print_parts/` 下的原始 STL：仅用于尺寸和装配校核，不代表已经适配 HLS3950。
- 后续增加接线图、皮带轮工程图和装配公差表。

当前机械适配在 [Onshape 文档](https://cad.onshape.com/documents/6b62f8794d0bbb7b41c1c997/w/e1534e929e40aaacf2109eb3/e/1d43023ae86ad55792d145ee) 中维护。CAD 已基本完成，尚待实物尺寸复核、打印和装配验证。

已实施的核心变更：

- 重新绘制与飞特 HLS3950 连接的基体，使安装孔位匹配舵机。
- 从动轮与基体左右安装耳改用 `5 mm × 35 mm` 光杆、`M4` 螺纹的塞打螺栓，不再使用圆柱销。
- 主动轮改为以轴心为中心、半径 `7 mm`（节圆直径 `14 mm`）的四孔圆周阵列，使用 `M3` 螺丝与舵机连接。

改造参数、复用范围和装配图片统一见[机械设计与装配](../docs/mechanical.md)。

## 参考模型来源

参考文件来自 [`Shua-Kang/force_gripper_hardware`](https://github.com/Shua-Kang/force_gripper_hardware)
提交 `ff68bf4fce071ca1d055616c89dba56ccfd226d8`。该参考仓库当前没有明确的许可证文件，
因此这些文件只用于本项目内部改型和尺寸校核，不受本仓库 Apache-2.0 许可覆盖；公开发布、再分发或商业使用前必须取得原作者授权。
