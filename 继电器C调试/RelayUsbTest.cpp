#include <windows.h>
#include <commctrl.h>
#include <setupapi.h>
#include <hidsdi.h>

#include <algorithm>
#include <cwchar>
#include <ctime>
#include <random>
#include <sstream>
#include <string>
#include <vector>

#pragma comment(lib, "setupapi.lib")
#pragma comment(lib, "hid.lib")
#pragma comment(lib, "comctl32.lib")
#pragma comment(linker, \
    "\"/manifestdependency:type='win32' name='Microsoft.Windows.Common-Controls' version='6.0.0.0' " \
    "processorArchitecture='*' publicKeyToken='6595b64144ccf1df' language='*'\"")

static const USHORT RELAY_VID = 0x16C0;
static const USHORT RELAY_PID = 0x05DF;
static const int CHANNEL_COUNT = 4;
static const int CHANNEL_DISPLAY_ORDER[CHANNEL_COUNT] = {4, 3, 2, 1};

static const UINT WM_APP_LOG = WM_APP + 1;
static const UINT WM_APP_CHANNEL_STATUS = WM_APP + 2;
static const UINT WM_APP_LOOP_STOPPED = WM_APP + 3;

enum ControlId {
    IDC_FIND_DEVICE = 1001,
    IDC_OPEN_DEVICE = 1002,
    IDC_RELEASE_DEVICE = 1003,
    IDC_ALL_CLOSE = 1004,
    IDC_ALL_OPEN = 1005,
    IDC_LOOP_START = 1006,
    IDC_MIN_CLOSE = 1007,
    IDC_MAX_CLOSE = 1008,
    IDC_OPEN_WAIT = 1009,
    IDC_LOG = 1010,
    IDC_CHANNEL_CLOSE_BASE = 1100,
    IDC_CHANNEL_OPEN_BASE = 1200,
    IDC_CHANNEL_LOOP_BASE = 1300
};

static HINSTANCE g_instance = nullptr;
static HWND g_main = nullptr;
static HFONT g_font = nullptr;
static HFONT g_font_bold = nullptr;
static HBRUSH g_bg_brush = nullptr;
static HBRUSH g_log_brush = nullptr;
static HBRUSH g_status_idle_brush = nullptr;
static HBRUSH g_status_ok_brush = nullptr;
static HBRUSH g_status_open_brush = nullptr;
static HBRUSH g_status_closed_brush = nullptr;
static HANDLE g_device = INVALID_HANDLE_VALUE;
static std::wstring g_device_path;
static bool g_connected = false;
static bool g_loop_running = false;
static HANDLE g_loop_thread = nullptr;

static HWND g_status_device = nullptr;
static HWND g_status_count = nullptr;
static HWND g_log = nullptr;
static HWND g_loop_button = nullptr;
static HWND g_min_close_edit = nullptr;
static HWND g_max_close_edit = nullptr;
static HWND g_open_wait_edit = nullptr;
static HWND g_channel_status[CHANNEL_COUNT + 1] = {};
static HWND g_channel_loop_button[CHANNEL_COUNT + 1] = {};
static bool g_channel_closed[CHANNEL_COUNT + 1] = {};
static bool g_channel_loop_enabled[CHANNEL_COUNT + 1] = {false, true, true, true, true};
static std::vector<HWND> g_action_controls;

static std::wstring Format(const wchar_t* text) {
    return std::wstring(text);
}

template <typename T>
static std::wstring Format(const wchar_t* prefix, T value, const wchar_t* suffix = L"") {
    std::wstringstream ss;
    ss << prefix << value << suffix;
    return ss.str();
}

static void AppendLog(const std::wstring& text) {
    if (!g_log) {
        return;
    }

    wchar_t stamp[32] = {};
    std::time_t now = std::time(nullptr);
    std::tm local_time = {};
    localtime_s(&local_time, &now);
    wcsftime(stamp, 32, L"%H:%M:%S", &local_time);

    std::wstring line = L"[";
    line += stamp;
    line += L"] ";
    line += text;
    line += L"\r\n";

    int length = GetWindowTextLengthW(g_log);
    SendMessageW(g_log, EM_SETSEL, length, length);
    SendMessageW(g_log, EM_REPLACESEL, FALSE, reinterpret_cast<LPARAM>(line.c_str()));
}

