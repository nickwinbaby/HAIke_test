# CAN A-Z 字段映射与 Robot 配置参考

本文档用于对照当前 `power_can_basic3` 测试套件里的 CAN 字段配置方式，方便后期继续补 PID、补协议字段、补校验规则。

当前结论：

- `A-Z` 不是单纯显示列名。当前代码里已经把一部分 `A-Z` 做成了 Robot 可配置入口。
- `A/B/C...` 这类入口会被 `HardwareLibrary.py` 解析成 OBD Mode 01 PID、特殊信号字段，或者协议预留字段。
- 已映射到 OBD PID 的字段会真实影响 CAN 响应。
- 已映射到特殊信号的字段，目前主要打包进 `0x9A` 或 `0xB7` 这类扩展响应。
- 协议预留字段目前只保存配置并输出日志，还没有真实打进 CAN 响应。

## 1. Robot 里怎么配置

固定值使用：

```robot
Set Can Signal Value    A    85
Set Can Signal Value    speed    88
Set Can Signal Value    rpm    1500
```

范围值使用：

```robot
Set Can Signal Range    A    80    90
Set Can Signal Range    speed    60    125
Set Can Signal Range    rpm    2000    2010
```

注意：

- `Set Can Signal Value` 是固定值，格式是：字段名 + 固定值。
- `Set Can Signal Range` 是范围值，格式是：字段名 + 最小值 + 最大值。
- 不是同一个关键字里“填一个值就是固定值、填两个值就是范围值”。这是两个独立关键字。
- 推荐在 `Start Can Simulation` 之前完成字段配置。
- 同一个字段如果先设置范围值、再设置固定值，后面的固定值会覆盖前面的范围值；反过来也一样。

## 2. 当前 CAN 是怎么运行的

当前 CAN 模拟是 OBD 请求-响应模式：

1. Robot 执行 `Configure Can Simulation`，配置 CAN 位宽、波特率、通道。
2. Robot 执行 `Set Can Signal Range` 或 `Set Can Signal Value`，写入要模拟的数据规则。
3. Robot 执行 `Start Can Simulation`，CAN 盒开始打开并监听设备请求。
4. 设备请求某个 Mode 01 PID 或 Mode 09 InfoType 时，Python 根据当前配置返回响应。
5. 如果设备不请求某个 PID，模拟器不会主动把所有 PID 广播出去。

内部动态值更新周期当前是 `0.1s`。也就是说范围值会在后台持续刷新，但真正发出 CAN 响应的频率取决于设备请求频率。

## 3. 当前支持的 CAN 类型

当前 CAN 连接配置支持：

| 配置项 | 当前支持 |
| --- | --- |
| CAN ID 格式 | `11bit`、`29bit` |
| CAN 波特率 | `250000`、`500000` |
| 默认格式 | `11bit` |
| 默认波特率 | `500000` |
| 默认通道 | `0` |

Robot 示例：

```robot
Configure Can Simulation    11bit    500000    0
Configure Can Simulation    11bit    250000    0
Configure Can Simulation    29bit    500000    0
Configure Can Simulation    29bit    250000    0
```

这里最后一个 `0` 是 CAN 通道编号，也就是当前使用第 0 路 CAN 通道。

## 4. A-Z 字段当前映射表

