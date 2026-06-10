# 主机通信协议

控制板与上位机使用 UTF-8 JSON Lines：每条请求和响应都是一行完整 JSON，以换行符结束。该协议只表达夹爪级命令，不暴露 HLS3950 寄存器。

## 通用响应

成功：

```json
{"ok":true,"status":{"initialized":true,"enabled":false,"fault":null,"left_position":0,"right_position":0}}
```

失败：

```json
{"ok":false,"error":"controller_disabled"}
```

## 命令

初始化：

```json
{"command":"initialize"}
```

使能和关闭：

```json
{"command":"enable"}
{"command":"disable"}
```

查询状态：

```json
{"command":"status"}
```

归一化位置命令：

```json
{"command":"position","left":0.25,"right":0.75}
```

`left` 和 `right` 范围为 `0.0` 到 `1.0`。具体开合方向由标定参数决定，不由上位机猜测电机正反方向。

## 兼容性规则

- 新增字段时，接收方应忽略不认识的可选字段。
- 删除字段或改变字段含义属于破坏性变更，需要增加协议版本。
- 错误使用稳定的机器可读字符串；中文解释由上位机根据错误码显示。
- 控制板必须限制单行最大长度，并对无效 JSON 返回错误而不是执行部分命令。