static void PostLog(const std::wstring& text) {
    PostMessageW(g_main, WM_APP_LOG, 0, reinterpret_cast<LPARAM>(new std::wstring(text)));
}

static HWND MakeControl(
    const wchar_t* cls,
    const wchar_t* text,
    DWORD style,
    int x,
    int y,
    int w,
    int h,
    HWND parent,
    HMENU id,
    DWORD ex_style = 0
) {
    HWND hwnd = CreateWindowExW(
        ex_style,
        cls,
        text,
        WS_CHILD | WS_VISIBLE | style,
        x,
        y,
        w,
        h,
        parent,
        id,
        g_instance,
        nullptr
    );
    if (g_font) {
        SendMessageW(hwnd, WM_SETFONT, reinterpret_cast<WPARAM>(g_font), TRUE);
    }
    return hwnd;
}

static HWND MakeStatic(const wchar_t* text, int x, int y, int w, int h, HWND parent, DWORD style = 0) {
    return MakeControl(L"STATIC", text, SS_LEFT | SS_CENTERIMAGE | style, x, y, w, h, parent, nullptr);
}

static HWND MakeStatus(const wchar_t* text, int x, int y, int w, int h, HWND parent) {
    return MakeStatic(text, x, y, w, h, parent, SS_CENTER | WS_BORDER);
}

static HWND MakeGroupBox(const wchar_t* text, int x, int y, int w, int h, HWND parent) {
    HWND hwnd = MakeControl(L"BUTTON", text, BS_GROUPBOX, x, y, w, h, parent, nullptr);
    if (g_font_bold) {
        SendMessageW(hwnd, WM_SETFONT, reinterpret_cast<WPARAM>(g_font_bold), TRUE);
    }
    return hwnd;
}

static HWND MakeButton(const wchar_t* text, int x, int y, int w, int h, HWND parent, int id) {
    return MakeControl(L"BUTTON", text, BS_PUSHBUTTON, x, y, w, h, parent, reinterpret_cast<HMENU>(id));
}

static HWND MakeEdit(const wchar_t* text, int x, int y, int w, int h, HWND parent, int id) {
    return MakeControl(
        L"EDIT",
        text,
        WS_BORDER | ES_AUTOHSCROLL,
        x,
        y,
        w,
        h,
        parent,
        reinterpret_cast<HMENU>(id),
        WS_EX_CLIENTEDGE
    );
}

static std::wstring LowerPath(const std::wstring& path) {
    std::wstring lower = path;
    std::transform(lower.begin(), lower.end(), lower.begin(), [](wchar_t ch) {
        return static_cast<wchar_t>(towlower(ch));
    });
    return lower;
}

static bool IsRelayPath(const std::wstring& path) {
    std::wstring lower = LowerPath(path);
    return lower.find(L"vid_16c0") != std::wstring::npos &&
           lower.find(L"pid_05df") != std::wstring::npos;
}

static int FindRelayDevices(std::wstring* first_path) {
    GUID hid_guid = {};
    HidD_GetHidGuid(&hid_guid);

    HDEVINFO dev_info = SetupDiGetClassDevsW(
        &hid_guid,
        nullptr,
        nullptr,
        DIGCF_PRESENT | DIGCF_DEVICEINTERFACE
    );
    if (dev_info == INVALID_HANDLE_VALUE) {
        return 0;
    }

    int count = 0;
    SP_DEVICE_INTERFACE_DATA interface_data = {};
    interface_data.cbSize = sizeof(interface_data);

    for (DWORD index = 0; SetupDiEnumDeviceInterfaces(dev_info, nullptr, &hid_guid, index, &interface_data); ++index) {
        DWORD required_size = 0;
        SetupDiGetDeviceInterfaceDetailW(dev_info, &interface_data, nullptr, 0, &required_size, nullptr);
        if (required_size == 0) {
            continue;
        }

        std::vector<BYTE> detail_buffer(required_size);
        auto* detail = reinterpret_cast<SP_DEVICE_INTERFACE_DETAIL_DATA_W*>(detail_buffer.data());
        detail->cbSize = sizeof(SP_DEVICE_INTERFACE_DETAIL_DATA_W);

        if (!SetupDiGetDeviceInterfaceDetailW(dev_info, &interface_data, detail, required_size, nullptr, nullptr)) {
            continue;
        }

        std::wstring path = detail->DevicePath;
        if (!IsRelayPath(path)) {
            continue;
        }

        ++count;
        if (first_path && first_path->empty()) {
            *first_path = path;
        }
        PostLog(L"NUM=HW341,PATH=" + path);
    }

    SetupDiDestroyDeviceInfoList(dev_info);
    return count;
}