| 字段 | 当前含义 | 映射类型 | 对应 PID / 信号 | 是否影响 CAN 响应 | Robot 示例 |
| --- | --- | --- | --- | --- | --- |
| `speed` | 车速 | Mode 01 PID | `0x0D` | 是 | `Set Can Signal Range    speed    60    125` |
| `rpm` | 发动机转速 | Mode 01 PID | `0x0C` | 是 | `Set Can Signal Range    rpm    2000    2010` |
| `A` | 发动机冷却液温度 | Mode 01 PID | `0x05` | 是 | `Set Can Signal Value    A    85` |
| `B` | 节气门位置 | Mode 01 PID | `0x11` | 是 | `Set Can Signal Value    B    92.9` |
| `C` | 发动机负荷 | Mode 01 PID | `0x04` | 是 | `Set Can Signal Value    C    5.8` |
| `D` | 进气流量 MAF | Mode 01 PID | `0x10`，并复用到 `0x66` | 是 | `Set Can Signal Value    D    0.1` |
| `E` | 进气温度 | Mode 01 PID | `0x0F` | 是 | `Set Can Signal Value    E    -23` |
| `F` | 进气压力 | Mode 01 PID | `0x0B` | 是 | `Set Can Signal Value    F    17` |
| `G` | 控制模块/车辆电压 | Mode 01 PID | `0x42` | 是 | `Set Can Signal Value    G    14.9` |
| `H` | 燃油液位 | Mode 01 PID | `0x2F` | 是 | `Set Can Signal Value    H    60` |
| `I` | 清除故障码后行驶距离 | Mode 01 PID | `0x31` | 是 | `Set Can Signal Value    I    17` |
| `J` | MIL 点亮后行驶距离 | Mode 01 PID | `0x21` | 是 | `Set Can Signal Value    J    17` |
| `K1` | 历史总里程 | 协议预留字段 | `historical_total_mileage` | 暂不影响 | `Set Can Signal Value    K1    123456` |
| `K2` | 历史总油耗 | 协议预留字段 | `historical_total_fuel_consumption` | 暂不影响 | `Set Can Signal Value    K2    6543` |
| `K3` | 历史总行驶时间 | 协议预留字段 | `historical_total_driving_time` | 暂不影响 | `Set Can Signal Value    K3    789` |
| `L` | 安全带状态 | 协议预留字段 | `seatbelt_status` | 暂不影响 | `Set Can Signal Value    L    1` |
| `M` | 里程表 | Mode 01 PID | `0xA6` | 是 | `Set Can Signal Value    M    12345` |
| `N` | 平均油耗 | 协议预留字段 | `average_fuel_consumption` | 暂不影响 | `Set Can Signal Value    N    88` |
| `O` | 里程单位 | 协议预留字段 | `odometer_unit` | 暂不影响 | `Set Can Signal Value    O    1` |
| `P` | 电池电量 / SOC | Mode 01 PID | `0x5B` | 是 | `Set Can Signal Value    P    93.3` |
| `Q` | 电池健康度 / SOH | Mode 01 PID | `0xB2` | 是 | `Set Can Signal Value    Q    93` |
| `R` | 电池包电流 | 特殊信号 | 打包进 `0x9A` | 是，需实测校准 | `Set Can Signal Value    R    12` |
| `S` | 电池包电压 | 特殊信号 | 打包进 `0x9A` | 是，需实测校准 | `Set Can Signal Value    S    360` |
| `T` | 充电状态 | 特殊信号 | 打包进 `0x9A` | 是，需实测校准 | `Set Can Signal Value    T    1` |
| `U` | 剩余里程 | 协议预留字段 | `remaining_range` | 暂不影响 | `Set Can Signal Value    U    456` |
| `V` | 电池包温度 | Mode 01 PID | `0xB7` | 是，需实测校准 | `Set Can Signal Value    V    25` |
| `W` | 下次保养里程 | 协议预留字段 | `next_service_distance` | 暂不影响 | `Set Can Signal Value    W    5000` |
| `X` | 发动机运行时间 | Mode 01 PID | `0x1F` | 是 | `Set Can Signal Value    X    17` |
| `Y` | 燃油类型 | Mode 01 PID | `0x51` | 是 | `Set Can Signal Value    Y    1` |
| `Z` | 转向灯状态 | 特殊信号 | 打包进 `0x9A` | 是，需实测校准 | `Set Can Signal Value    Z    1` |

## 5. 关键公式确认

### 5.1 车速 speed / 0x0D

车速 PID 是单字节：

```text
Vehicle speed = A
```

Robot 设置 `speed=125` 时，CAN 响应数据字节应为 `0x7D`。当前代码已经支持大于 100 的车速，例如 `120-125` 范围。

### 5.2 转速 rpm / 0x0C

转速 PID 是双字节：

```text
RPM = ((A * 256) + B) / 4
```

Robot 设置 `rpm=2000` 时，代码会编码为 `2000 * 4 = 8000`，也就是 `0x1F40`。

### 5.3 里程表 M / 0xA6

OBD 表公式：

```text
Odometer = ((A * 16777216) + (B * 65536) + (C * 256) + D) / 10
```

Robot 设置：

```robot
Set Can Signal Value    M    12345
```

CAN 响应会编码为原始值 `123450`，设备按 `/10` 解析后应得到 `12345 km`。这一点已经在代码里修正过，避免出现设置 `12345`、设备读到 `1234` 的问题。

