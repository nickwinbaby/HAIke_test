# WIFI热点-连接管理器

版本说明：当前源码版本为 `2026.09.19-CLIENT-NETWORK-SAFE-R19`，文档更新于 2026-09-20。

这是一个面向 Windows / Linux 测试场景的 Python 图形工具，主要完成两类工作：

1. 让无线网卡作为 Wi-Fi 热点发射。
2. 让多块无线网卡作为客户端连接同一个外部 Wi-Fi。

程序不会把“命令提交成功”直接当成“热点已经可用”或“Wi-Fi 已经连接”。命令执行结束后还会读取系统状态，并在界面和底部运行日志中显示结果。

## 功能概览

- 自动识别内置或 USB 无线网卡，并在表格中显示网卡、SSID、频段、实际信道、运行状态和独立操作按钮。
- 顶部提供“WIFI热点”和“WIFI连接”两个页面，底部运行日志由两个页面共用。
- 每 10 秒静默刷新热点和客户端 Wi-Fi 状态；后台刷新不会弹窗、不会显示进度条，也不会打断 SSID 或密码输入。
- 用户点击连接、断开、启停网卡或热点时，底部进度条会滚动，并显示“正在执行上一项操作，请稍等”等提示。
- 底部提供“强制终止本程序命令”，只终止本程序登记的外部命令进程，不直接停止 NetworkManager、WLAN AutoConfig 等系统服务。
- 程序带单实例保护，避免多个窗口同时修改网卡或热点状态。
- 软件运行期间会固定已经出现过的网卡序号；刷新后原网卡保持原序号，新插入的网卡追加到后面。
- 正常关闭窗口时会尝试停止本程序管理的热点；如果网卡已经拔出，界面会保留待恢复提示。

## 启动

### Windows

可以双击：

```text
启动热点管理器.bat
```

也可以在 PowerShell 中运行：

```powershell
py .\wifi_hotspot_gui.py
```

Windows 不再在启动入口自动触发 UAC 提权。普通用户权限可以读取网卡、读取部分连接状态、连接外部 Wi-Fi；启用/禁用网卡、旧式 Hosted Network、部分热点共享操作可能需要管理员权限。遇到权限不足时，请重新右键 Python 或启动脚本，选择“以管理员身份运行”。

### Linux

Ubuntu / Debian / Linux Mint：

```bash
sudo apt install python3-tk network-manager iw
python3 wifi_hotspot_gui.py
```

也可以执行：

```bash
chmod +x 启动热点管理器.sh
./启动热点管理器.sh
```

脚本会检查 `python3`、`tkinter`、`nmcli` 和 `iw`。Fedora/RHEL 可安装 `python3-tkinter NetworkManager iw`；Arch Linux 可安装 `tk networkmanager iw`。

Linux 不需要 Windows 那种“位置服务”权限。Linux 的 Wi-Fi 扫描和连接结果主要来自 NetworkManager/nmcli；实际信道、AP 模式和信号读取通常来自 `iw`。如果 `iw` 超时，连接可能仍然已经成功，最终以 NetworkManager 状态和手机/扫描工具为准。

## WIFI热点页面

### SSID 和密码

- 热点名称默认按网卡顺序生成，例如 `AAA1-2.4G`、`AAA2-2.4G`。
- 修改“热点名称前缀（SSID）”后，程序会自动生成“前缀 + 序号 + 频段后缀”。
- SSID 中的 `2.4G` / `5G` 只是名称后缀，不等于已经确认的实际发射频段。
- 热点密码默认是 `12345678`，可以在界面中修改。
- 热点后端默认使用 WPA2-Personal/AES；热点密码通常需要 8～63 个 ASCII 字符。

### 频段和信道

- 可选择 2.4G 或 5G，默认 2.4G。
- 程序不再把某个信道当成硬性启动条件，也不会因为实际信道和界面预览不一致而自动回滚热点。
- 启动热点时，最终信道由操作系统、NetworkManager、Windows、驱动和无线网卡自行协商。
- Linux 5G 为提高手机可见率，会优先请求 36/40/44/48；如果驱动拒绝，会退回完全自动协商。
- 2.4G 以及其他 5G 信道不强制固定。界面能读取到 `iw` 或系统返回的实际信道时会显示；读不到时显示“自动协商/未读取”。
- 程序不主动设置或校验 Linux 国家码，也不绕过内核、驱动或固件的监管限制。即使程序没有设置国家码，驱动仍可能因为自身监管域、DFS、硬件能力或 AP 模式限制而拒绝启动。

### 启动和停止