static void EnableActionControls(bool enabled) {
    for (HWND hwnd : g_action_controls) {
        EnableWindow(hwnd, enabled ? TRUE : FALSE);
    }
}

static void UpdateDeviceStatus(const wchar_t* text, bool connected) {
    SetWindowTextW(g_status_device, text);
    g_connected = connected;
    EnableActionControls(connected);
}

static void UpdateChannelStatus(int channel, bool closed) {
    if (channel < 1 || channel > CHANNEL_COUNT) {
        return;
    }
    g_channel_closed[channel] = closed;
    SetWindowTextW(g_channel_status[channel], closed ? L"闭合" : L"断开");
}

static void UpdateAllChannelStatus(bool closed) {
    for (int channel = 1; channel <= CHANNEL_COUNT; ++channel) {
        UpdateChannelStatus(channel, closed);
    }
}

static bool OpenRelayDevice() {
    if (g_device != INVALID_HANDLE_VALUE) {
        AppendLog(L"设备 [HW341] 已启动。");
        return true;
    }

    if (g_device_path.empty()) {
        std::wstring first_path;
        int count = FindRelayDevices(&first_path);
        SetWindowTextW(g_status_count, Format(L"设备数量：", count).c_str());
        if (first_path.empty()) {
            AppendLog(L"启动设备失败：未找到继电器设备。");
            return false;
        }
        g_device_path = first_path;
    }

    g_device = CreateFileW(
        g_device_path.c_str(),
        GENERIC_READ | GENERIC_WRITE,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        nullptr,
        OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL,
        nullptr
    );

    if (g_device == INVALID_HANDLE_VALUE) {
        AppendLog(Format(L"设备 [HW341] 打开失败，错误码：", GetLastError()));
        UpdateDeviceStatus(L"连接失败", false);
        return false;
    }

    UpdateDeviceStatus(L"已连接", true);
    AppendLog(L"设备 [HW341] 打开成功。");
    return true;
}

static void ReleaseRelayDevice() {
    g_loop_running = false;
    SetWindowTextW(g_loop_button, L"启动循环");

    if (g_device != INVALID_HANDLE_VALUE) {
        CloseHandle(g_device);
        g_device = INVALID_HANDLE_VALUE;
    }

    UpdateDeviceStatus(L"未连接", false);
    AppendLog(L"设备已释放。");
}

static bool SendRelayCommand(BYTE cmd, BYTE channel) {
    if (g_device == INVALID_HANDLE_VALUE) {
        AppendLog(L"设备未连接，请先点击“启动设备”。");
        return false;
    }

    BYTE report[9] = {};
    report[0] = 0x00;
    report[1] = cmd;
    report[2] = channel;

    if (HidD_SetFeature(g_device, report, sizeof(report))) {
        return true;
    }

    DWORD written = 0;
    if (WriteFile(g_device, report, sizeof(report), &written, nullptr)) {
        return true;
    }

    AppendLog(Format(L"发送命令失败，错误码：", GetLastError()));
    ReleaseRelayDevice();
    return false;
}

static bool SetChannel(int channel, bool closed) {
    BYTE cmd = closed ? 0xFF : 0xFD;
    if (!SendRelayCommand(cmd, static_cast<BYTE>(channel))) {
        return false;
    }

    UpdateChannelStatus(channel, closed);
    AppendLog(Format(L"第", channel, closed ? L"路继电器闭合成功。" : L"路继电器断开成功。"));
    return true;
}

static bool SetAll(bool closed) {
    BYTE cmd = closed ? 0xFE : 0xFC;
    if (!SendRelayCommand(cmd, 0)) {
        return false;
    }

    UpdateAllChannelStatus(closed);
    AppendLog(closed ? L"全部继电器闭合成功。" : L"全部继电器断开成功。");
    return true;
}

static double ReadDouble(HWND edit, double fallback) {
    wchar_t text[64] = {};
    GetWindowTextW(edit, text, 64);
    wchar_t* end = nullptr;
    double value = wcstod(text, &end);
    return end == text ? fallback : value;
}

