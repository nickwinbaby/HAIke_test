# CAN 协议字段适配清单

本文档记录 `auto_test_reboot` 当前 CAN 模拟能力与 4.0 协议车况输出字段的对应关系。

## 配置方式

- 固定值：`Set Can Signal Value    字段名    值`
- 范围值：`Set Can Signal Range    字段名    最小值    最大值`
- 字段名可以使用输出列字母，例如 `A`、`R`、`Z`，也可以使用英文别名，例如 `coolant_temp`、`battery_current`。
- 已知 OBD PID 的字段会直接影响 CAN 响应。
- 标记为“协议字段已预留”的字段，目前只保存配置并输出日志，还没有明确的 CAN PID、UDS DID 或私有帧映射。

## A-Z 字段适配

| 输出列 | 协议字段 | 当前配置名示例 | CAN/OBD 映射 | 固定/范围支持 | 当前状态 |
|---|---|---|---|---|---|
| 转速 | Engine Speed | `rpm` | Mode01 PID `0x0C` | 支持 | 已适配，默认范围随机 |
| 车速 | Vehicle Speed | `speed` | Mode01 PID `0x0D` | 支持 | 已适配，默认范围随机 |
| A | 发动机冷却液温度 | `A` / `coolant_temp` | Mode01 PID `0x05` | 支持 | 已适配，公式 `raw - 40` |
| B | 节气门位置 | `B` / `throttle` | Mode01 PID `0x11` | 支持 | 已适配，百分比公式 |
| C | 发动机负荷 | `C` / `engine_load` | Mode01 PID `0x04` | 支持 | 已适配，百分比公式 |
| D | 进气流量 | `D` / `maf` | Mode01 PID `0x10`，并被 `0x66` 扩展 MAF 复用 | 支持 | 已适配；`0x66` 已按 `/32` 公式修正 |
| E | 进气温度 | `E` / `intake_temp` | Mode01 PID `0x0F` | 支持 | 已适配，公式 `raw - 40` |
| F | 进气压力 | `F` / `intake_pressure` | Mode01 PID `0x0B` | 支持 | 已适配 |
| G | 车辆电池电压 | `G` / `vehicle_battery_voltage` | Mode01 PID `0x42` | 支持 | 已适配，公式 `raw / 1000` |
| H | 油量 | `H` / `fuel_level` | Mode01 PID `0x2F` | 支持 | 已适配，百分比公式 |
| I | DTC 清除后距离 | `I` / `distance_since_clear_dtc` | Mode01 PID `0x31` | 支持 | 已适配 |
| J | 故障灯点亮后距离 | `J` / `distance_with_mil_on` | Mode01 PID `0x21` | 支持 | 已适配 |
| K1 | 历史总里程 | `K1` | 未确认 | 支持配置 | 协议字段已预留，当前不影响 CAN 响应 |
| K2 | 历史总油耗 | `K2` | 未确认 | 支持配置 | 协议字段已预留，当前不影响 CAN 响应 |
| K3 | 历史总行驶时间 | `K3` | 未确认 | 支持配置 | 协议字段已预留，当前不影响 CAN 响应 |
| L | 安全带状态 | `L` / `seatbelt_status` | 未确认 | 支持配置 | 协议字段已预留，当前不影响 CAN 响应 |
| M | 里程表 | `M` / `odometer` | Mode01 PID `0xA6` | 支持 | 已适配，按 `raw / 10 km` 公式编码 |
| N | 平均油耗 | `N` / `average_fuel_consumption` | 未确认 | 支持配置 | 协议字段已预留，当前不影响 CAN 响应 |
| O | 里程单位 | `O` / `odometer_unit` | 未确认 | 支持配置 | 协议字段已预留，当前不影响 CAN 响应 |
| P | SOC | `P` / `soc` | Mode01 PID `0x5B` | 支持 | 已适配，百分比公式 |
| Q | SOH | `Q` / `soh` | Mode01 PID `0xB2` | 支持 | 已适配，J1979-DA 高位 PID，需实测确认设备解析 |
| R | 电池包电流 | `R` / `battery_current` | Mode01 PID `0x9A` 子信号 | 支持 | 已适配，编码为 `(值 + 1000) * 10`，需实测校准 |
| S | 电池包电压 | `S` / `battery_pack_voltage` | Mode01 PID `0x9A` 子信号 | 支持 | 已适配，编码为 `值 * 10`，需实测校准 |
| T | 充电状态 | `T` / `charging_state` | Mode01 PID `0x9A` 子信号 | 支持 | 已适配，单字节状态，需实测校准 |
| U | 剩余里程 | `U` / `remaining_range` | 未确认 | 支持配置 | 协议字段已预留，当前不影响 CAN 响应 |
| V | 电池包温度 | `V` / `battery_temperature` | Mode01 PID `0xB7` | 支持 | 已适配，温度按 `raw - 40` 方向编码，需实测校准 |
| W | 下次保养里程 | `W` / `next_service_distance` | 未确认 | 支持配置 | 协议字段已预留，当前不影响 CAN 响应 |
| X | 发动机运行时间 | `X` / `engine_run_time` | Mode01 PID `0x1F` | 支持 | 已适配 |
| Y | 燃油类型 | `Y` / `fuel_type` | Mode01 PID `0x51` | 支持 | 已适配 |
| Z | 转向灯状态 | `Z` / `turn_signal_status` | Mode01 PID `0x9A` 子信号 | 支持 | 已适配，单字节状态，需实测校准 |