### 5.4 进气流量 D / 0x10 和 0x66

`D` 映射常规 MAF，即 Mode 01 PID `0x10`：

```text
MAF = ((A * 256) + B) / 100
```

如果设备请求 Mode 01 PID `0x66`，当前代码会复用 `D / maf` 的值，并按扩展 MAF 公式编码：

```text
Sensor A = ((B * 256) + C) / 32
Sensor B = ((D * 256) + E) / 32
```

例如 `D=12.5` 时，`0x66` 会返回可解码为 `12.5 g/s` 的传感器 A/B。

### 5.5 R/S/T/Z / 0x9A

`0x9A` 是 Hybrid/EV vehicle system data。公开 OBD 表只说明它包含充电状态、电压、电流等子项，精确字节定义需要 J1979-DA 或设备实测确认。

当前工程为了配合现阶段验证，暂按 4.0 服务器数据流缩放方向打包：

```text
R 电池包电流: raw = (value + 1000) * 10
S 电池包电压: raw = value * 10
T 充电状态:  单字节
Z 转向灯状态: 单字节
```

这部分已经可以通过日志看到原始字节和解码值，但最终仍建议以设备实际上报结果校准。

### 5.6 V / 0xB7

`0xB7` 是 Hybrid/EV battery temperature data。公开表只说明它包含多类温度/状态子项，精确定义仍需 J1979-DA 或实测确认。当前代码返回电流、电压、温度组合，其中温度按 `raw - 40` 方向编码。

## 6. Mode 09 / VIN 当前支持情况

当前 Mode 09 已支持 `0x01` 到 `0x0B` 的 InfoType，其中 VIN 在 `0x09 0x02`：

| Mode 09 InfoType | 当前含义 | 当前响应 |
| --- | --- | --- |
| `0x01` | VIN 消息数量 | 已响应 |
| `0x02` | VIN | 已响应 |
| `0x03` | 校准 ID 消息数量 | 已响应 |
| `0x04` | 校准 ID | 已响应，默认 `CALID2026` |
| `0x05` | CVN 消息数量 | 已响应 |
| `0x06` | CVN | 已响应，默认 `12 34 56 78` |
| `0x07` | 性能跟踪消息数量 | 已响应 |
| `0x08` | 性能跟踪数据 | 已响应，默认 0 |
| `0x09` | ECU 名称消息数量 | 已响应 |
| `0x0A` | ECU 名称 | 已响应，默认 `ECM_AUTO_TEST` |
| `0x0B` | 性能跟踪数据 | 已响应，默认 0 |

当前 Robot 里还没有单独提供 `Set Vin` 关键字。VIN 默认来自 `can_core.py` 里的 `VIN` 常量。后续如果需要把 VIN 做成用例变量，可以新增类似：

```robot
Set Can Vin    LSVXXXXXXXXXXXXXX
```

## 6.1 WWH-OBD Current DTC 当前支持情况

当前已支持 WWH-OBD Current DTC，也就是设备请求当前故障码时，CAN 模拟器按 Robot 配置的 DTC 列表返回。

Robot 关键字：

```robot
Set Wwh Obd Current Dtc    set       0101    0202    0103    0102
Set Wwh Obd Current Dtc    remove    0202
Set Wwh Obd Current Dtc    clear
```

含义：

- `set` / `replace` / `override`：覆盖当前 DTC 列表。模拟器后续就按这个新列表响应。
- `remove` / `delete`：从当前 DTC 列表里删除指定 DTC。
- `clear`：清空当前 DTC 列表。清空后再请求 Current DTC，会返回 0 个 DTC。
- 当前“增加 DTC”的推荐写法是重新 `set` 一个更完整的新列表，例如先 `set 0101 0202`，再 `set 0101 0202 0103 0102`。

当前抓包已经确认 4 种组合均可看到 Current DTC 响应：

| CAN 类型 | 波特率 | 抓包结论 |
| --- | --- | --- |
| `11bit` | `500000` | 已看到 `03 -> 43` Current DTC 响应 |
| `11bit` | `250000` | 已看到 `03 -> 43` Current DTC 响应 |
| `29bit` | `500000` | 已看到 `03 -> 43` Current DTC 响应 |
| `29bit` | `250000` | 已看到 `03 -> 43` Current DTC 响应 |