static bool SleepInterruptible(double seconds) {
    DWORD total_ms = static_cast<DWORD>(seconds * 1000.0);
    DWORD elapsed = 0;
    while (g_loop_running && elapsed < total_ms) {
        DWORD remaining = total_ms - elapsed;
        DWORD step = remaining < 200 ? remaining : 200;
        Sleep(step);
        elapsed += step;
    }
    return g_loop_running;
}

static bool ThreadSetChannels(const std::vector<int>& channels, bool closed) {
    if (channels.size() == CHANNEL_COUNT) {
        bool ok = SendRelayCommand(closed ? 0xFE : 0xFC, 0);
        if (!ok) {
            return false;
        }
        for (int channel : channels) {
            PostMessageW(g_main, WM_APP_CHANNEL_STATUS, static_cast<WPARAM>(channel), static_cast<LPARAM>(closed));
        }
        return true;
    }

    for (int channel : channels) {
        bool ok = SendRelayCommand(closed ? 0xFF : 0xFD, static_cast<BYTE>(channel));
        if (!ok) {
            return false;
        }
        PostMessageW(g_main, WM_APP_CHANNEL_STATUS, static_cast<WPARAM>(channel), static_cast<LPARAM>(closed));
        Sleep(50);
    }
    return true;
}

static DWORD WINAPI LoopThreadProc(LPVOID param) {
    delete reinterpret_cast<int*>(param);

    double min_close = ReadDouble(g_min_close_edit, 10.0);
    double max_close = ReadDouble(g_max_close_edit, 20.0);
    double open_wait = ReadDouble(g_open_wait_edit, 5.0);
    if (min_close > max_close) {
        std::swap(min_close, max_close);
    }

    std::vector<int> channels;
    for (int channel = 1; channel <= CHANNEL_COUNT; ++channel) {
        if (g_channel_loop_enabled[channel]) {
            channels.push_back(channel);
        }
    }

    if (channels.empty()) {
        PostLog(L"请至少选择一路参与循环。");
        PostMessageW(g_main, WM_APP_LOOP_STOPPED, 0, 0);
        return 0;
    }

    std::random_device rd;
    std::mt19937 gen(rd());
    std::uniform_real_distribution<double> dist(min_close, max_close);

    while (g_loop_running) {
        double close_seconds = dist(gen);

        if (!ThreadSetChannels(channels, true)) {
            break;
        }
        PostLog(Format(L"循环：继电器闭合，持续 ", close_seconds, L" 秒。"));
        if (!SleepInterruptible(close_seconds)) {
            break;
        }

        if (!ThreadSetChannels(channels, false)) {
            break;
        }
        PostLog(Format(L"循环：继电器断开，持续 ", open_wait, L" 秒。"));
        if (!SleepInterruptible(open_wait)) {
            break;
        }
    }

    PostMessageW(g_main, WM_APP_LOOP_STOPPED, 0, 0);
    return 0;
}

static void StartOrStopLoop() {
    if (g_loop_running) {
        g_loop_running = false;
        SetWindowTextW(g_loop_button, L"启动循环");
        AppendLog(L"随机循环测试停止。");
        return;
    }

    if (!g_connected || g_device == INVALID_HANDLE_VALUE) {
        AppendLog(L"设备未连接，请先点击“启动设备”。");
        return;
    }

    g_loop_running = true;
    SetWindowTextW(g_loop_button, L"停止循环");
    g_loop_thread = CreateThread(nullptr, 0, LoopThreadProc, new int(0), 0, nullptr);
    AppendLog(L"随机循环测试启动。");
}

static void ToggleLoopChannel(int channel) {
    if (channel < 1 || channel > CHANNEL_COUNT) {
        return;
    }

    g_channel_loop_enabled[channel] = !g_channel_loop_enabled[channel];
    SetWindowTextW(g_channel_loop_button[channel], g_channel_loop_enabled[channel] ? L"●" : L"○");
}

static bool IsChannelStatusControl(HWND hwnd, int* out_channel) {
    for (int channel = 1; channel <= CHANNEL_COUNT; ++channel) {
        if (g_channel_status[channel] == hwnd) {
            if (out_channel) {
                *out_channel = channel;
            }
            return true;
        }
    }
    return false;
}

