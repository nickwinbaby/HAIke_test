# 继电器 C 调试版

这个目录是 Python 版工具的原生 Win32 复刻版，目标是做成更小的 Windows exe。

## 文件

- `RelayUsbTest.cpp`：Win32 GUI + Windows HID API 控制逻辑。
- `build_msvc.bat`：MSVC 一键编译脚本。

## 依赖

需要安装 Visual Studio 或 Visual Studio Build Tools，并勾选：

- Desktop development with C++
- Windows 10/11 SDK
- MSVC C++ build tools

不需要第三方 HID 库。程序直接使用 Windows 自带库：

- `hid.lib`
- `setupapi.lib`

## 编译方式一：Developer Command Prompt

1. 打开开始菜单。
2. 搜索并打开 `x64 Native Tools Command Prompt for VS`。
3. 进入本目录：

```bat
cd /d C:\Users\G1006871\Desktop\BIANYI\继电器C调试
```

4. 执行：

```bat
build_msvc.bat
```

成功后会生成：

```text
RelayUsbTest.exe
```

## 编译方式二：Visual Studio 打开文件夹

1. Visual Studio 打开 `继电器C调试` 文件夹。
2. 打开 `Developer PowerShell` 或 `Developer Command Prompt`。
3. 执行：

```bat
build_msvc.bat
```

## 当前逻辑

- 查找设备：枚举 HID 设备，筛选 `VID_16C0` + `PID_05DF`。
- 启动设备：`CreateFileW` 打开 HID 设备路径。
- 发送命令：优先 `HidD_SetFeature`，失败后尝试 `WriteFile`。
- 全部闭合：`FE 00 00 00 00 00 00 00`
- 全部断开：`FC 00 00 00 00 00 00 00`
- 单路闭合：`FF 通道 00 00 00 00 00 00`
- 单路断开：`FD 通道 00 00 00 00 00 00`
- 发送时会补 Report ID：`00`，最终发送 9 字节。

界面通道显示顺序按当前物理连接为：

```text
4
3
2
1
```

## 说明

这个版本是原生 Win32 程序，编译后的 exe 会比 Python 打包小很多。不过实际大小取决于 MSVC 运行库链接方式、优化选项、图标资源等。
