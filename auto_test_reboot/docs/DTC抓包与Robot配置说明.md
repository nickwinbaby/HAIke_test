# DTC 抓包与 Robot 配置说明

本文档记录 `auto_test_reboot` 当前 WWH-OBD Current DTC 的抓包结论、Robot 配置方式和代码调用关系。

## 1. 当前结论

当前已经确认 `11bit 500K`、`11bit 250K`、`29bit 500K`、`29bit 250K` 四种组合都可以看到 WWH-OBD Current DTC 响应。

| 抓包文件 | CAN ID 格式 | 波特率 | 结论 |
| --- | --- | --- | --- |
| `DTC-11B-500K-1.txt` | `11bit` | `500000` | 已看到 `03 -> 43` Current DTC 响应 |
| `DTC-11B-250K.txt` | `11bit` | `250000` | 已看到 `03 -> 43` Current DTC 响应 |
| `DTC-29B-500K-1.txt` | `29bit` | `500000` | 已看到 `03 -> 43` Current DTC 响应 |
| `DTC-29B-250K.txt` | `29bit` | `250000` | 已看到 `03 -> 43` Current DTC 响应 |

29bit 和 11bit 的主要区别是 CAN ID 寻址方式不同，Current DTC 的业务数据本身一致。

## 2. 典型报文

以当前配置：

```robot
Set Wwh Obd Current Dtc    set    0101    0202    0103    0102
```

抓包里可以看到类似流程：

```text
01 03
10 0A 43 04 01 01 02 02
30 00
21 01 03 01 02
```

含义：

| 内容 | 含义 |
| --- | --- |
| `03` | 请求 Current DTC |
| `43` | Current DTC 响应，等于 `0x03 + 0x40` |
| `04` | 返回 4 个 DTC |
| `0101` | 第 1 个 DTC |
| `0202` | 第 2 个 DTC |
| `0103` | 第 3 个 DTC |
| `0102` | 第 4 个 DTC |
| `10 0A` | ISO-TP 首帧，总长度 10 字节 |
| `30 00` | 设备发出的流控帧 |
| `21 ...` | ISO-TP 连续帧 |

## 3. Robot 关键字

当前关键字是：

```robot
Set Wwh Obd Current Dtc    function    DTC1    DTC2    ...    DTCN
```

`function` 支持：

| function | 作用 |
| --- | --- |
| `set` | 设置/覆盖当前 DTC 列表 |
| `replace` | 同 `set`，覆盖当前 DTC 列表 |
| `override` | 同 `set`，覆盖当前 DTC 列表 |
| `update` | 同 `set`，覆盖当前 DTC 列表 |
| `remove` | 从当前列表删除指定 DTC |
| `delete` | 同 `remove` |
| `clear` | 清空所有 Current DTC |

## 4. 增加、删除、覆盖 Demo

当前模拟器的核心逻辑是“当前 DTC 列表是什么，就按什么响应”。因此推荐这样理解：

- 增加：重新 `set` 一个包含新 DTC 的完整列表。
- 删除某个 DTC：使用 `remove`。
- 覆盖：直接 `set` 新列表。
- 清空：使用 `clear`。

Demo：

```robot
Demo Wwh Obd Current Dtc Settings
    Set Wwh Obd Current Dtc    set    0101    0202
    Set Wwh Obd Current Dtc    set    0101    0202    0103    0102
    Set Wwh Obd Current Dtc    remove    0202
    Set Wwh Obd Current Dtc    clear
    Set Wwh Obd Current Dtc    set    0101    0202    0103    0102
```

逐行解释：

| 步骤 | 当前 DTC 列表 |
| --- | --- |
| `set 0101 0202` | `0101, 0202` |
| `set 0101 0202 0103 0102` | 覆盖为 `0101, 0202, 0103, 0102` |
| `remove 0202` | 删除 `0202`，剩余 `0101, 0103, 0102` |
| `clear` | 清空，剩余 0 个 |
| `set 0101 0202 0103 0102` | 恢复为 4 个 DTC，方便后续测试继续使用 |

## 5. 四条固定值用例

`power_can_basic3.robot` 中以下四条用例都已经加入 DTC 设置：

- `Power Can Basic3 Fixed Values 11bit 500K`
- `Power Can Basic3 Fixed Values 11bit 250K`
- `Power Can Basic3 Fixed Values 29bit 500K`
- `Power Can Basic3 Fixed Values 29bit 250K`

每条用例里的位置都是：

```robot
Configure Can Simulation    11bit/29bit    250000/500000    0
Set Wwh Obd Current Dtc    set    0101    0202    0103    0102
Set Can Signal Range    speed    60    125
Set Can Signal Range    rpm    2000    2010
```

也就是先配置 CAN 位宽、波特率、通道，再设置 DTC 和普通 PID 数据，最后执行 `Start Can Simulation`。

## 6. 代码调用关系

```text
Robot 用例
  -> Set Wwh Obd Current Dtc
    -> HardwareLibrary.set_wwh_obd_current_dtc()
      -> 解析 function 和 DTC 字符串
      -> self.can.set_dtc_list("current", parsed_dtcs)
        -> HeadlessCanSimulator.set_dtc_list()
          -> ObdIsoTpResponder.set_dtc_list()
            -> 设备请求 03 时返回 43 + DTC 列表
```

相关文件：

- `auto_test_reboot/tests/power_can_basic3.robot`
- `auto_test_reboot/resources/power_can_basic3.resource`
- `auto_test_reboot/libraries/HardwareLibrary.py`
- `auto_test_reboot/libraries/can_headless.py`
- `auto_test_reboot/libraries/can_core.py`

## 7. 暂未覆盖范围

当前主要实现和验证的是 WWH-OBD Current DTC。

暂未作为重点验证：

- Pending DTC
- Permanent DTC
- UDS DTC
- J1939 DTC

后续如果需要扩展，建议先抓对应请求和响应，再按当前 Current DTC 的结构继续加关键字。
