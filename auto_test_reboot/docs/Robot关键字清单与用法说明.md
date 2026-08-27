# Robot 关键字清单与用法说明

本文档记录当前 `auto_test_reboot` 工程里可以直接在 Robot 用例中使用的关键字，包括 Python Library 关键字和 resource 里封装的业务关键字。

当前主要入口文件：

- `auto_test_reboot/tests/power_can_basic3.robot`
- `auto_test_reboot/resources/power_can_basic3.resource`
- `auto_test_reboot/libraries/HardwareLibrary.py`

## 1. Runtime 运行配置

| 关键字 | 作用 | 用法示例 |
| --- | --- | --- |
| `Configure Runtime` | 配置是否干跑硬件、时间缩放比例。`dry_run=false` 表示真跑硬件。 | `Configure Runtime    false    1.0` |

说明：

- `dry_run=true`：只跑流程，不控制真实硬件。
- `dry_run=false`：连接并控制真实程控电源、继电器、CAN 盒。
- `time_scale=1.0`：真实时间。
- `time_scale=0.01`：把等待时间缩短到 1%，常用于 Jenkins 流程调试。

## 2. 电源控制关键字

| 关键字 | 作用 | 用法示例 |
| --- | --- | --- |
| `Configure Power Supply` | 配置程控电源参数，目前主要用于设置默认电流。 | `Configure Power Supply    current=2.0` |
| `Connect Power Supply Usb` | 搜索并连接 USB 程控电源。 | `Connect Power Supply Usb` |
| `Close Power Supply Usb` | 断开程控电源连接。 | `Close Power Supply Usb` |
| `Set Power Current` | 设置程控电源电流。 | `Set Power Current    2.0` |
| `Set Power Voltage` | 设置程控电源电压，可指定输出开关。 | `Set Power Voltage    12.0    on` |
| `Ramp Power Voltage` | 按步进方式在指定时间内调节电压。 | `Ramp Power Voltage    12.0    15.0    5    20` |
| `Power Off To Zero` | 设置电压到 0V 并关闭输出。 | `Power Off To Zero` |

常用流程：

```robot
Connect Power Supply Usb
Power Off To Zero
Wait Seconds    3
Set Power Current    2.0
Set Power Voltage    0    on
Ramp Power Voltage    0    12.0    2    20
```

## 3. 继电器控制关键字

| 关键字 | 作用 | 用法示例 |
| --- | --- | --- |
| `Connect Relay Usb` | 连接 USB 继电器。 | `Connect Relay Usb` |
| `Close Relay Usb` | 断开 USB 继电器连接。 | `Close Relay Usb` |
| `Set Relay Channel` | 设置指定通道为闭合或断开。 | `Set Relay Channel    1    close` |
| `Close Relay Channel` | 闭合指定继电器通道。 | `Close Relay Channel    1` |
| `Open Relay Channel` | 断开指定继电器通道。 | `Open Relay Channel    1` |
| `Set All Relays` | 设置所有继电器通道。 | `Set All Relays    open` |
| `Close All Relays` | 闭合所有继电器。 | `Close All Relays` |
| `Open All Relays` | 断开所有继电器。 | `Open All Relays` |

说明：

- `close` 表示继电器闭合/导通。
- `open` 表示继电器断开/不导通。

## 4. CAN 连接与运行关键字

| 关键字 | 作用 | 用法示例 |
| --- | --- | --- |
| `Configure Can Simulation` | 配置 CAN ID 格式、波特率、通道。 | `Configure Can Simulation    11bit    500000    0` |
| `Start Can Simulation` | 打开 CAN 盒并启动模拟线程，开始响应设备请求。 | `Start Can Simulation` |
| `Stop Can Simulation` | 停止 CAN 模拟并关闭连接。 | `Stop Can Simulation` |
| `Close Can Connection` | 关闭 CAN 连接。 | `Close Can Connection` |

说明：

- `Configure Can Simulation` 第 1 个参数：`11bit` 或 `29bit`。
- 第 2 个参数：`250000` 或 `500000`。
- 第 3 个参数：CAN 通道号，目前常用 `0`。
- CAN 当前是请求-响应模式，不是主动广播所有 PID。

## 5. CAN PID 与信号配置关键字

| 关键字 | 作用 | 用法示例 |
| --- | --- | --- |
| `Set Can Signal Value` | 按字段名设置固定值。推荐用于业务字段。 | `Set Can Signal Value    A    85` |
| `Set Can Signal Range` | 按字段名设置范围值，模拟动态波动。 | `Set Can Signal Range    speed    60    125` |
| `Set Can Pid Value` | 按 Mode 01 PID 设置固定值。 | `Set Can Pid Value    0x0D    88` |
| `Set Can Pid Range` | 按 Mode 01 PID 设置范围值。 | `Set Can Pid Range    0x0C    1000    3000` |
| `Set Can Field Value` | `Set Can Signal Value` 的兼容别名。 | `Set Can Field Value    A    85` |
| `Set Can Field Range` | `Set Can Signal Range` 的兼容别名。 | `Set Can Field Range    speed    60    125` |
| `Set Can Rpm Range` | 专门设置 rpm 动态范围。 | `Set Can Rpm Range    1000    3000` |
| `Set Can Raw Pid Response` | 直接覆盖某个 service/pid 的原始响应 payload。高级调试用。 | `Set Can Raw Pid Response    0x01    0x0D    7B` |

推荐优先级：

