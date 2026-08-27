# 基本流程测试

这是把原来的自动化逻辑整理成“套件 + 用例”的版本。

## 运行单个用例

```powershell
python .\基本流程测试\run_case.py --dry-run --time-scale 0.01
```

默认单用例是 `json流程测试/case_完整电源CAN流程.json`。

## 运行两个用例的套件

```powershell
python .\基本流程测试\run_suite.py --dry-run --time-scale 0.01
```

默认套件是完整电源 CAN 流程。要跑两条验证用例：

```powershell
python .\基本流程测试\run_suite.py --suite ..\json流程测试\suite_两条用例验证.json
```

## 报告

套件执行后会生成：

- `基本流程测试/reports/<时间戳>/result.json`
- `基本流程测试/reports/<时间戳>/report.html`