- 点击网卡表格最后一列，只操作该行对应的热点。
- Windows 的 Hosted Network 和现代移动热点都是系统级单实例，通常同一台 Windows 电脑只能运行一个系统热点。切换到另一行时，程序会提示先停止原热点再切换。
- Linux 使用 NetworkManager 为每块网卡创建独立热点 profile，程序会尽量保留其他网卡热点；最终能否同时运行，取决于每块网卡、驱动、USB 供电以及物理 `wiphy` 是否支持并发 AP。
- 表格显示“运行中”并不等于手机一定能看到 Beacon。最终是否可见，请用手机、Wi-Fi 扫描器或频谱工具确认。
- Linux 发现热点数量减少时，会记录掉线网卡的 NetworkManager 状态、原因代码和接口状态；程序不会把“profile 仍 active”直接当成射频一定正常。

### 共享上网来源

- Windows 优先使用旧 Hosted Network + ICS，失败时尝试现代移动热点接口。
- Linux 使用 NetworkManager `ipv4.method=shared` 提供 DHCP/NAT。
- Linux 的“共享网络”下拉框用于选择可共享的有线接口；程序还会检查当前 IPv4 默认路由，并在日志中说明实际默认出口。
- 共享来源只影响热点的上网出口，不负责解决无线网卡是否支持 AP 模式、是否能同时运行或是否能在指定频段发射。

## WIFI连接页面

这个页面用于让多块无线网卡同时连接同一个外部 Wi-Fi。默认输入为：

```text
SSID：Richlink-Guest-2.4G
密码：richlink_0401
```

两项都可以直接编辑；输入框支持常规复制、粘贴和 `Ctrl+A`。空密码可用于开放网络，具体是否允许由目标热点和系统驱动决定。

### 连接流程

点击“连接外部 WiFi”后，程序会按以下阶段执行：

1. 准备连接并记录选中的网卡。
2. 读取扫描缓存和网卡状态。
3. 逐块提交连接命令，并等待系统响应。
4. 重新读取实际连接状态。

程序会先让所有选中的网卡各尝试一轮；第一轮结束后，只对未连接网卡再重试一轮，不会无限重试。底部日志会明确记录第一轮和第二轮结果。

### Windows 客户端状态

- Windows 优先通过 Win32 WLAN API 读取当前链路真实关联的 SSID，不用 WLAN Profile 名称冒充 SSID。
- 如果 Windows 的位置服务或系统策略阻止 WLAN API/netsh 读取详细 WLAN 信息，程序可能只能确认“接口存在活动网络”和 IP，不能确认它是否连接到目标 SSID。
- 此时界面会显示“已连接，但真实 SSID 受权限限制，未核对”，不会把网络配置名称当成 SSID。
- 要读取更多扫描、信号和真实 SSID 信息，可在 Windows 打开：设置 → 隐私和安全性 → 位置 → 位置服务。
- Windows 的位置权限只影响 WLAN 详细信息读取，不等于 Wi-Fi 连接本身一定失败。
- 如果网卡显示 `Hardware On / Software Off`、`0x80342002` 或无线射频关闭，请先打开 Windows Wi-Fi、关闭飞行模式并确认网卡射频开关已开启。程序可以等待网卡恢复，但不能绕过硬件开关、飞行模式、驱动或系统无线服务的限制。

### Linux 客户端状态

- Linux 使用 NetworkManager/nmcli 连接，并等待 `connected/activated` 状态，而不是只看命令退出码。
- 扫描缓存暂时看不到目标 SSID 时，程序不会把它当成硬门槛；仍会把连接请求交给 NetworkManager。
- 连接前只清理明确属于目标网卡的本程序 profile，避免误删有线接口或其他无线网卡的连接。
- 如果目标网卡之前处于 AP 模式或残留热点 profile，程序只清理该网卡的残留状态。
- 连接目标网卡前会记录其他无线网卡的活动连接；如果驱动或 NetworkManager 意外连带断开其他接口，程序只尝试恢复受影响的原接口，不操作 `ens33`、`docker0` 等有线接口。
- Linux 的 IP、信号和状态通常比 Windows 完整；如果 `iw dev` 暂时超时，顶部周期性状态可能缺少信号或 SSID，但底部连接日志和 NetworkManager 状态仍可能显示连接成功。

## 常见状态含义

- `尚未连接（尚未发起连接）`：程序刚启动或刚刷新，只是在展示当前状态，不代表一次连接操作失败。
- `连接请求已提交，等待系统确认`：命令已交给系统，程序尚未确认最终 SSID/连接状态；后台 10 秒刷新会继续核对。
- `已连接目标热点`：已经读取到真实 SSID，且与目标 SSID 一致。
- `已连接（真实 SSID 受权限限制，未核对）`：系统确认接口有活动连接，但 Windows 不允许读取真实 SSID；不能据此确认目标热点匹配。
- `已连接其他热点`：读取到真实 SSID，但与目标 SSID 不一致。
- `未连接，扫描信息受 Windows 位置权限限制`：Windows 详细扫描被位置权限或系统策略阻止，不能据此判断目标热点不存在。
- `0x80342002`：通常表示无线射频处于软件关闭、网卡刚启用但驱动尚未恢复，或 WLAN 服务尚未准备好。
- `802.1X supplicant`：NetworkManager 的通用连接激活/认证超时文案，不自动等于企业 802.1X 配置；热点和普通 Wi-Fi 是否使用 WPA2-Personal 仍由具体 profile 决定。