典型响应流程：

```text
01 03
10 0A 43 04 01 01 02 02
30 00
21 01 03 01 02
```

解释：

- `03`：请求 Current DTC。
- `43`：Current DTC 响应，等于请求服务 `0x03 + 0x40`。
- `04`：当前返回 4 个 DTC。
- `0101 0202 0103 0102`：Robot 配置的 4 个 DTC。
- 因为响应内容超过单帧长度，所以走 ISO-TP 首帧、流控、连续帧。

## 7. basic3 默认动态配置

`power_can_basic3.resource` 里的 `Can Configure Default Dynamic Profile` 会给默认流程配置范围值。默认设计是代码一直跑范围值，只有你显式执行 `Set Can Signal Value` 或 `Set Can Signal Range` 后，才会按你的设置覆盖默认值。

当前默认动态配置摘要：

```robot
Set Can Signal Range    speed    0    120
Set Can Signal Range    rpm    1000    3000
Set Can Signal Range    A    80    90
Set Can Signal Range    B    0    100
Set Can Signal Range    C    0    100
Set Can Signal Range    D    0    10
Set Can Signal Range    E    -40    100
Set Can Signal Range    F    0    255
Set Can Signal Range    G    11    15.5
Set Can Signal Range    H    0    100
Set Can Signal Range    I    0    1000
Set Can Signal Range    J    0    1000
Set Can Signal Range    M    0    100000
Set Can Signal Range    N    0    20000
Set Can Signal Range    O    1    2
Set Can Signal Range    P    0    100
Set Can Signal Range    Q    0    100
Set Can Signal Range    R    -500    500
Set Can Signal Range    S    0    1000
Set Can Signal Range    T    0    3
Set Can Signal Range    U    0    1000
Set Can Signal Range    V    -40    100
Set Can Signal Range    W    0    50000
Set Can Signal Range    X    0    100000
Set Can Signal Range    Y    0    32
Set Can Signal Range    Z    0    3
```

其中 `K1/K2/K3/L/N/O/U/W` 目前属于“保存配置但不影响 CAN 响应”的预留字段。它们在 Robot 里能写，是为了先保留测试数据入口；后续需要把它们接到具体 PID、私有协议帧或者服务器数据校验逻辑里。

## 8. 固定值校验 demo

`power_can_basic3.resource` 里的 `Demo Can Signal Fixed Value Settings` 当前用于展示“车速和转速仍然保持小范围波动，其余字段固定”的写法：

```robot
Demo Can Signal Fixed Value Settings
    Set Can Signal Range    speed    60    125
    Set Can Signal Range    rpm    2000    2010
    Set Can Signal Value    A    85
    Set Can Signal Value    B    92.9
    Set Can Signal Value    C    5.8
    Set Can Signal Value    D    0.1
    Set Can Signal Value    E    -23
    Set Can Signal Value    F    17
    Set Can Signal Value    G    14.9
    Set Can Signal Value    H    60
    Set Can Signal Value    I    17
    Set Can Signal Value    J    17
    Set Can Signal Value    K1    123456
    Set Can Signal Value    K2    6543
    Set Can Signal Value    K3    789
    Set Can Signal Value    L    1
    Set Can Signal Value    M    12345
    Set Can Signal Value    N    88
    Set Can Signal Value    O    1
    Set Can Signal Value    P    93.3
    Set Can Signal Value    Q    93
    Set Can Signal Value    R    12
    Set Can Signal Value    S    360
    Set Can Signal Value    T    1
    Set Can Signal Value    U    456
    Set Can Signal Value    V    25
    Set Can Signal Value    W    5000
    Set Can Signal Value    X    17
    Set Can Signal Value    Y    1
    Set Can Signal Value    Z    1
```

这个 demo 与 `power_can_basic3.robot` 里的四条固定值遍历用例保持一致：

- `Power Can Basic3 Fixed Values 11bit 500K`
- `Power Can Basic3 Fixed Values 11bit 250K`
- `Power Can Basic3 Fixed Values 29bit 500K`
- `Power Can Basic3 Fixed Values 29bit 250K`

四条固定值遍历用例现在都已加入 Current DTC 设置，位置在 `Configure Can Simulation` 之后、`Set Can Signal Range    speed` 之前：