static void BuildUi(HWND hwnd) {
    g_bg_brush = CreateSolidBrush(RGB(244, 246, 248));
    g_log_brush = CreateSolidBrush(RGB(255, 255, 255));
    g_status_idle_brush = CreateSolidBrush(RGB(226, 232, 240));
    g_status_ok_brush = CreateSolidBrush(RGB(203, 244, 216));
    g_status_open_brush = CreateSolidBrush(RGB(219, 234, 254));
    g_status_closed_brush = CreateSolidBrush(RGB(220, 252, 231));

    g_font = CreateFontW(
        -14,
        0,
        0,
        0,
        FW_NORMAL,
        FALSE,
        FALSE,
        FALSE,
        DEFAULT_CHARSET,
        OUT_DEFAULT_PRECIS,
        CLIP_DEFAULT_PRECIS,
        DEFAULT_QUALITY,
        DEFAULT_PITCH | FF_DONTCARE,
        L"Microsoft YaHei UI"
    );

    g_font_bold = CreateFontW(
        -14,
        0,
        0,
        0,
        FW_BOLD,
        FALSE,
        FALSE,
        FALSE,
        DEFAULT_CHARSET,
        OUT_DEFAULT_PRECIS,
        CLIP_DEFAULT_PRECIS,
        DEFAULT_QUALITY,
        DEFAULT_PITCH | FF_DONTCARE,
        L"Microsoft YaHei UI"
    );

    MakeGroupBox(L"设备", 14, 12, 812, 86, hwnd);
    MakeButton(L"查找设备", 36, 46, 96, 32, hwnd, IDC_FIND_DEVICE);
    MakeButton(L"启动设备", 146, 46, 96, 32, hwnd, IDC_OPEN_DEVICE);
    MakeButton(L"释放设备", 256, 46, 96, 32, hwnd, IDC_RELEASE_DEVICE);
    MakeStatic(L"状态", 392, 50, 44, 24, hwnd);
    g_status_device = MakeStatus(L"未连接", 438, 48, 112, 28, hwnd);
    g_status_count = MakeStatic(L"设备数量：0", 590, 50, 180, 24, hwnd);

    MakeGroupBox(L"四路继电器独立控制", 14, 110, 520, 226, hwnd);
    MakeStatic(L"通道", 44, 142, 60, 24, hwnd, SS_CENTER);
    MakeStatic(L"当前状态", 120, 142, 88, 24, hwnd, SS_CENTER);
    MakeStatic(L"单独控制", 242, 142, 120, 24, hwnd, SS_CENTER);
    MakeStatic(L"参与循环", 408, 142, 90, 24, hwnd, SS_CENTER);

    for (int row = 0; row < CHANNEL_COUNT; ++row) {
        int channel = CHANNEL_DISPLAY_ORDER[row];
        int y = 176 + row * 38;

        wchar_t channel_text[8] = {};
        swprintf_s(channel_text, L"%d", channel);
        MakeStatic(channel_text, 58, y + 4, 36, 24, hwnd, SS_CENTER);
        g_channel_status[channel] = MakeStatus(L"断开", 126, y, 74, 28, hwnd);

        HWND close_button = MakeButton(L"闭合", 236, y, 78, 30, hwnd, IDC_CHANNEL_CLOSE_BASE + channel);
        HWND open_button = MakeButton(L"断开", 326, y, 78, 30, hwnd, IDC_CHANNEL_OPEN_BASE + channel);
        g_action_controls.push_back(close_button);
        g_action_controls.push_back(open_button);

        g_channel_loop_button[channel] = MakeButton(L"●", 432, y, 42, 30, hwnd, IDC_CHANNEL_LOOP_BASE + channel);
    }

    MakeGroupBox(L"全部控制", 548, 110, 278, 102, hwnd);
    HWND all_close = MakeButton(L"全部闭合", 576, 152, 108, 34, hwnd, IDC_ALL_CLOSE);
    HWND all_open = MakeButton(L"全部断开", 696, 152, 108, 34, hwnd, IDC_ALL_OPEN);
    g_action_controls.push_back(all_close);
    g_action_controls.push_back(all_open);

    MakeGroupBox(L"随机循环测试", 548, 228, 278, 108, hwnd);
    MakeStatic(L"闭合最小", 572, 260, 68, 24, hwnd);
    g_min_close_edit = MakeEdit(L"10", 644, 258, 56, 26, hwnd, IDC_MIN_CLOSE);
    MakeStatic(L"s", 706, 260, 20, 24, hwnd);
    MakeStatic(L"闭合最大", 572, 294, 68, 24, hwnd);
    g_max_close_edit = MakeEdit(L"20", 644, 292, 56, 26, hwnd, IDC_MAX_CLOSE);
    MakeStatic(L"s", 706, 294, 20, 24, hwnd);
    MakeStatic(L"断开时间", 724, 260, 68, 24, hwnd);
    g_open_wait_edit = MakeEdit(L"5", 788, 258, 34, 26, hwnd, IDC_OPEN_WAIT);
    MakeStatic(L"s", 824, 260, 16, 24, hwnd);
    g_loop_button = MakeButton(L"启动循环", 724, 292, 98, 30, hwnd, IDC_LOOP_START);
    g_action_controls.push_back(g_loop_button);

    MakeGroupBox(L"STATE", 14, 350, 812, 174, hwnd);
    g_log = CreateWindowExW(
        WS_EX_CLIENTEDGE,
        L"EDIT",
        L"",
        WS_CHILD | WS_VISIBLE | ES_MULTILINE | ES_AUTOVSCROLL | WS_VSCROLL | ES_READONLY,
        32,
        378,
        776,
        126,
        hwnd,
        reinterpret_cast<HMENU>(IDC_LOG),
        g_instance,
        nullptr
    );
    SendMessageW(g_log, WM_SETFONT, reinterpret_cast<WPARAM>(g_font), TRUE);

    EnableActionControls(false);
    AppendLog(L"程序已启动，点击“查找设备”扫描 USB HID 继电器。");
}

