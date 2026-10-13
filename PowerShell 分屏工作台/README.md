# powershell 分屏工作台 V1.3.1 - Mangetic - 2026-9-11

这是一个 C# WinForms 编写的 Windows Terminal 分屏工具，可创建 2–6 个 pane，并为每个 pane 设置独立工作目录。

## 直接使用

双击“启动 PowerShell 分屏工作台.bat”，或直接运行 dist 目录中的 V1.3.1 EXE。启动器精确指向 V1.3.1，不会误启动旧版。

## V1.3.1 主要行为

- 快速模式一次性提交完整布局。
- 标准模式按 750/500 ms 节奏分步创建布局。
- 所有模式都生成唯一 PSSW 窗口目标并新建独立 Windows Terminal 窗口。
- “打开方式”已经删除，避免已有活动 pane、重复点击或并发任务干扰布局。
- 每个 pane 可以设置独立工作目录。
- 支持工作区方案、设置记忆、命令预览和内置 WT 安装器。

## 终端程序与启动后执行命令

终端程序可以填写完整 EXE、包含程序的安装目录、从列表选择，或点击“选择程序”。

- PowerShell：powershell.exe 或 pwsh.exe；命令示例为 dir。
- Python：可填写包含 python.exe 的目录，例如 D:\Python310；命令示例为 print(123)。
- Git Bash：根据 PATH、git.exe 位置和常见 Git 目录自动查找 bin\bash.exe；命令示例为 pwd。
- CMD：cmd.exe；命令示例为 dir。
- WSL：wsl.exe。
- ADB：选择实际 adb.exe；命令示例为 -s DEVICE_SERIAL shell。

普通 GUI 程序不能嵌入 Windows Terminal pane。

## 运行日志

Windows PowerShell 和 PowerShell 7 使用原生 Start-Transcript，日志保存在正式 EXE 同目录的“窗口运行日志”中。日志不再按每次启动创建子目录，而是固定按窗口编号追加到“窗口1.log”至“窗口6.log”。单个文件在启动前达到 500 MiB 后会依次切换为“窗口1-1.log”“窗口1-2.log”等分卷。启动记录持续追加到固定的“启动信息.txt”。分卷限制单个文件大小，但不会自动删除历史分卷。

Python、CMD、Git Bash、WSL、ADB 等非 PowerShell 终端当前不启用日志，以避免改变交互方式、破坏分屏节奏或产生残留进程。选择这些终端时，日志选项会自动禁用并显示当前终端不支持；切回 PowerShell 后恢复原来的日志偏好。

## 进程清理与超时

“清理本工具进程”用于处理旧版本遗留的日志转发器或孤立终端。清理后分别显示真正成功和失败的进程组数量；无法结束的进程不会再被误报为成功。

标准模式的每个 Windows Terminal 步骤最多等待 7 秒。超时后停止后续分屏步骤并提示失败，但不会强制关闭可能已经显示出来的 Terminal 窗口。

## 安装 WT

“安装 WT”会把主 EXE 内置的 Microsoft 签名安装器释放到：

%LOCALAPPDATA%\PowerShellSplitWorkbench\安装程序\Windows Terminal Installer.exe

程序校验 SHA-256 后才询问是否运行。分享工具时只需要发送 V1.3.1 主 EXE。

## 配置文件

- 上次设置：%LOCALAPPDATA%\PowerShellSplitWorkbench\settings.ini
- 工作区方案：%LOCALAPPDATA%\PowerShellSplitWorkbench\profiles

旧配置中的 target 字段会被忽略；V1.3.1 保存配置和方案时不再写入该字段。

## 重新编译

PowerShell 中执行：& ".\source\build_terminal_split.ps1"

CMD 中执行：build.bat

编译前只需关闭同名 V1.3.1 配置窗口；已经打开的 Windows Terminal pane 不需要关闭。

内置自测使用临时模拟的 python.exe 和 bash.exe 文件验证目录解析与命令构造，不依赖开发电脑上的固定 D 盘路径；正式运行时仍检测用户电脑上的真实程序。

## 源码结构

- source\PowerShellSplitWorkbench.cs：界面、布局、配置、启动与自测。
- source\PowerShellSplitWorkbench.PaneLogger.cs：旧日志转发与进程树辅助代码。
- source\build_terminal_split.ps1：正式构建脚本。
- source\PowerShellSplitWorkbench-分布开启.cs：V1.1 历史备份。
- legacy-python：早期 Python 版本，仅供留档。