```robot
Set Wwh Obd Current Dtc    set    0101    0202    0103    0102
```

`power_can_basic3.resource` 里也提供了 DTC demo：

```robot
Demo Wwh Obd Current Dtc Settings
    Set Wwh Obd Current Dtc    set    0101    0202
    Set Wwh Obd Current Dtc    set    0101    0202    0103    0102
    Set Wwh Obd Current Dtc    remove    0202
    Set Wwh Obd Current Dtc    clear
    Set Wwh Obd Current Dtc    set    0101    0202    0103    0102
```

## 9. power_can_basic3.robot 当前用例结构

当前测试套件保留了 8 条用例：

| 用例名 | 作用 |
| --- | --- |
| `Power Can Basic3 Dynamic Flow` | 最简主流程，只调用 `Run Power Can Basic3 Flow` |
| `Power Can Basic3 Dynamic Flow Full Steps` | 中等展开版，方便看主流程关键阶段 |
| `Power Can Basic3 Dynamic Flow Plus` | 展开到具体 CAN 范围配置，但仍引用变量 |
| `Power Can Basic3 Dynamic Flow Plus Clear` | 展开到具体步骤，并把变量写成明确数值 |
| `Power Can Basic3 Fixed Values 11bit 500K` | 固定值校验版，11bit / 500K |
| `Power Can Basic3 Fixed Values 11bit 250K` | 固定值校验版，11bit / 250K |
| `Power Can Basic3 Fixed Values 29bit 500K` | 固定值校验版，29bit / 500K |
| `Power Can Basic3 Fixed Values 29bit 250K` | 固定值校验版，29bit / 250K |

## 10. 代码调用关系

以 `Set Can Signal Range    A    80    90` 为例：

```text
Robot 用例
  -> HardwareLibrary.set_can_signal_range("A", 80, 90)
    -> _resolve_can_field("A")
      -> A 被识别为 Mode 01 PID 0x05
    -> self.can.set_pid_range(0x05, 80, 90)
      -> HeadlessCanSimulator 每 0.1 秒生成 80-90 之间的随机值
      -> ObdIsoTpResponder 在设备请求 01 05 时返回当前值
```

以 `Set Can Signal Range    R    -500    500` 为例：

```text
Robot 用例
  -> HardwareLibrary.set_can_signal_range("R", -500, 500)
    -> _resolve_can_field("R")
      -> R 被识别为特殊信号 battery_pack_current
    -> self.can.set_signal_range("battery_pack_current", -500, 500)
      -> HeadlessCanSimulator 每 0.1 秒生成动态值
      -> ObdIsoTpResponder 在设备请求 01 9A 时把电流/电压/充电状态/转向灯状态打包返回
```

以 `Set Can Signal Value    M    12345` 为例：

```text
Robot 用例
  -> HardwareLibrary.set_can_signal_value("M", 12345)
    -> _resolve_can_field("M")
      -> M 被识别为 Mode 01 PID 0xA6
    -> self.can.set_pid_value(0xA6, 12345)
      -> ObdIsoTpResponder 在设备请求 01 A6 时编码为 raw=123450
      -> 设备按 raw / 10 解析为 12345 km
```

以 `Set Can Signal Value    N    88` 为例：

```text
Robot 用例
  -> HardwareLibrary.set_can_signal_value("N", 88)
    -> _resolve_can_field("N")
      -> N 被识别为协议预留字段 average_fuel_consumption
    -> self.can.set_protocol_field_value("average_fuel_consumption", 88)
      -> 当前只保存配置和日志，不改变 CAN 响应
```

## 11. 后续补充建议

后续如果要把当前协议做完整，建议按这个顺序补：

1. 先确认 `N/O/U/W/K1/K2/K3/L` 这些字段到底来自标准 OBD PID、UDS DID、私有 CAN 帧，还是服务器接口。
2. 如果来自标准 OBD PID，就补到 `CAN_SIGNAL_PID_ALIASES` 和 `can_core.py` 的 PID 响应里。
3. 如果来自 UDS DID，就补 `22 DID` 请求响应逻辑，不要硬塞到标准 Mode 01。
4. 如果来自私有 CAN 帧，就新增私有帧发送/响应逻辑。
5. 如果来自服务器接口，就在 Robot 里单独做数据校验关键字，不建议放进 CAN 模拟层。