static void OnFindDevice() {
    g_device_path.clear();
    std::wstring first_path;
    int count = FindRelayDevices(&first_path);
    g_device_path = first_path;

    SetWindowTextW(g_status_count, Format(L"设备数量：", count).c_str());
    AppendLog(Format(L"共找到", count, L"个设备。"));
}

static LRESULT CALLBACK WindowProc(HWND hwnd, UINT msg, WPARAM wparam, LPARAM lparam) {
    switch (msg) {
    case WM_CREATE:
        BuildUi(hwnd);
        return 0;

    case WM_COMMAND: {
        int id = LOWORD(wparam);
        if (id == IDC_FIND_DEVICE) {
            OnFindDevice();
        } else if (id == IDC_OPEN_DEVICE) {
            OpenRelayDevice();
        } else if (id == IDC_RELEASE_DEVICE) {
            ReleaseRelayDevice();
        } else if (id == IDC_ALL_CLOSE) {
            SetAll(true);
        } else if (id == IDC_ALL_OPEN) {
            SetAll(false);
        } else if (id == IDC_LOOP_START) {
            StartOrStopLoop();
        } else if (id >= IDC_CHANNEL_CLOSE_BASE + 1 && id <= IDC_CHANNEL_CLOSE_BASE + CHANNEL_COUNT) {
            SetChannel(id - IDC_CHANNEL_CLOSE_BASE, true);
        } else if (id >= IDC_CHANNEL_OPEN_BASE + 1 && id <= IDC_CHANNEL_OPEN_BASE + CHANNEL_COUNT) {
            SetChannel(id - IDC_CHANNEL_OPEN_BASE, false);
        } else if (id >= IDC_CHANNEL_LOOP_BASE + 1 && id <= IDC_CHANNEL_LOOP_BASE + CHANNEL_COUNT) {
            ToggleLoopChannel(id - IDC_CHANNEL_LOOP_BASE);
        }
        return 0;
    }

    case WM_ERASEBKGND: {
        RECT rect = {};
        GetClientRect(hwnd, &rect);
        FillRect(reinterpret_cast<HDC>(wparam), &rect, g_bg_brush);
        return 1;
    }

    case WM_CTLCOLORSTATIC: {
        HDC hdc = reinterpret_cast<HDC>(wparam);
        HWND ctrl = reinterpret_cast<HWND>(lparam);
        SetBkMode(hdc, OPAQUE);

        if (ctrl == g_status_device) {
            SetTextColor(hdc, g_connected ? RGB(20, 83, 45) : RGB(51, 65, 85));
            SetBkColor(hdc, g_connected ? RGB(203, 244, 216) : RGB(226, 232, 240));
            return reinterpret_cast<LRESULT>(g_connected ? g_status_ok_brush : g_status_idle_brush);
        }

        int channel = 0;
        if (IsChannelStatusControl(ctrl, &channel)) {
            bool closed = g_channel_closed[channel];
            SetTextColor(hdc, closed ? RGB(20, 83, 45) : RGB(30, 64, 175));
            SetBkColor(hdc, closed ? RGB(220, 252, 231) : RGB(219, 234, 254));
            return reinterpret_cast<LRESULT>(closed ? g_status_closed_brush : g_status_open_brush);
        }

        if (ctrl == g_log) {
            SetTextColor(hdc, RGB(17, 24, 39));
            SetBkColor(hdc, RGB(255, 255, 255));
            return reinterpret_cast<LRESULT>(g_log_brush);
        }

        SetBkMode(hdc, TRANSPARENT);
        SetTextColor(hdc, RGB(31, 41, 55));
        return reinterpret_cast<LRESULT>(g_bg_brush);
    }

    case WM_CTLCOLOREDIT: {
        HDC hdc = reinterpret_cast<HDC>(wparam);
        SetTextColor(hdc, RGB(17, 24, 39));
        SetBkColor(hdc, RGB(255, 255, 255));
        return reinterpret_cast<LRESULT>(g_log_brush);
    }

    case WM_APP_LOG: {
        auto* text = reinterpret_cast<std::wstring*>(lparam);
        if (text) {
            AppendLog(*text);
            delete text;
        }
        return 0;
    }

    case WM_APP_CHANNEL_STATUS:
        UpdateChannelStatus(static_cast<int>(wparam), lparam != 0);
        return 0;

    case WM_APP_LOOP_STOPPED:
        g_loop_running = false;
        SetWindowTextW(g_loop_button, L"启动循环");
        return 0;

    case WM_DESTROY:
        g_loop_running = false;
        if (g_device != INVALID_HANDLE_VALUE) {
            CloseHandle(g_device);
            g_device = INVALID_HANDLE_VALUE;
        }
        if (g_font) {
            DeleteObject(g_font);
            g_font = nullptr;
        }
        if (g_font_bold) {
            DeleteObject(g_font_bold);
            g_font_bold = nullptr;
        }
        if (g_bg_brush) {
            DeleteObject(g_bg_brush);
            g_bg_brush = nullptr;
        }
        if (g_log_brush) {
            DeleteObject(g_log_brush);
            g_log_brush = nullptr;
        }
        if (g_status_idle_brush) {
            DeleteObject(g_status_idle_brush);
            g_status_idle_brush = nullptr;
        }
        if (g_status_ok_brush) {
            DeleteObject(g_status_ok_brush);
            g_status_ok_brush = nullptr;
        }
        if (g_status_open_brush) {
            DeleteObject(g_status_open_brush);
            g_status_open_brush = nullptr;
        }
        if (g_status_closed_brush) {
            DeleteObject(g_status_closed_brush);
            g_status_closed_brush = nullptr;
        }
        PostQuitMessage(0);
        return 0;

    default:
        return DefWindowProcW(hwnd, msg, wparam, lparam);
    }
}

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE, PWSTR, int show_cmd) {
    g_instance = instance;

    INITCOMMONCONTROLSEX icc = {};
    icc.dwSize = sizeof(icc);
    icc.dwICC = ICC_STANDARD_CLASSES;
    InitCommonControlsEx(&icc);

    WNDCLASSW wc = {};
    wc.lpfnWndProc = WindowProc;
    wc.hInstance = instance;
    wc.hCursor = LoadCursorW(nullptr, IDC_ARROW);
    wc.hbrBackground = reinterpret_cast<HBRUSH>(COLOR_WINDOW + 1);
    wc.lpszClassName = L"RelayUsbTestWindow";
    RegisterClassW(&wc);

    g_main = CreateWindowExW(
        0,
        wc.lpszClassName,
        L"继电器 USB 测试",
        WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX,
        CW_USEDEFAULT,
        CW_USEDEFAULT,
        860,
        580,
        nullptr,
        nullptr,
        instance,
        nullptr
    );

    ShowWindow(g_main, show_cmd);
    UpdateWindow(g_main);

    MSG msg = {};
    while (GetMessageW(&msg, nullptr, 0, 0)) {
        TranslateMessage(&msg);
        DispatchMessageW(&msg);
    }
    return static_cast<int>(msg.wParam);
}