## Windows 与 Linux 的重要差异

| 项目 | Windows | Linux |
| --- | --- | --- |
| 热点数量 | 通常只能运行一个系统热点 | 可尝试多块网卡独立热点 |
| 热点后端 | Hosted Network / 现代移动热点 | NetworkManager shared/AP profile |
| 真实 SSID 读取 | 可能受位置权限和 WLAN API 限制 | 通常由 NetworkManager/iw 读取 |
| 信号/IP 展示 | 权限不足时可能只有 IP 或无信号 | 通常可显示 IP、信号和激活状态 |
| 连接重试 | 全部网卡第一轮后，对失败网卡重试一轮 | 同样只重试一轮 |
| 多网卡并发 | 系统热点通常不支持多个独立 SSID | 受驱动、物理射频、USB 和 NetworkManager 限制 |

## 运行日志和强制终止

热点和 Wi-Fi 连接两个页面共用底部“运行日志”。日志会记录：

- 当前程序版本和刷新时间。
- 每块网卡的启动、停止、连接、断开和重试过程。
- Windows WLAN API、位置权限、无线射频和权限错误。
- Linux NetworkManager、接口状态、AP 模式、实际信道和掉线原因。

操作仍在执行时，底部进度条会滚动。此时重复点击按钮不会并发执行同一类网络操作；如确认需要停止当前命令，可点击“强制终止本程序命令”。终止后请等待网卡和 NetworkManager 回到稳定状态，再重新刷新或发起下一次操作。

## Windows 编译 EXE

请在 Windows 上编译 Windows EXE，不能把 Linux ELF 文件直接复制后当作 Windows 程序运行：

```powershell
py -m pip install pyinstaller
py -m PyInstaller --noconsole --onefile --name WIFI热点-连接管理器-R19 wifi_hotspot_gui.py
```

生成文件位于当前项目的 `dist` 目录。当前版本不使用 `--uac-admin` 自动提权；需要管理员权限的具体操作会在运行时给出提示。

Linux 请在 Linux 上单独运行源码或单独打包 Linux 可执行文件。Linux ELF 与 Windows PE/EXE 是不同格式，不能跨平台直接运行。

## 状态文件

- Windows：`%LOCALAPPDATA%\GMYHotspotManager`
- Linux：`~/.local/state/gmy_hotspot_manager`，可由 `XDG_STATE_HOME` 覆盖

程序会保存热点运行状态、待恢复网卡设置和客户端相关运行信息。旧版本状态文件会在成功写入新位置后兼容迁移；如果旧 USB 网卡已经拔出，重新插回后可在界面点击“重试残留恢复”。

## 排查建议

### 热点启动后手机搜不到

1. 先确认表格对应行是否为“运行中”，而不是只看“启动命令成功”。
2. 用 `iw dev <接口> info` 查看 Linux 接口是否仍为 `type AP` 以及实际信道。
3. 检查两块 USB 网卡是否属于同一个物理 `wiphy`，以及 USB 供电是否稳定。
4. 在 Windows 用手机或 Wi-Fi 扫描工具确认 SSID 和实际频段，不要只根据 SSID 后缀判断 2.4G/5G。

### Wi-Fi 连接失败但手动连接成功

1. 确认目标 SSID 正在广播、密码正确、网卡频段兼容。
2. Linux 先断开该网卡残留的 AP/旧 Wi-Fi profile，再点击连接；程序只会清理明确属于目标接口的 profile。
3. Windows 检查 Wi-Fi、飞行模式和无线射频状态；如果是 `Software Off` 或 `0x80342002`，先让系统无线恢复。
4. 查看底部日志是否已经完成第二轮重试；不要把“连接请求已提交”当成最终成功。
5. Windows 若只显示“真实 SSID 未核对”，打开位置服务后再刷新状态。

### Linux 连接一块网卡后另一块也掉线

程序会尽量记录并恢复受影响的其他无线连接，但驱动或 NetworkManager 仍可能在同一物理射频、AP/客户端模式切换或 USB 复位时连带影响接口。重点查看日志中的：

```bash
journalctl -u NetworkManager --since "10 minutes ago"
dmesg --ctime | tail -n 100
```

如果出现 USB disconnect、firmware crash、reset 或 autosuspend，优先更换 USB 口/有源 HUB、检查驱动固件和 USB 自动休眠设置。

