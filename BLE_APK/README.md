# BLE AT 调试助手

一个面向 Android / Redmi（MIUI、HyperOS）手机的原生 BLE GATT 调试工具。可以扫描并连接 BLE 外设、选择 GATT 服务及收发特征值、发送 AT 文本并显示通知/指示数据。

## 构建 APK

在本目录执行：

```powershell
gradle assembleDebug
```

生成的调试包位于 `app/build/outputs/apk/debug/app-debug.apk`。首次构建需要 Android SDK Platform 35 和 Android Build Tools 35.0.0。

## 使用

1. 手机打开蓝牙。点击扫描时，应用会申请“附近的设备”和定位权限，并检查系统“位置信息”总开关；从设置页面开启后，返回应用会自动开始扫描。这也覆盖了 Android 12 上仍限制 BLE 扫描的部分 MIUI 13 机型。
2. 首页只显示 BLE 扫描、过滤和设备列表。点击“扫描 BLE”，选择你的 BLE 模块并连接；GATT 连接成功后会自动进入设备工作页，顶部持续显示设备名称、MAC 和连接状态。
   - “设备名称包含”和“MAC 包含”默认留空，即不过滤。
   - 输入名称或 MAC 片段后只显示包含该片段的设备；两项都输入时，设备必须同时满足两项条件。MAC 输入可带或不带冒号/横线。
   - 设备区域最多同时展示 10 台，更多结果在设备区域内上下滑动查看。
   - 点击设备项会立即建立 BLE GATT 连接，不会自动触发系统配对。连接按钮会依次显示“连接中”“已连接”；已连接时点击可断开，断开后再次点击可重新连接当前设备。
   - “连接”按钮旁提供独立“配对”按钮，只有主动点击才发起系统配对；配对完成后按钮变为“取消配对”。若 MIUI 阻止应用删除配对记录，应用会引导打开系统蓝牙设置。
3. 工作页分为“服务”和“AT”两个全屏菜单。“服务”菜单用于选择及开关 GATT 通信服务，“AT”菜单用于命令收发和查看带时间戳的日志。
   - 连接后会自动选择包含 WRITE / WRITE_NO_RESPONSE 的服务，并优先匹配 FFE1 和 Nordic UART。
   - 配置通信 UUID 为服务 `d973f2e0-b19e-11e2-9e96-0800200c9a66`、TX `d973f2e1-b19e-11e2-9e96-0800200c9a66`、RX `d973f2e2-b19e-11e2-9e96-0800200c9a66`；应用会优先自动选择该服务及对应特征值。
   - 服务页不再显示服务/特征值下拉框，只保留三个开关，且默认全部关闭：“配置服务”负责打开/停止私有服务；“TX”单独控制 AT 发送；“RX”单独控制回包接收。
   - App 按文档优先使用 `TX_CHR_UUID (...e1)` 发送、`RX_CHR_UUID (...e2)` 接收；如果实际 GATT Properties 明确显示另一条通道才支持 WRITE 或 NOTIFY/READ，会自动选择具备对应能力的通道。服务页和日志会显示最终实际使用的 UUID。
   - RX 支持 Notify/Indicate 时会订阅主动回包；仅支持 READ 时，会在发送 AT 后延迟执行一次读取。
   - 点击“读取接收特征值”可对支持 GATT READ 的接收特征值进行单次读取。
   - “标准与公开服务”区域会识别 Generic Access、Generic Attribute、Device Information、Battery、Current Time、Environmental Sensing 等 SIG 标准 UUID，并列出设备实际公布的服务、特征值和属性。除基础 GAP/GATT 外，其他公开服务都是设备可选实现，并非每台设备都有。
   - “已连接”表示 GATT 通道已建立；“未配对（BLE 可直连）”表示没有系统加密绑定记录，两者并不冲突，很多 BLE AT 模块无需配对即可使用。
4. 切换到“AT”菜单，输入命令并发送。默认追加 CRLF（`\r\n`），也可以选择 LF 或不追加。AT 与系统收发日志均带 `HH:mm:ss` 时间戳。
   - GATT 服务发现完成后会请求更大的 MTU；日志会显示协商结果。
   - 无论 MTU 是否协商成功，超过 `MTU - 3` 的命令都会自动拆包并等待每包写入完成后再发送下一包。默认 MTU 23 时按 20 字节分包，因此 `AT+ACTIVATION_CONTROL?` 加 CRLF 的 24 字节内容会分为 20+4 两包。
   - 输入框初始值为 `AT+ACTIVATION_CONTROL?`。
   - 收到 `+Activate:ON` 时，激活状态显示为绿色“已激活”。
   - 收到 `+Activate:OFF` 时，激活状态显示为红色“未激活”。
   - 发送 `AT+ACTIVATION_CONTROL=0` 后收到 `OK`，状态也会更新为红色“未激活”。

应用默认识别常见 BLE UART 特征值，但不同模组的服务 UUID、写入/通知特征值可能不同，因此保留了手动选择。若能连接但无回显，请核对模组的 GATT UUID、AT 模式、波特率/透传设置及命令结束符。

## 工程信息

- 原生 Java，无第三方运行库
- minSdk 23（Android 6.0），targetSdk 34
- Android 12 及以上使用附近设备权限；Android 11 及以下使用定位运行时权限