1. 普通业务用 `Set Can Signal Value` / `Set Can Signal Range`。
2. 明确知道标准 PID 时，可用 `Set Can Pid Value` / `Set Can Pid Range`。
3. 需要临时验证特殊报文时，才使用 `Set Can Raw Pid Response`。

## 6. WWH-OBD Current DTC 关键字

| 关键字 | 作用 | 用法示例 |
| --- | --- | --- |
| `Set Wwh Obd Current Dtc` | 设置、覆盖、删除或清空 Current DTC。 | `Set Wwh Obd Current Dtc    set    0101    0202` |
| `Clear Wwh Obd Current Dtc` | 清空 Current DTC。 | `Clear Wwh Obd Current Dtc` |

`Set Wwh Obd Current Dtc` 的 function 支持：

| function | 作用 |
| --- | --- |
| `set` | 设置/覆盖当前 DTC 列表 |
| `replace` | 同 `set` |
| `override` | 同 `set` |
| `update` | 同 `set` |
| `remove` | 删除指定 DTC |
| `delete` | 同 `remove` |
| `clear` | 清空所有 Current DTC |

Demo：

```robot
Set Wwh Obd Current Dtc    set    0101    0202
Set Wwh Obd Current Dtc    set    0101    0202    0103    0102
Set Wwh Obd Current Dtc    remove    0202
Set Wwh Obd Current Dtc    clear
Set Wwh Obd Current Dtc    set    0101    0202    0103    0102
```

当前“增加 DTC”的推荐写法是重新 `set` 一个包含新增 DTC 的完整列表。

## 7. 通用辅助关键字

| 关键字 | 作用 | 用法示例 |
| --- | --- | --- |
| `Wait Seconds` | 等待指定秒数，受 `TIME_SCALE` 影响。 | `Wait Seconds    60` |
| `Cleanup Hardware` | 清理 CAN、电源、继电器连接，通常用于 Suite/Test Teardown。 | `Cleanup Hardware` |

## 8. resource 封装关键字：电源

这些关键字定义在 `power_can_basic3.resource`，属于业务层封装，用来让主流程更清晰。

| 关键字 | 作用 | 展开逻辑 |
| --- | --- | --- |
| `Power Connect And Reset To Zero` | 连接电源并归零。 | `Connect Power Supply Usb` -> `Power Off To Zero` |
| `Power On And Ramp To High` | 先等待 3 秒，再从 0V 上到 12V，等待联网，再从 12V 升到 15V。 | 等待 -> 设置电流 -> 0V 输出 -> 0 到 12V -> 等待 60 秒 -> 12 到 15V |
| `Power Ramp Back To Normal` | 电压从 15V 回落到 12V。 | `Ramp Power Voltage    15.0    12.0    5    20` |
| `Power Wait Off And Disconnect` | 等待 90 秒，电压归零并断开电源。 | `Wait Seconds` -> `Power Off To Zero` -> `Close Power Supply Usb` |

## 9. resource 封装关键字：继电器

| 关键字 | 作用 | 展开逻辑 |
| --- | --- | --- |
| `Relay Connect And Turn On` | 连接继电器并闭合指定通道。 | `Connect Relay Usb` -> `Set Relay Channel    1    close` |
| `Relay Turn Off And Disconnect` | 断开继电器通道并关闭连接。 | `Set Relay Channel    1    open` -> `Close Relay Usb` |

## 10. resource 封装关键字：CAN

| 关键字 | 作用 | 说明 |
| --- | --- | --- |
| `Can Configure Default Dynamic Profile` | 配置默认动态 CAN 数据。 | 包含 speed、rpm、A-Z 多个范围值 |
| `Demo Can Signal Range Settings` | 范围值配置 demo。 | 展示 speed/rpm/A/P/R 等字段范围写法 |
| `Demo Can Signal Fixed Value Settings` | 固定值配置 demo。 | speed/rpm 保持小范围波动，其余字段固定 |
| `Demo Wwh Obd Current Dtc Settings` | DTC 增加、删除、覆盖 demo。 | 展示 set/remove/clear 的效果 |
| `Can Run Simulation` | 配置默认 CAN 动态数据并运行。 | `Can Configure Default Dynamic Profile` -> `Start Can Simulation` -> `Wait Seconds` |
| `Can Stop And Disconnect` | 停止 CAN 并断开连接。 | `Stop Can Simulation` -> `Close Can Connection` |

## 11. 主流程封装关键字

| 关键字 | 作用 | 当前流程 |
| --- | --- | --- |
| `Run Power Can Basic3 Flow` | 执行 basic3 的完整封装流程。 | 配置运行环境 -> 电源上电 -> 继电器打开 -> CAN 运行 -> 电压回落 -> CAN 停止 -> 继电器断开 -> 电源断开 |

## 12. 当前建议用法

日常写业务用例时，推荐优先使用这些关键字：

```robot
Configure Runtime
Connect Power Supply Usb
Power Off To Zero
Set Power Current
Set Power Voltage
Ramp Power Voltage
Connect Relay Usb
Set Relay Channel
Configure Can Simulation
Set Wwh Obd Current Dtc
Set Can Signal Range
Set Can Signal Value
Start Can Simulation
Wait Seconds
Stop Can Simulation
Close Can Connection
Close Relay Usb
Close Power Supply Usb
```

如果只是想跑标准封装流程，可以直接使用：

```robot
Run Power Can Basic3 Flow
```

如果想把流程写得最清楚，建议不要一开始就调用 `Run Power Can Basic3 Flow`，而是在测试用例中逐行写出每个步骤。
