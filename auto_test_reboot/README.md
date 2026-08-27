# auto_test_reboot

Robot Framework 版本的自动化测试示例。底层能力仍然是 Python，Robot 只负责编排用例、步骤结果和报告。

## 快速 dry-run

不操作真实硬件，只验证流程：

```powershell
D:\Python310\python.exe -m robot -d auto_test_reboot\results -v DRY_RUN:True -v TIME_SCALE:0.01 auto_test_reboot\tests
```

## 真实执行

会操作程控电源和 CAN：

```powershell
D:\Python310\python.exe -m robot -d auto_test_reboot\results -v DRY_RUN:False auto_test_reboot\tests
```

## power_can_basic2

`tests\power_can_basic2.robot` 是可配置版本，支持：

- 电源电压、电流、升降压时间和步数配置。
- CAN `11bit/29bit`、`250000/500000` 参数入口。
- OBD PID 值覆盖，例如 `0x0D` 车速、`0x0C` 转速、`0x05` 水温、`0x2F` 油量。
- USB HID 继电器通断控制。

单独运行 basic2：

```powershell
D:\Python310\python.exe -m robot -d auto_test_reboot\results -v DRY_RUN:True -v TIME_SCALE:0.01 auto_test_reboot\tests\power_can_basic2.robot
```

覆盖 CAN 模式：

```powershell
D:\Python310\python.exe -m robot -d auto_test_reboot\results -v DRY_RUN:True -v TIME_SCALE:0.01 -v CAN_ID_FORMAT:29bit -v CAN_BITRATE:250000 auto_test_reboot\tests\power_can_basic2.robot
```

正式跑硬件时把 `DRY_RUN:True` 改成 `DRY_RUN:False`，并把 `TIME_SCALE` 改成 `1.0`。

## 结果

Robot 会生成：

```text
auto_test_reboot\results\report.html
auto_test_reboot\results\log.html
auto_test_reboot\results\output.xml
```