## 关键公式确认

### M / 0xA6 里程表

OBD 表公式：

```text
Odometer = ((A * 16777216) + (B * 65536) + (C * 256) + D) / 10
```

因此 Robot 设置：

```robot
Set Can Signal Value    M    12345
```

CAN 响应应编码为原始值 `123450`，设备按 `/10` 解析后得到 `12345 km`。

### D / 0x66 MAF 扩展数据

`D` 仍然代表常规 MAF，映射到 Mode01 PID `0x10`。如果设备请求 Mode01 PID `0x66`，当前代码会复用 `D / maf` 的值，并按扩展 MAF 公式编码：

```text
Sensor A = ((B * 256) + C) / 32
Sensor B = ((D * 256) + E) / 32
```

例如 `D=12.5` 时，`0x66` 会返回可解码为 `12.5 g/s` 的传感器 A/B。

### R/S/T/Z / 0x9A

`0x9A` 是 Hybrid/EV vehicle system data。公开 OBD 表只说明它包含充电状态、电压、电流等子项，精确字节定义需要 J1979-DA 或实测确认。

当前工程为了配合现阶段验证，暂按 4.0 服务器数据流缩放方向打包：

```text
R 电池包电流: raw = (value + 1000) * 10
S 电池包电压: raw = value * 10
T 充电状态:  单字节
Z 转向灯状态: 单字节
```

这部分已经可以通过日志看到原始字节和解码值，但最终仍建议以设备实际上报结果校准。

### V / 0xB7

`0xB7` 是 Hybrid/EV battery temperature data。公开表只说明它包含多类温度/状态子项，精确定义仍需 J1979-DA 或实测确认。当前代码返回电流、电压、温度组合，其中温度按 `raw - 40` 方向编码。

## 协议字段预留说明

`K1/K2/K3/L/N/O/U/W` 是 4.0 协议数据流里的字段，但目前没有在 OBD PID 表里找到一一对应的标准 Mode01 PID。

当前处理方式：

- Robot 可以写入这些字段，便于保留用例数据入口。
- Python 会保存这些配置并输出日志。
- 这些字段当前不会改变 CAN 响应。

后续如果要让这些字段真正由 CAN 模拟驱动，需要确认它们来自：

1. 标准 OBD PID；
2. UDS DID，例如设备日志中的 `22 xxxx`；
3. 私有 CAN 帧；
4. 服务器接口或业务校验逻辑。

确认映射后，再在 `HardwareLibrary.py` 增加别名映射，并在 `can_core.py` 增加对应响应编码。
