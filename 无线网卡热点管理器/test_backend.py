import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import wifi_hotspot_gui as hotspot
from wifi_hotspot_gui import (
    _decode_output,
    adapter_channel_options,
    LinuxHotspotBackend,
    HotspotError,
    localized_adapter_status,
    localized_band,
    localized_nm_device_reason,
    localized_nm_device_state,
    localized_tethering_status,
    PendingRecoveryError,
    WifiAdapter,
    make_ssid,
    parse_driver_capabilities,
    random_unique_channel_assignment,
    ssid_prefix_from_preview,
)


class DriverCapabilityTests(unittest.TestCase):
    def test_custom_ssid_prefix(self):
        self.assertEqual(make_ssid("TEST", 2, "5G"), "TEST2-5G")

    def test_default_adapter_ssid_prefix_is_aaa(self):
        adapter = WifiAdapter(3, "wlan2", "WiFi 3", "disconnected", 3, "")
        self.assertEqual(hotspot.DEFAULT_SSID_PREFIX, "AAA")
        self.assertEqual(adapter.default_ssid, "AAA3-2.4G")

    def test_default_client_wifi_credentials_match_test_network(self):
        self.assertEqual(hotspot.DEFAULT_CLIENT_SSID, "Richlink-Guest-2.4G")
        self.assertEqual(hotspot.DEFAULT_CLIENT_PASSWORD, "richlink_0401")

    def test_ssid_prefix_is_trimmed(self):
        self.assertEqual(make_ssid("  GMY-  ", 1, "2.4G"), "GMY-1-2.4G")

    def test_numeric_ssid_prefix_is_preserved(self):
        preview = make_ssid("TEST2026", 1, "2.4G")
        self.assertEqual(ssid_prefix_from_preview(preview, 1, "2.4G"), "TEST2026")

    def test_utf8_output_decode(self):
        self.assertEqual(_decode_output("承载网络".encode("utf-8")), "承载网络")

    def test_gbk_output_decode_fallback(self):
        self.assertEqual(_decode_output("以太网".encode("gb18030")), "以太网")

    def test_linux_client_connect_creates_profile_per_adapter(self):
        backend = LinuxHotspotBackend()
        backend._require_nmcli = lambda: None
        run_commands = []
        cmd_commands = []
        backend._run = lambda args, timeout=30: run_commands.append((args, timeout)) or (0, "")
        backend._cmd = lambda args, timeout=30: cmd_commands.append((args, timeout)) or ""
        backend._soft_release_device = lambda name: None
        backend._wait_device_leaves_transition = lambda name, timeout=8.0: ""
        backend._scan_wifi_ssid = lambda name, ssid, log: True
        backend._wait_client_connected = lambda name, ssid, timeout=25.0: (True, "100 (connected)｜GMY-CLIENT")
        adapters = [
            WifiAdapter(1, "wlan0", "WiFi 1", "disconnected", 1, ""),
            WifiAdapter(2, "wlan1", "WiFi 2", "disconnected", 2, ""),
        ]
        result = backend.connect_wifi_adapters(adapters, "TEST_AP", "12345678", lambda _: None)
        self.assertEqual(set(result), {"wlan0", "wlan1"})
        connect_profiles = [
            args for args, _ in cmd_commands
            if args[:4] == ["nmcli", "device", "wifi", "connect"]
        ]
        self.assertEqual(len(connect_profiles), 2)
        self.assertIn("ifname", connect_profiles[0])
        self.assertIn("name", connect_profiles[0])
        self.assertTrue(any("GMY-CLIENT-wlan0" in args for args in connect_profiles))
        self.assertTrue(any("GMY-CLIENT-wlan1" in args for args in connect_profiles))
        modify_profiles = [
            args for args, _ in cmd_commands
            if args[:3] == ["nmcli", "connection", "modify"]
        ]
        self.assertTrue(any("connection.autoconnect" in args for args in modify_profiles))
        self.assertTrue(any("connection.interface-name" in args and "wlan0" in args for args in modify_profiles))
        self.assertTrue(any("connection.interface-name" in args and "wlan1" in args for args in modify_profiles))

    def test_linux_client_retries_failed_adapter_once_after_first_round(self):
        backend = LinuxHotspotBackend()
        backend._require_nmcli = lambda: None
        backend._linux_active_wifi_connection_map = lambda: {}
        backend._safe_client_profile_for_adapter = lambda adapter, log: f"GMY-CLIENT-{adapter.name}"
        backend._connection_interface_name = lambda profile: ""
        backend._run = lambda args, timeout=30: (0, "")
        backend._cmd = lambda args, timeout=30: ""
        backend._client_needs_ap_cleanup = lambda name: False
        backend._wait_client_device_ready = lambda name, timeout=15.0: (True, "")
        backend._scan_wifi_ssid = lambda name, ssid, log: True
        backend._wait_client_connected = lambda name, ssid, timeout=25.0: (
            True,
            "100 (connected)｜GMY-CLIENT",
        )
        backend._restore_protected_client_connections = lambda protected, log: None
        activate_calls = 0

        def fake_activate(*args, **kwargs):
            nonlocal activate_calls
            activate_calls += 1
            if activate_calls == 1:
                raise HotspotError("transient activation failure")

        backend._activate_wifi_client_profile = fake_activate
        logs = []
        adapter = WifiAdapter(1, "wlan0", "WiFi 1", "disconnected", 1, "")

        result = backend.connect_wifi_adapters([adapter], "TEST_AP", "12345678", logs.append)

        self.assertIn("wlan0", result)
        self.assertEqual(activate_calls, 2)
        self.assertTrue(any("第一轮连接已完成" in item for item in logs))

    def test_linux_client_fallback_activation_is_bound_to_adapter_ifname(self):
        backend = LinuxHotspotBackend()
        backend._require_nmcli = lambda: None
        run_commands = []
        cmd_commands = []
        backend._run = lambda args, timeout=30: run_commands.append((args, timeout)) or (0, "")

        def fake_cmd(args, timeout=30):
            cmd_commands.append((args, timeout))
            if args[:4] == ["nmcli", "device", "wifi", "connect"]:
                raise HotspotError("primary connect failed")
            return ""

        backend._cmd = fake_cmd
        backend._soft_release_device = lambda name: None
        backend._wait_device_leaves_transition = lambda name, timeout=8.0: ""
        backend._scan_wifi_ssid = lambda name, ssid, log: True
        backend._wait_client_connected = lambda name, ssid, timeout=25.0: (True, "100 (connected)｜GMY-CLIENT")
        adapter = WifiAdapter(1, "wlx500ff502514c", "USB WiFi", "disconnected", 1, "")

        result = backend.connect_wifi_adapters([adapter], "TEST_AP", "12345678", lambda _: None)

        self.assertEqual(set(result), {"wlx500ff502514c"})
        self.assertIn(
            ["nmcli", "connection", "up", "id", "GMY-CLIENT-wlx500ff502514c", "ifname", "wlx500ff502514c"],
            [args for args, _ in cmd_commands],
        )
        self.assertTrue(any(
            args[:3] == ["nmcli", "connection", "modify"]
            and "connection.interface-name" in args
            and "wlx500ff502514c" in args
            for args, _ in cmd_commands
        ))

    def test_linux_client_status_uses_active_connection_when_device_show_lags(self):
        backend = LinuxHotspotBackend()
        backend._require_nmcli = lambda: None

        def fake_run(args, timeout=30):
            if args[:4] == ["nmcli", "-t", "--escape", "no"] and "device" in args and "status" in args:
                return 0, "wlan0:wifi:connected:GMY-CLIENT-wlan0\n"
            if args[:4] == ["nmcli", "-t", "--escape", "no"] and "connection" in args:
                return 0, "GMY-CLIENT-wlan0:wifi:wlan0\n"
            if args[:4] == ["nmcli", "-g", "GENERAL.STATE,GENERAL.CONNECTION,IP4.ADDRESS"]:
                return 0, "30 (disconnected)\n--\n"
            if args[:3] == ["nmcli", "-g", "802-11-wireless.ssid"]:
                return 0, "Richlink-Guest-5G\n"
            return 0, ""

        backend._run = fake_run
        adapter = WifiAdapter(1, "wlan0", "USB WiFi", "disconnected", 1, "")
        with patch.object(hotspot.shutil, "which", return_value=None):
            rows = backend.get_wifi_client_status([adapter], target_ssid="Richlink-Guest-5G")

        self.assertTrue(rows[0]["connected"])
        self.assertEqual(rows[0]["ssid"], "Richlink-Guest-5G")
        self.assertEqual(rows[0]["profile"], "GMY-CLIENT-wlan0")

    def test_linux_client_status_reports_target_visible_without_connection(self):
        backend = LinuxHotspotBackend()
        backend._require_nmcli = lambda: None

        def fake_run(args, timeout=30):
            if args[:4] == ["nmcli", "-t", "--escape", "no"] and "device" in args and "status" in args:
                return 0, "wlan0:wifi:disconnected:--\n"
            if args[:4] == ["nmcli", "-t", "--escape", "no"] and "connection" in args:
                return 0, ""
            if args[:4] == ["nmcli", "-g", "GENERAL.STATE,GENERAL.CONNECTION,IP4.ADDRESS"]:
                return 0, "30 (disconnected)\n--\n"
            if args[:4] == ["nmcli", "-t", "--escape", "no"] and "wifi" in args and "list" in args:
                return 0, "Richlink-Guest-5G:87\n"
            return 0, ""

        backend._run = fake_run
        adapter = WifiAdapter(1, "wlan0", "USB WiFi", "disconnected", 1, "")
        with patch.object(hotspot.shutil, "which", return_value=None):
            rows = backend.get_wifi_client_status([adapter], target_ssid="Richlink-Guest-5G")

        self.assertFalse(rows[0]["connected"])
        self.assertTrue(rows[0]["target_visible"])
        self.assertEqual(rows[0]["target_signal"], "87")

    def test_linux_client_scan_chooses_strongest_bssid_for_same_ssid(self):
        backend = LinuxHotspotBackend()
        backend._run = lambda args, timeout=30: (
            0,
            "14:9F:4F:D2:4F:F7:Richlink-Guest-5G:65\n"
            "14:9F:4F:D2:4F:C7:Richlink-Guest-5G:90\n"
            "14:9F:4F:D2:4F:F6:Other-SSID:99\n",
        )
        self.assertEqual(
            backend._scan_wifi_bssid("wlx500ff502514c", "Richlink-Guest-5G"),
            "14:9F:4F:D2:4F:C7",
        )

    def test_linux_client_connect_localizes_wrong_device_profile_error(self):
        backend = LinuxHotspotBackend()
        backend._require_nmcli = lambda: None
        backend._run = lambda args, timeout=30: (0, "")
        def fake_cmd(args, timeout=30):
            if tuple(args[:4]) in {
                ("nmcli", "device", "wifi", "connect"),
                ("nmcli", "connection", "up", "id"),
            }:
                raise HotspotError(
                    "Error: Connection activation failed: No suitable device found "
                    "(device ens33 not available because profile is not compatible with device "
                    "(mismatching interface name))."
                )
            return ""

        backend._cmd = fake_cmd
        backend._soft_release_device = lambda name: None
        backend._wait_device_leaves_transition = lambda name, timeout=8.0: ""
        backend._scan_wifi_ssid = lambda name, ssid, log: True
        backend._wait_client_connected = lambda name, ssid, timeout=25.0: (True, "100 (connected)｜GMY-CLIENT")
        adapter = WifiAdapter(1, "wlx500ff502514c", "USB WiFi", "disconnected", 1, "")

        with self.assertRaisesRegex(HotspotError, "没有被 NetworkManager 绑定"):
            backend.connect_wifi_adapters([adapter], "TEST_AP", "12345678", lambda _: None)

    def test_linux_client_connect_does_not_delete_profile_bound_to_other_device(self):
        backend = LinuxHotspotBackend()
        backend._require_nmcli = lambda: None
        run_commands = []
        cmd_commands = []

        def fake_run(args, timeout=30):
            run_commands.append(args)
            if args[:4] == ["nmcli", "-g", "connection.interface-name", "connection"]:
                return (0, "ens33\n") if args[-1] == "GMY-CLIENT-wlan0" else (1, "")
            if args[:4] == ["nmcli", "-t", "--escape", "no"] and "connection" in args:
                return 0, ""
            return 0, ""

        def fake_cmd(args, timeout=30):
            cmd_commands.append(args)
            if args[:4] == ["nmcli", "device", "wifi", "connect"]:
                return ""
            return ""

        backend._run = fake_run
        backend._cmd = fake_cmd
        backend._scan_wifi_ssid = lambda name, ssid, log: True
        backend._wait_client_connected = lambda name, ssid, timeout=25.0: (
            True, "100 (connected)｜GMY-CLIENT-wlan0"
        )
        adapter = WifiAdapter(1, "wlan0", "USB WiFi", "disconnected", 1, "")

        result = backend.connect_wifi_adapters([adapter], "TEST_AP", "12345678", lambda _: None)

        self.assertIn("wlan0", result)
        self.assertFalse(any(
            args[:4] == ["nmcli", "connection", "down", "id"]
            and "GMY-CLIENT-wlan0" in args
            for args in run_commands
        ))
        self.assertFalse(any(
            args[:4] == ["nmcli", "connection", "delete", "id"]
            and "GMY-CLIENT-wlan0" in args
            for args in run_commands
        ))
        self.assertTrue(any(
            args[:4] == ["nmcli", "device", "wifi", "connect"]
            and "GMY-CLIENT-wlan0-1" in args
            for args in cmd_commands
        ))

    def test_linux_client_disconnect_is_scoped_to_selected_adapter(self):
        backend = LinuxHotspotBackend()
        backend._require_nmcli = lambda: None
        commands = []
        active_calls = 0

        def fake_run(args, timeout=30):
            nonlocal active_calls
            commands.append(args)
            if args[:4] == ["nmcli", "-t", "--escape", "no"] and "connection" in args:
                active_calls += 1
                if active_calls == 1:
                    return 0, (
                        "GMY-CLIENT-wlan0:wifi:wlan0\n"
                        "GMY-CLIENT-wlan1:wifi:wlan1\n"
                    )
                return 0, "GMY-CLIENT-wlan1:wifi:wlan1\n"
            if args[:4] == ["nmcli", "-g", "connection.interface-name", "connection"]:
                return 0, f"{args[-1].replace('GMY-CLIENT-', '')}\n"
            return 0, ""

        backend._run = fake_run
        target = WifiAdapter(1, "wlan0", "WiFi 1", "connected", 1, "")
        result = backend.disconnect_wifi_adapters([target], lambda _: None)

        self.assertIn("wlan0", result)
        self.assertTrue(any(
            args == [
                "nmcli", "connection", "down", "id",
                "GMY-CLIENT-wlan0", "ifname", "wlan0",
            ]
            for args in commands
        ))
        self.assertTrue(any(
            args == ["nmcli", "connection", "delete", "id", "GMY-CLIENT-wlan0"]
            for args in commands
        ))
        self.assertFalse(any("radio" in args for args in commands))
        self.assertFalse(any("GMY-CLIENT-wlan1" in args for args in commands))

    def test_linux_client_disconnect_recovers_other_adapter_if_driver_drops_it(self):
        backend = LinuxHotspotBackend()
        backend._require_nmcli = lambda: None
        commands = []
        active_calls = 0

        def fake_run(args, timeout=30):
            nonlocal active_calls
            commands.append(args)
            if args[:4] == ["nmcli", "-t", "--escape", "no"] and "connection" in args:
                active_calls += 1
                if active_calls == 1:
                    return 0, (
                        "GMY-CLIENT-wlan0:wifi:wlan0\n"
                        "GMY-CLIENT-wlan1:wifi:wlan1\n"
                    )
                return 0, ""
            if args[:4] == ["nmcli", "-g", "connection.interface-name", "connection"]:
                return 0, f"{args[-1].replace('GMY-CLIENT-', '')}\n"
            return 0, ""

        backend._run = fake_run
        target = WifiAdapter(1, "wlan0", "WiFi 1", "connected", 1, "")
        backend.disconnect_wifi_adapters([target], lambda _: None)

        self.assertIn(
            ["nmcli", "connection", "up", "id", "GMY-CLIENT-wlan1", "ifname", "wlan1"],
            commands,
        )

    def test_linux_client_disconnect_removes_active_safe_suffix_profile(self):
        backend = LinuxHotspotBackend()
        backend._require_nmcli = lambda: None
        commands = []
        active_calls = 0

        def fake_run(args, timeout=30):
            nonlocal active_calls
            commands.append(args)
            if args[:4] == ["nmcli", "-t", "--escape", "no"] and "connection" in args:
                active_calls += 1
                return (
                    (0, "GMY-CLIENT-wlan0-1:wifi:wlan0\n")
                    if active_calls == 1
                    else (0, "")
                )
            if args[:4] == ["nmcli", "-g", "connection.interface-name", "connection"]:
                if args[-1] == "GMY-CLIENT-wlan0-1":
                    return 0, "wlan0\n"
                return 1, ""
            return 0, ""

        backend._run = fake_run
        target = WifiAdapter(1, "wlan0", "WiFi 1", "connected", 1, "")
        backend.disconnect_wifi_adapters([target], lambda _: None)

        self.assertIn(
            ["nmcli", "connection", "down", "id", "GMY-CLIENT-wlan0-1", "ifname", "wlan0"],
            commands,
        )
        self.assertIn(
            ["nmcli", "connection", "delete", "id", "GMY-CLIENT-wlan0-1"],
            commands,
        )

    def test_windows_client_connect_uses_interface_specific_netsh(self):
        backend = hotspot.WindowsHotspotBackend()
        adapter = WifiAdapter(1, "WLAN 2", "USB WiFi", "Up", 2, "")
        commands = []

        backend._wait_windows_client_connected = lambda name, ssid, timeout=30: (
            True,
            f"已连接｜SSID：{ssid}",
        )

        def fake_netsh(args, timeout=30):
            commands.append(args)
            return 0, "ok"

        with patch.object(hotspot, "run_netsh", side_effect=fake_netsh):
            result = backend.connect_wifi_adapters([adapter], "TEST_AP", "12345678", lambda _: None)
        self.assertIn("WLAN 2", result)
        self.assertIn("TEST_AP", result["WLAN 2"])
        self.assertTrue(any(args[:4] == ["netsh", "wlan", "add", "profile"] for args in commands))
        self.assertIn(
            ["netsh", "wlan", "connect", "name=TEST_AP", "ssid=TEST_AP", "interface=WLAN 2"],
            commands,
        )

    def test_windows_client_connect_explains_admin_requirement_for_disabled_adapter(self):
        backend = hotspot.WindowsHotspotBackend()
        adapter = WifiAdapter(1, "WLAN 2", "USB WiFi", "Disabled", 2, "")
        logs = []
        with patch.object(hotspot.os, "name", "nt"), \
             patch.object(hotspot, "is_admin", return_value=False), \
             patch.object(hotspot, "run_netsh") as netsh:
            with self.assertRaisesRegex(HotspotError, "启用网卡需要管理员权限") as ctx:
                backend.connect_wifi_adapters([adapter], "TEST_AP", "12345678", logs.append)
        self.assertIn("以管理员身份运行", str(ctx.exception))
        self.assertTrue(any("管理员权限" in item for item in logs))
        netsh.assert_not_called()

    def test_windows_set_adapter_enabled_sanitizes_access_denied(self):
        backend = hotspot.WindowsHotspotBackend()
        with patch.object(hotspot.os, "name", "nt"), \
             patch.object(hotspot, "is_admin", return_value=True), \
             patch.object(
                 hotspot,
                 "run_powershell",
                 side_effect=HotspotError(
                     "Access is denied.\n所在位置 行:27 字符: 19\n"
                     "FullyQualifiedErrorId : UnauthorizedAccess"
                 ),
             ):
            with self.assertRaisesRegex(HotspotError, "权限不足") as ctx:
                backend.set_adapter_enabled("WLAN 2", True)
        self.assertIn("以管理员身份运行", str(ctx.exception))
        self.assertNotIn("FullyQualifiedErrorId", str(ctx.exception))

    def test_windows_client_retries_when_adapter_reports_power_state_error(self):
        backend = hotspot.WindowsHotspotBackend()
        adapter = WifiAdapter(1, "WLAN 2", "USB WiFi", "Disabled", 2, "")
        commands = []
        connect_attempts = 0

        def fake_netsh(args, timeout=30):
            nonlocal connect_attempts
            commands.append(args)
            if args[:3] == ["netsh", "wlan", "connect"]:
                connect_attempts += 1
                if connect_attempts == 1:
                    return 1, "连接请求失败，错误 0x80342002。"
            return 0, "ok"

        backend._wait_windows_adapter_ready = Mock(return_value=True)
        backend._wait_windows_client_connected = lambda name, ssid, timeout=30: (
            True,
            f"已连接｜SSID：{ssid}",
        )
        with patch.object(hotspot.os, "name", "nt"), \
             patch.object(hotspot, "is_admin", return_value=True), \
             patch.object(backend, "set_adapter_enabled", return_value="Up"), \
             patch.object(hotspot, "run_netsh", side_effect=fake_netsh):
            result = backend.connect_wifi_adapters([adapter], "TEST_AP", "12345678", lambda _: None)

        self.assertIn("WLAN 2", result)
        self.assertEqual(connect_attempts, 2)
        self.assertEqual(backend._wait_windows_adapter_ready.call_count, 2)

    def test_windows_client_explains_software_radio_off(self):
        backend = hotspot.WindowsHotspotBackend()
        adapter = WifiAdapter(1, "WLAN 2", "USB WiFi", "Up", 2, "")
        logs = []

        def fake_netsh(args, timeout=30):
            if args[:4] == ["netsh", "wlan", "show", "interfaces"]:
                return 0, (
                    "Name : WLAN 2\n"
                    "State : disconnected\n"
                    "Radio status : Hardware On\n"
                    "                 Software Off\n"
                )
            self.fail("radio-off preflight should stop before profile/connect commands")

        with patch.object(hotspot, "run_netsh", side_effect=fake_netsh):
            with self.assertRaisesRegex(HotspotError, "无线射频被 Windows 软件关闭") as ctx:
                backend.connect_wifi_adapters([adapter], "TEST_AP", "12345678", logs.append)
        self.assertIn("打开 Windows WiFi", str(ctx.exception))

    def test_windows_client_status_falls_back_when_location_permission_blocks_netsh(self):
        backend = hotspot.WindowsHotspotBackend()
        adapter = WifiAdapter(1, "WLAN 2", "USB WiFi", "Up", 2, "")
        blocked = (
            "网络 shell 命令需要位置权限才能访问 WLAN 信息。\n"
            "功能 WlanQueryInterface 返回错误 5：拒绝访问。"
        )
        profile_json = json.dumps({
            "InterfaceAlias": "WLAN 2",
            "Name": "Richlink-Guest-5G",
            "IPv4Connectivity": "Internet",
            "IPv6Connectivity": "NoTraffic",
        })
        with patch.object(hotspot, "run_netsh", return_value=(1, blocked)), \
             patch.object(hotspot, "run_powershell", return_value=profile_json):
            rows = backend.get_wifi_client_status([adapter], target_ssid="Richlink-Guest-5G")
        self.assertTrue(rows[0]["connected"])
        self.assertEqual(rows[0]["ssid"], "")
        self.assertIsNone(rows[0]["target_match"])
        self.assertIn("不能确认它是不是目标 SSID", rows[0]["warning"])
        self.assertEqual(rows[0]["profile"], "")

    def test_windows_location_limited_connected_status_is_explanatory(self):
        backend = hotspot.WindowsHotspotBackend()
        adapter = WifiAdapter(1, "WLAN 2", "USB WiFi", "Up", 2, "")
        blocked = (
            "网络 shell 命令需要位置权限才能访问 WLAN 信息。\n"
            "功能 WlanQueryInterface 返回错误 5：拒绝访问。"
        )
        profile_json = json.dumps({
            "InterfaceAlias": "WLAN 2",
            "Name": "HAike",
            "IPv4Connectivity": "Internet",
            "IPv6Connectivity": "NoTraffic",
        })
        with patch.object(hotspot, "run_netsh", return_value=(1, blocked)), \
             patch.object(hotspot, "run_powershell", return_value=profile_json):
            rows = backend.get_wifi_client_status([adapter], target_ssid="HAike")
        self.assertTrue(rows[0]["connected"])
        self.assertIn("不能确认它是不是目标 SSID", rows[0]["warning"])

    def test_windows_network_profile_name_does_not_claim_other_ssid(self):
        backend = hotspot.WindowsHotspotBackend()
        adapter = WifiAdapter(1, "WLAN 2", "USB WiFi", "Up", 2, "")
        blocked = (
            "网络 shell 命令需要位置权限才能访问 WLAN 信息。\n"
            "功能 WlanQueryInterface 返回错误 5：拒绝访问。"
        )
        profile_json = json.dumps({
            "InterfaceAlias": "WLAN 2",
            "Name": "gosuncn.com",
            "IPv4Connectivity": "Internet",
            "IPv6Connectivity": "NoTraffic",
        })
        with patch.object(hotspot, "run_netsh", return_value=(1, blocked)), \
             patch.object(hotspot, "run_powershell", return_value=profile_json):
            rows = backend.get_wifi_client_status([adapter], target_ssid="Richlink-Guest-5G")
        self.assertTrue(rows[0]["connected"])
        self.assertEqual(rows[0]["ssid"], "")
        self.assertIsNone(rows[0]["target_match"])
        self.assertNotIn("已连接其他热点", rows[0]["warning"])

    def test_windows_status_prefers_win32_wlan_api_real_ssid(self):
        backend = hotspot.WindowsHotspotBackend()
        adapter = WifiAdapter(1, "WLAN 2", "Realtek WiFi", "Up", 2, "{11111111-1111-1111-1111-111111111111}")
        backend._get_windows_wlan_api_status = lambda adapters: (
            {
                "WLAN 2": {
                    "connected": True,
                    "ssid": "Richlink-Guest-5G",
                    "signal": "86%",
                    "state": "已连接（Win32 WLAN API）",
                }
            },
            "",
        )
        with patch.object(hotspot, "run_netsh", side_effect=AssertionError("不应回退到 netsh")):
            rows = backend.get_wifi_client_status([adapter], target_ssid="Richlink-Guest-5G")
        self.assertTrue(rows[0]["connected"])
        self.assertEqual(rows[0]["ssid"], "Richlink-Guest-5G")
        self.assertEqual(rows[0]["target_match"], True)
        self.assertEqual(rows[0]["signal"], "86%")

    def test_windows_scan_parser_reads_target_signal_when_not_connected(self):
        output = (
            "SSID 1 : Other\n"
            "    BSSID 1 : 00:11:22:33:44:55\n"
            "         Signal             : 99%\n"
            "SSID 2 : Richlink-Guest-5G\n"
            "    BSSID 1 : 14:9F:4F:D2:4F:F7\n"
            "         Signal             : 75%\n"
            "    BSSID 2 : 14:9F:4F:D2:4F:C7\n"
            "         Signal             : 88%\n"
        )
        visible, signal = hotspot.WindowsHotspotBackend._parse_windows_scan_target(
            output, "Richlink-Guest-5G",
        )
        self.assertTrue(visible)
        self.assertEqual(signal, "88%")

    def test_linux_multi_adapter_profiles_and_ssids(self):
        backend = LinuxHotspotBackend()
        commands = []
        backend._require_nmcli = lambda: None
        backend._ensure_cn_regulatory_domain = lambda log=None, allow_elevation=False: True
        backend._run = lambda args, timeout=30: (0, "")
        backend._cmd = lambda args, timeout=30: commands.append(args) or ""
        backend._discover_profiles = lambda active_only=False: []
        backend._wait_for_hotspots_active = lambda expected, timeout=12.0: (
            [
                {"profile": profile, "adapter": adapter, "ssid": ""}
                for profile, adapter in expected.items()
            ],
            {adapter: "AP" for adapter in expected.values()},
        )
        backend._interface_channel = lambda name: 1 if name == "wlan0" else 2
        adapters = [
            WifiAdapter(
                1, "wlan0", "USB WiFi 1", "disconnected", 1, "", True, ("2.4G",),
                {"2.4G": tuple(range(1, 14)), "5G": ()}, True,
            ),
            WifiAdapter(
                2, "wlan1", "USB WiFi 2", "disconnected", 2, "", True, ("2.4G",),
                {"2.4G": tuple(range(1, 14)), "5G": ()}, True,
            ),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir)
            state_file = state_dir / "runtime_state.json"
            with patch.object(hotspot, "STATE_DIR", state_dir), patch.object(hotspot, "STATE_FILE", state_file):
                backend.start_hotspots(
                    adapters, "eth0", "TEST20261-2.4G", "12345678", "2.4G", False,
                    lambda _: None,
                )
                state = json.loads(state_file.read_text(encoding="utf-8"))
        self.assertEqual(state["ssids"], ["TEST20261-2.4G", "TEST20262-2.4G"])
        self.assertEqual(state["bands"], ["2.4G", "2.4G"])
        modify_commands = [
            cmd for cmd in commands
            if cmd[:3] == ["nmcli", "connection", "modify"]
            and "802-11-wireless.mode" in cmd
        ]
        self.assertEqual(len(modify_commands), 2)
        self.assertIn("ap", modify_commands[0])
        self.assertIn("shared", modify_commands[0])
        self.assertIn("connection.autoconnect", modify_commands[0])
        self.assertIn("connection.autoconnect-retries", modify_commands[0])
        self.assertIn("802-11-wireless.powersave", modify_commands[0])
        self.assertNotIn("802-11-wireless.channel", modify_commands[0])
        self.assertNotIn("802-11-wireless.channel", modify_commands[1])
        self.assertEqual(state["channels"], [1, 2])

    def test_random_channels_are_in_range_and_unique(self):
        adapters = [
            WifiAdapter(index, f"wlan{index}", f"WiFi {index}", "disconnected", index, "")
            for index in range(1, 7)
        ]
        assignment = random_unique_channel_assignment(
            adapters, "2.4G", rng=hotspot.random.Random(20260917),
        )
        self.assertEqual(len(assignment), len(adapters))
        self.assertEqual(len(set(assignment.values())), len(adapters))
        self.assertTrue(all(1 <= channel <= 13 for channel in assignment.values()))

    def test_random_5g_channels_use_defined_range_and_exclusions(self):
        adapters = [
            WifiAdapter(index, f"wlan{index}", f"WiFi {index}", "disconnected", index, "")
            for index in range(1, 3)
        ]
        assignment = random_unique_channel_assignment(
            adapters, "5G", excluded={36, 40}, rng=hotspot.random.Random(5),
        )
        self.assertEqual(len(assignment), len(adapters))
        self.assertEqual(len(set(assignment.values())), len(adapters))
        self.assertFalse({36, 40} & set(assignment.values()))
        self.assertTrue(
            all(channel in hotspot.RANDOM_CHANNELS_BY_BAND["5G"] for channel in assignment.values())
        )
        self.assertEqual(
            hotspot.DEFAULT_CHANNELS_BY_BAND["5G"],
            (
                36, 40, 44, 48, 52, 56, 60, 64, 68, 96,
                100, 104, 108, 112, 116, 120, 124, 128,
                132, 136, 140, 144, 149, 153, 157, 161,
                165, 169, 173, 177,
            ),
        )
        self.assertEqual(hotspot.RANDOM_CHANNELS_BY_BAND["5G"], hotspot.DEFAULT_CHANNELS_BY_BAND["5G"])

    def test_random_channels_prefer_currently_usable_driver_channels(self):
        adapters = [
            WifiAdapter(1, "wlan0", "WiFi 1", "disconnected", 1, "", True, ("2.4G",),
                        {"2.4G": (1,), "5G": ()}, True),
            WifiAdapter(2, "wlan1", "WiFi 2", "disconnected", 2, "", True, ("2.4G",),
                        {"2.4G": (1, 6), "5G": ()}, True),
            WifiAdapter(3, "wlan2", "WiFi 3", "disconnected", 3, "", True, ("2.4G",),
                        {"2.4G": (6, 11), "5G": ()}, True),
        ]
        assignment = random_unique_channel_assignment(
            adapters, "2.4G", rng=hotspot.random.Random(8),
        )
        self.assertEqual(set(assignment), {"wlan0", "wlan1", "wlan2"})
        self.assertEqual(len(set(assignment.values())), 3)
        for adapter in adapters:
            self.assertIn(assignment[adapter.name], adapter.channels_by_band["2.4G"])

    def test_random_channels_do_not_duplicate_when_adapters_exceed_capacity(self):
        adapters = [
            WifiAdapter(index, f"wlan{index}", f"WiFi {index}", "disconnected", index, "")
            for index in range(1, 16)
        ]
        assignment = random_unique_channel_assignment(
            adapters, "2.4G", rng=hotspot.random.Random(11),
        )
        self.assertEqual(len(assignment), 13)
        self.assertEqual(len(set(assignment.values())), 13)

    def test_app_displays_auto_channel_for_stopped_adapter(self):
        app = object.__new__(hotspot.HotspotApp)
        app.hotspot_status = {"started": False, "adapter": "", "adapters": []}
        adapter = WifiAdapter(1, "wlan0", "WiFi 1", "disconnected", 1, "")
        self.assertEqual(app._channel_display(adapter), "自动")

    def test_app_recognizes_only_the_matching_adapter_as_running(self):
        app = object.__new__(hotspot.HotspotApp)
        first = WifiAdapter(1, "wlan0", "WiFi 1", "disconnected", 1, "")
        second = WifiAdapter(2, "wlan1", "WiFi 2", "disconnected", 2, "")
        app.hotspot_status = {
            "started": True,
            "adapter": "wlan0",
            "adapters": ["wlan0"],
        }
        self.assertTrue(app._adapter_hotspot_running(first))
        self.assertFalse(app._adapter_hotspot_running(second))

    def test_app_detects_running_hotspot_with_unknown_adapter_assignment(self):
        app = object.__new__(hotspot.HotspotApp)
        app.hotspot_status = {"started": True, "adapter": "", "adapters": []}
        self.assertTrue(app._hotspot_assignment_unknown())

    def test_linux_unknown_assignment_never_stops_all_hotspots(self):
        app = object.__new__(hotspot.HotspotApp)
        app.busy = False
        app.hotspot_status = {"started": True, "adapter": "", "adapters": []}
        app.platform_var = Mock(get=Mock(return_value="Linux"))
        app.stop_all_hotspots = Mock()
        app.stop_hotspot = Mock()
        app.start_hotspot = Mock()
        app.refresh_hotspot_status = Mock()
        adapter = WifiAdapter(1, "wlan0", "WiFi", "connected", 1, "")
        with patch.object(hotspot.messagebox, "showwarning") as warning:
            app._toggle_hotspot_for_adapter(adapter)
        warning.assert_called_once()
        app.refresh_hotspot_status.assert_called_once_with(silent=True)
        app.stop_all_hotspots.assert_not_called()
        app.stop_hotspot.assert_not_called()

    def test_windows_unknown_assignment_uses_system_level_stop(self):
        app = object.__new__(hotspot.HotspotApp)
        app.busy = False
        app.hotspot_status = {"started": True, "adapter": "", "adapters": []}
        app.platform_var = Mock(get=Mock(return_value="Windows"))
        app.stop_all_hotspots = Mock()
        app.stop_hotspot = Mock()
        app.start_hotspot = Mock()
        adapter = WifiAdapter(1, "WLAN", "WiFi", "Up", 1, "")
        app._toggle_hotspot_for_adapter(adapter)
        app.stop_all_hotspots.assert_called_once()

    def test_platform_controls_do_not_require_channel_widgets(self):
        app = object.__new__(hotspot.HotspotApp)
        app.busy = False
        app.platform_var = Mock(get=Mock(return_value="Windows"))
        app.isolate_var = Mock()
        app.isolate_check = Mock()
        app.retry_recovery_button = Mock()
        app.tree = Mock()
        app.selected_adapter = Mock(return_value=None)
        app._update_platform_controls()
        app.isolate_check.configure.assert_called_with(state="normal")
        app.retry_recovery_button.configure.assert_called_with(state="normal")

    def test_app_keeps_adapter_order_stable_during_session(self):
        app = object.__new__(hotspot.HotspotApp)
        app.platform_var = Mock(get=Mock(return_value="Linux"))
        app.adapter_order = {}
        app.next_adapter_index = 1
        first = [
            WifiAdapter(1, "wlan0", "WiFi 1", "disconnected", 1, ""),
            WifiAdapter(2, "wlan1", "WiFi 2", "disconnected", 2, ""),
        ]
        second = [
            WifiAdapter(1, "wlan1", "WiFi 2", "disconnected", 2, ""),
            WifiAdapter(2, "wlan2", "WiFi 3", "disconnected", 3, ""),
            WifiAdapter(3, "wlan0", "WiFi 1", "disconnected", 1, ""),
        ]

        self.assertEqual(
            [(item.name, item.index) for item in app._stabilize_adapter_order(first)],
            [("wlan0", 1), ("wlan1", 2)],
        )
        self.assertEqual(
            [(item.name, item.index) for item in app._stabilize_adapter_order(second)],
            [("wlan0", 1), ("wlan1", 2), ("wlan2", 3)],
        )

    def test_close_window_stops_all_hotspots_before_destroy(self):
        app = object.__new__(hotspot.HotspotApp)
        app.closing = False
        app.busy = False
        app.status_var = Mock()
        app.retry_recovery_button = Mock()
        app.platform_combo = Mock()
        app.progress = Mock()
        app.progress.winfo_manager.return_value = True
        app.backend = Mock()
        app.thread_log = Mock()
        app._set_hotspot_state = Mock()
        app._log = Mock()
        app.events = Mock()

        started_threads = []

        class ImmediateThread:
            def __init__(self, target, daemon=False):
                self.target = target
                self.daemon = daemon

            def start(self):
                started_threads.append(self)
                self.target()

        with patch.object(hotspot.threading, "Thread", ImmediateThread):
            app._on_close()

        app.backend.stop_hotspots.assert_called_once_with([], restore=True, log=app.thread_log)
        app.events.put.assert_called_once_with(("close_done", None))
        self.assertTrue(app.closing)
        self.assertTrue(app.busy)
        self.assertEqual(len(started_threads), 1)

    def test_close_window_allows_pending_recovery_after_hotspot_stop(self):
        app = object.__new__(hotspot.HotspotApp)
        app.closing = False
        app.busy = False
        app.status_var = Mock()
        app.retry_recovery_button = Mock()
        app.platform_combo = Mock()
        app.progress = Mock()
        app.progress.winfo_manager.return_value = True
        app.backend = Mock()
        app.backend.stop_hotspots.side_effect = PendingRecoveryError("热点已停止，但旧网卡设置暂未恢复：WLAN 3")
        app.thread_log = Mock()
        app._set_hotspot_state = Mock()
        app._log = Mock()
        app.events = Mock()

        class ImmediateThread:
            def __init__(self, target, daemon=False):
                self.target = target
                self.daemon = daemon

            def start(self):
                self.target()

        with patch.object(hotspot.threading, "Thread", ImmediateThread):
            app._on_close()

        app.events.put.assert_called_once_with(("close_done", None))
        self.assertGreaterEqual(app.thread_log.call_count, 2)

    def test_close_window_blocks_when_hotspot_may_still_be_running(self):
        app = object.__new__(hotspot.HotspotApp)
        app.closing = False
        app.busy = False
        app.status_var = Mock()
        app.retry_recovery_button = Mock()
        app.platform_combo = Mock()
        app.progress = Mock()
        app.progress.winfo_manager.return_value = True
        app.backend = Mock()
        app.backend.stop_hotspots.side_effect = PendingRecoveryError("当前热点仍在运行，请先停止热点")
        app.thread_log = Mock()
        app._set_hotspot_state = Mock()
        app._log = Mock()
        app.events = Mock()

        class ImmediateThread:
            def __init__(self, target, daemon=False):
                self.target = target
                self.daemon = daemon

            def start(self):
                self.target()

        with patch.object(hotspot.threading, "Thread", ImmediateThread):
            app._on_close()

        kind, payload = app.events.put.call_args.args[0]
        self.assertEqual(kind, "close_error")
        self.assertIsInstance(payload[0], PendingRecoveryError)

    def test_close_error_message_summarizes_missing_windows_adapter_property(self):
        raw = (
            "Get-NetAdapterAdvancedProperty : 找不到任何 \"Name\" 属性等于 \"WLAN 3\" 的 "
            "MSFT_NetAdapterAdvancedPropertySettingData 对象"
        )
        message = hotspot.HotspotApp._close_error_message(RuntimeError(raw))
        self.assertIn("找不到之前记录的网卡或属性", message)
        self.assertIn("重试残留恢复", message)

    def test_app_displays_actual_running_ssid_and_preview_for_stopped_adapter(self):
        app = object.__new__(hotspot.HotspotApp)
        first = WifiAdapter(1, "wlan0", "WiFi 1", "connected", 1, "")
        second = WifiAdapter(2, "wlan1", "WiFi 2", "disconnected", 2, "")
        app.hotspot_status = {
            "started": True,
            "adapter": "wlan0",
            "adapters": ["wlan0"],
            "ssid": "OLD1-2.4G",
            "ssids": ["OLD1-2.4G"],
        }
        app.ssid_prefix_var = Mock(get=Mock(return_value="NEW"))
        app.band_var = Mock(get=Mock(return_value="5G"))
        self.assertEqual(app._ssid_display_for_adapter(first), "OLD1-2.4G")
        self.assertEqual(app._ssid_display_for_adapter(second), "NEW2-5G")

    def test_app_displays_only_confirmed_running_channel_number(self):
        app = object.__new__(hotspot.HotspotApp)
        adapter = WifiAdapter(1, "wlan0", "WiFi 1", "connected", 1, "")
        app.platform_var = Mock(get=Mock(return_value="Linux"))
        app.hotspot_status = {
            "started": True,
            "adapter": "wlan0",
            "adapters": ["wlan0"],
            "channels": [11],
            "channel_confirmed": [True],
        }
        self.assertEqual(app._channel_display(adapter), "11")

    def test_app_displays_unconfirmed_running_channel_clearly(self):
        app = object.__new__(hotspot.HotspotApp)
        adapter = WifiAdapter(1, "WLAN 2", "USB WiFi", "Up", 2, "")
        app.hotspot_status = {
            "started": True,
            "adapter": "WLAN 2",
            "channels": [6],
            "channel": 6,
            "channel_confirmed": False,
        }
        app.platform_var = Mock(get=Mock(return_value="Windows"))
        self.assertEqual(app._channel_display(adapter), "6（未复核）")

    def test_app_blocks_start_for_linux_unmanaged_adapter(self):
        app = object.__new__(hotspot.HotspotApp)
        adapter = WifiAdapter(1, "wlan0", "WiFi 1", "unmanaged", 1, "")
        with patch.object(hotspot.messagebox, "showwarning") as warning:
            app.start_hotspot(adapter)
        warning.assert_called_once()
        self.assertIn("已禁用", warning.call_args.args[1])

    def test_app_blocks_disabling_adapter_when_hotspot_assignment_is_uncertain(self):
        app = object.__new__(hotspot.HotspotApp)
        adapter = WifiAdapter(2, "WLAN 2", "USB WiFi", "Up", 2, "")
        app.hotspot_status = {
            "started": True,
            "adapter": "WLAN 1",
            "adapters": [],
            "adapter_confirmed": False,
        }
        app.selected_adapter = Mock(return_value=adapter)
        app.backend = Mock()
        with patch.object(hotspot.messagebox, "showwarning") as warning:
            app._toggle_adapter(False)
        warning.assert_called_once()
        self.assertIn("无法可靠确认", warning.call_args.args[1])
        app.backend.set_adapter_enabled.assert_not_called()

    def test_app_starts_only_the_requested_linux_adapter(self):
        app = object.__new__(hotspot.HotspotApp)
        adapter = WifiAdapter(2, "wlan1", "WiFi 2", "disconnected", 2, "")
        app.hotspot_status = {"started": False, "adapter": "", "adapters": []}
        app.platform_var = Mock(get=Mock(return_value="Linux"))
        app.ssid_prefix_var = Mock(get=Mock(return_value="TEST"))
        app.band_var = Mock(get=Mock(return_value="2.4G"))
        app.source_var = Mock(get=Mock(return_value="eth0"))
        app.password_var = Mock(get=Mock(return_value="12345678"))
        app.isolate_var = Mock(get=Mock(return_value=False))
        app.status_var = Mock()
        app.backend = Mock()
        app.backend.get_hotspot_status.return_value = {
            "started": True,
            "adapter": "wlan1",
            "adapters": ["wlan1"],
            "ssid": "TEST2-2.4G",
            "ssids": ["TEST2-2.4G"],
        }
        app.thread_log = Mock()
        app._update_tree_hotspot_state = Mock()
        app.refresh_hotspot_status = Mock()
        app._run_async = lambda _label, worker, done: done(worker())
        with patch.object(hotspot.messagebox, "showinfo"):
            app.start_hotspot(adapter)
        app.backend.start_hotspot.assert_called_once()
        called_adapter = app.backend.start_hotspot.call_args.args[0]
        self.assertIs(called_adapter, adapter)
        app.backend.start_hotspots.assert_not_called()

    def test_app_stops_only_the_requested_linux_adapter(self):
        app = object.__new__(hotspot.HotspotApp)
        adapter = WifiAdapter(2, "wlan1", "WiFi 2", "disconnected", 2, "")
        app.hotspot_status = {"started": True, "adapter": "wlan1", "adapters": ["wlan1"]}
        app.platform_var = Mock(get=Mock(return_value="Linux"))
        app.status_var = Mock()
        app.backend = Mock()
        app.thread_log = Mock()
        app._set_hotspot_state = Mock()
        app.after = Mock()
        app._run_async = lambda _label, worker, done: done(worker())
        app.stop_hotspot(adapter)
        stopped_adapters = app.backend.stop_hotspots.call_args.args[0]
        self.assertEqual(stopped_adapters, [adapter])

    def test_adapter_channel_options_keep_common_display_range(self):
        adapter = WifiAdapter(
            2, "wlan1", "WiFi 2", "disconnected", 2, "", True, ("2.4G",),
            {"2.4G": (1, 6, 11), "5G": ()}, True,
        )
        self.assertEqual(
            adapter_channel_options(adapter, "2.4G"),
            tuple(range(1, 14)),
        )
        self.assertEqual(
            adapter_channel_options(adapter, "5G"),
            (
                36, 40, 44, 48, 52, 56, 60, 64, 68, 96,
                100, 104, 108, 112, 116, 120, 124, 128,
                132, 136, 140, 144, 149, 153, 157, 161,
                165, 169, 173, 177,
            ),
        )

    def test_linux_records_actual_channels_after_auto_negotiation(self):
        backend = LinuxHotspotBackend()
        backend._require_nmcli = lambda: None
        backend._ensure_cn_regulatory_domain = lambda log=None, allow_elevation=False: True
        backend._default_route_devices = lambda: ["eth0"]
        backend._discover_profiles = lambda active_only=False: []
        backend._run = lambda args, timeout=30: (0, "")
        backend._cmd = lambda args, timeout=30: ""
        backend._wait_for_hotspots_active = lambda expected, timeout=12.0: (
            [
                {"profile": profile, "adapter": adapter, "ssid": ""}
                for profile, adapter in expected.items()
            ],
            {adapter: "AP" for adapter in expected.values()},
        )
        backend._interface_channel = lambda name: 6
        adapters = [
            WifiAdapter(1, "wlan0", "WiFi 1", "disconnected", 1, "", True, ("2.4G",)),
            WifiAdapter(2, "wlan1", "WiFi 2", "disconnected", 2, "", True, ("2.4G",)),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir)
            state_file = state_dir / "runtime_state.json"
            with patch.object(hotspot, "STATE_DIR", state_dir), patch.object(hotspot, "STATE_FILE", state_file):
                backend.start_hotspots(
                    adapters, "eth0", "AAA1-2.4G", "12345678", "2.4G", False,
                    lambda _: None,
                )
                state = json.loads(state_file.read_text(encoding="utf-8"))
        self.assertEqual(state["channels"], [6, 6])

    def test_linux_status_text_is_localized(self):
        self.assertEqual(localized_adapter_status("connecting (prepare)"), "正在连接")
        self.assertEqual(localized_adapter_status("disconnecting"), "正在断开")
        self.assertEqual(localized_adapter_status("unavailable"), "已启用（暂不可用）")
        self.assertEqual(localized_adapter_status("unmanaged"), "已禁用（未由网络服务管理）")
        self.assertEqual(localized_adapter_status("10 (unmanaged)"), "已禁用（未由网络服务管理）")
        self.assertEqual(localized_adapter_status("30 (disconnected)"), "已启用（未连接）")
        self.assertTrue(hotspot.adapter_status_is_disabled("unmanaged"))
        self.assertTrue(hotspot.adapter_status_is_disabled("10 (unmanaged)"))
        self.assertFalse(hotspot.adapter_status_is_disabled("30 (disconnected)"))

    def test_linux_status_reports_per_adapter_actual_bands_and_channels(self):
        backend = LinuxHotspotBackend()
        backend._require_nmcli = lambda: None
        backend._discover_profiles = lambda active_only=False: [
            {"profile": "GMY-AP-wlan0-1", "adapter": "wlan0", "ssid": "GMY1-2.4G"},
            {"profile": "GMY-AP-wlan1-2", "adapter": "wlan1", "ssid": "GMY2-5G"},
        ] if active_only else []
        backend._interface_mode = lambda name: "AP"
        backend._interface_channel = lambda name: 1 if name == "wlan0" else 36
        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir)
            state_file = state_dir / "runtime_state.json"
            with patch.object(hotspot, "STATE_DIR", state_dir), \
                 patch.object(hotspot, "STATE_FILE", state_file), \
                 patch.object(hotspot, "DEFAULT_STATE_FILE", state_file), \
                 patch.object(hotspot, "LEGACY_STATE_FILE", state_dir / "legacy.json"):
                status = backend.get_hotspot_status()
        self.assertEqual(status["channels"], [1, 36])
        self.assertEqual(status["bands"], ["2.4G", "5G"])
        self.assertEqual(status["band"], "2.4G、5G")
        self.assertTrue(status["channels_confirmed"])
        self.assertTrue(status["band_confirmed"])

    def test_linux_networkmanager_health_is_localized(self):
        self.assertEqual(localized_nm_device_state("120 (failed)"), "连接失败（代码 120）")
        self.assertEqual(
            localized_nm_device_reason("36 (Now removed)"),
            "网卡被拔出或被系统移除（代码 36）",
        )
        backend = LinuxHotspotBackend()
        backend._run = lambda args, timeout=30: (
            0,
            "120 (failed)\n36 (Now removed)\nGMY-AP-wlan1-2\n",
        )
        detail = backend._device_health("wlan1")
        self.assertIn("设备状态：连接失败（代码 120）", detail)
        self.assertIn("掉线原因：网卡被拔出或被系统移除（代码 36）", detail)

    def test_linux_multi_adapter_start_fails_when_only_one_remains_active(self):
        backend = LinuxHotspotBackend()
        backend._require_nmcli = lambda: None
        backend._ensure_cn_regulatory_domain = lambda log=None, allow_elevation=False: True
        backend._default_route_devices = lambda: ["eth0"]
        backend._discover_profiles = lambda active_only=False: []
        backend._run = lambda args, timeout=30: (0, "")
        backend._cmd = lambda args, timeout=30: ""
        backend._wait_for_hotspots_active = lambda expected, timeout=12.0: (
            [{"profile": "GMY-AP-wlan0-1", "adapter": "wlan0", "ssid": "GMY1-2.4G"}],
            {"wlan0": "AP", "wlan1": ""},
        )
        adapters = [
            WifiAdapter(1, "wlan0", "USB WiFi 1", "disconnected", 1, "", True, ("2.4G",)),
            WifiAdapter(2, "wlan1", "USB WiFi 2", "disconnected", 2, "", True, ("2.4G",)),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir)
            state_file = state_dir / "runtime_state.json"
            with patch.object(hotspot, "STATE_DIR", state_dir), patch.object(hotspot, "STATE_FILE", state_file):
                with self.assertRaisesRegex(HotspotError, "1/2"):
                    backend.start_hotspots(
                        adapters, "eth0", "GMY1-2.4G", "12345678", "2.4G", False, lambda _: None
                    )
                self.assertFalse(state_file.exists())

    def test_linux_partial_start_rolls_back_profiles(self):
        backend = LinuxHotspotBackend()
        run_commands = []
        backend._require_nmcli = lambda: None
        backend._ensure_cn_regulatory_domain = lambda log=None, allow_elevation=False: True

        def fake_run(args, timeout=30):
            run_commands.append(args)
            return 0, ""

        def fake_cmd(args, timeout=30):
            if args[:4] == ["nmcli", "connection", "up", "id"] and args[-1].endswith("wlan1-2"):
                raise HotspotError("模拟第二块网卡启动失败")
            return ""

        backend._run = fake_run
        backend._cmd = fake_cmd
        adapters = [
            WifiAdapter(1, "wlan0", "USB WiFi 1", "disconnected", 1, "", True, ("2.4G",)),
            WifiAdapter(2, "wlan1", "USB WiFi 2", "disconnected", 2, "", True, ("2.4G",)),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir)
            state_file = state_dir / "runtime_state.json"
            with patch.object(hotspot, "STATE_DIR", state_dir), patch.object(hotspot, "STATE_FILE", state_file):
                with self.assertRaises(HotspotError):
                    backend.start_hotspots(
                        adapters, "eth0", "GMY1-2.4G", "12345678", "2.4G", False, lambda _: None
                    )
                self.assertFalse(state_file.exists())
        deleted_profiles = [cmd[-1] for cmd in run_commands if cmd[:3] == ["nmcli", "connection", "delete"]]
        self.assertIn("GMY-AP-wlan0-1", deleted_profiles)
        self.assertIn("GMY-AP-wlan1-2", deleted_profiles)

    def test_linux_default_route_devices(self):
        backend = LinuxHotspotBackend()
        backend._run = lambda args, timeout=30: (
            0,
            "default via 192.168.1.1 dev eth0 proto dhcp metric 100\n"
            "default via 10.0.0.1 dev enp3s0 metric 200",
        )
        with patch.object(hotspot.shutil, "which", return_value="/usr/sbin/ip"):
            self.assertEqual(backend._default_route_devices(), ["eth0", "enp3s0"])

    def test_linux_iw_keeps_common_5g_channels_for_diagnostics(self):
        backend = LinuxHotspotBackend()

        def fake_run(args, timeout=30):
            if args[:3] == ["iw", "dev", "wlan0"]:
                return 0, "Interface wlan0\n\twiphy 2"
            return 0, (
                "Supported interface modes:\n\t * AP\n"
                "\t* 5500 MHz [100]\n"
                "\t* 5745 MHz [149]"
            )

        backend._run = fake_run
        with patch.object(hotspot.shutil, "which", return_value="/usr/sbin/iw"):
            self.assertEqual(
                backend._probe_iw("wlan0"),
                (True, ("5G",), {"2.4G": (), "5G": (100, 149)}, True),
            )

    def test_linux_iw_marks_no_ir_channels_unavailable_for_random_assignment(self):
        backend = LinuxHotspotBackend()

        def fake_run(args, timeout=30):
            if args[:3] == ["iw", "dev", "wlan0"]:
                return 0, "Interface wlan0\n\twiphy 2"
            return 0, (
                "Supported interface modes:\n\t * AP\n"
                "\t* 2412 MHz [1] (20.0 dBm) (no IR)\n"
                "\t* 2437 MHz [6] (20.0 dBm) (no IR)\n"
                "\t* 2462 MHz [11] (disabled)\n"
            )

        backend._run = fake_run
        with patch.object(hotspot.shutil, "which", return_value="/usr/sbin/iw"):
            self.assertEqual(
                backend._probe_iw("wlan0"),
                (True, ("2.4G",), {"2.4G": (), "5G": ()}, True),
            )

    def test_linux_regulatory_domain_check_is_skipped(self):
        backend = LinuxHotspotBackend()
        commands = []

        def fake_run(args, timeout=30):
            commands.append(args)
            return 0, ""

        backend._run = fake_run
        logs = []
        self.assertTrue(backend._ensure_cn_regulatory_domain(logs.append, allow_elevation=True))
        self.assertEqual(commands, [])
        self.assertTrue(any("已跳过国家码" in message for message in logs))

    def test_linux_regulatory_skip_never_uses_pkexec(self):
        backend = LinuxHotspotBackend()
        commands = []

        def fake_run(args, timeout=30):
            commands.append((args, timeout))
            return 0, ""

        def fake_which(name):
            return "/usr/sbin/iw" if name == "iw" else "/usr/bin/pkexec" if name == "pkexec" else None

        backend._run = fake_run
        logs = []
        with patch.object(hotspot.shutil, "which", side_effect=fake_which):
            self.assertTrue(backend._ensure_cn_regulatory_domain(logs.append, allow_elevation=True))
        self.assertEqual(commands, [])
        self.assertTrue(any("36/40/44/48" in message for message in logs))

    def test_linux_regulatory_skip_is_stable_after_previous_failure(self):
        backend = LinuxHotspotBackend()
        commands = []

        def fake_run(args, timeout=30):
            commands.append(args)
            return 0, ""

        backend._run = fake_run
        with patch.object(hotspot.shutil, "which", side_effect=lambda name: "/usr/sbin/iw" if name == "iw" else None):
            self.assertTrue(backend._ensure_cn_regulatory_domain())
            self.assertTrue(backend._ensure_cn_regulatory_domain())
        self.assertEqual(commands, [])

    def test_linux_iw_command_failure_is_unknown(self):
        backend = LinuxHotspotBackend()

        def fake_run(args, timeout=30):
            if args[:3] == ["iw", "dev", "wlan0"]:
                return 0, "Interface wlan0\n\twiphy 2"
            return 1, "command failed"

        backend._run = fake_run
        with patch.object(hotspot.shutil, "which", return_value="/usr/sbin/iw"):
            self.assertEqual(backend._probe_iw("wlan0"), (None, (), {}, False))

    def test_linux_active_ap_without_channel_is_not_ready(self):
        backend = LinuxHotspotBackend()
        backend._run = lambda args, timeout=30: (0, "Interface wlan0\n\ttype AP\n")
        with patch.object(hotspot.shutil, "which", return_value="/usr/sbin/iw"):
            self.assertEqual(backend._interface_mode("wlan0"), "AP（未分配工作信道）")

    def test_linux_reads_actual_interface_channel(self):
        backend = LinuxHotspotBackend()
        backend._run = lambda args, timeout=30: (
            0,
            "Interface wlan0\n\ttype AP\n\tchannel 6 (2437 MHz), width: 20 MHz\n",
        )
        with patch.object(hotspot.shutil, "which", return_value="/usr/sbin/iw"):
            self.assertEqual(backend._interface_channel("wlan0"), 6)

    def test_linux_ignores_legacy_channel_argument_and_auto_negotiates(self):
        backend = LinuxHotspotBackend()
        backend._require_nmcli = lambda: None
        backend._ensure_cn_regulatory_domain = lambda log=None, allow_elevation=False: True
        backend._default_route_devices = lambda: ["eth0"]
        backend._discover_profiles = lambda active_only=False: []
        backend._run = lambda args, timeout=30: (0, "")
        commands = []
        backend._cmd = lambda args, timeout=30: commands.append(args) or ""
        backend._wait_for_hotspots_active = lambda expected, timeout=12.0: (
            [{"profile": profile, "adapter": adapter, "ssid": "GMY1-2.4G"}
             for profile, adapter in expected.items()],
            {adapter: "AP" for adapter in expected.values()},
        )
        backend._interface_channel = lambda name: 6
        adapter = WifiAdapter(
            1, "wlan0", "WiFi", "disconnected", 1, "", True, ("2.4G",),
            {"2.4G": (1, 6, 11), "5G": ()}, True,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir)
            state_file = state_dir / "runtime_state.json"
            with patch.object(hotspot, "STATE_DIR", state_dir), patch.object(hotspot, "STATE_FILE", state_file):
                backend.start_hotspots(
                    [adapter], "eth0", "GMY1-2.4G", "12345678", "2.4G", False,
                    lambda _: None, channels={"wlan0": 14},
                )
                state = json.loads(state_file.read_text(encoding="utf-8"))
        modify_commands = [
            cmd for cmd in commands
            if cmd[:3] == ["nmcli", "connection", "modify"]
            and "802-11-wireless.mode" in cmd
        ]
        self.assertEqual(state["channels"], [6])
        self.assertNotIn("802-11-wireless.channel", modify_commands[0])

    def test_linux_keeps_hotspot_and_records_actual_auto_channel(self):
        backend = LinuxHotspotBackend()
        backend._require_nmcli = lambda: None
        backend._ensure_cn_regulatory_domain = lambda log=None, allow_elevation=False: True
        backend._default_route_devices = lambda: ["eth0"]
        backend._discover_profiles = lambda active_only=False: []
        backend._run = lambda args, timeout=30: (0, "")
        backend._cmd = lambda args, timeout=30: ""
        backend._wait_for_hotspots_active = lambda expected, timeout=12.0: (
            [{"profile": profile, "adapter": adapter, "ssid": "GMY1-2.4G"}
             for profile, adapter in expected.items()],
            {adapter: "AP" for adapter in expected.values()},
        )
        backend._interface_channel = lambda name: 6
        adapter = WifiAdapter(
            1, "wlan0", "WiFi", "disconnected", 1, "", True, ("2.4G",),
            {"2.4G": (1, 6, 11), "5G": ()}, True,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir)
            state_file = state_dir / "runtime_state.json"
            with patch.object(hotspot, "STATE_DIR", state_dir), \
                 patch.object(hotspot, "STATE_FILE", state_file):
                logs = []
                backend.start_hotspots(
                    [adapter], "eth0", "GMY1-2.4G", "12345678", "2.4G", False,
                    logs.append,
                )
                state = json.loads(state_file.read_text(encoding="utf-8"))
        self.assertEqual(state["channels"], [6])
        self.assertTrue(any("实际发射信道" in message for message in logs))

    def test_linux_incremental_start_preserves_unchecked_hotspot(self):
        backend = LinuxHotspotBackend()
        commands = []
        backend._require_nmcli = lambda: None
        backend._ensure_cn_regulatory_domain = lambda log=None, allow_elevation=False: True
        backend._default_route_devices = lambda: ["eth0"]
        backend._discover_profiles = lambda active_only=False: ([
            {"profile": "GMY-AP-wlan0-1", "adapter": "wlan0", "ssid": "GMY1-2.4G"}
        ] if active_only else [])
        backend._run = lambda args, timeout=30: (0, "")
        backend._cmd = lambda args, timeout=30: commands.append(args) or ""
        backend._wait_for_hotspots_active = lambda expected, timeout=12.0: (
            [
                {"profile": profile, "adapter": adapter, "ssid": ""}
                for profile, adapter in expected.items()
            ],
            {adapter: "AP" for adapter in expected.values()},
        )
        adapter = WifiAdapter(2, "wlan1", "USB WiFi 2", "disconnected", 2, "", True, ("2.4G", "5G"))
        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir)
            state_file = state_dir / "runtime_state.json"
            state_file.write_text(json.dumps({
                "platform": "linux",
                "profiles": ["GMY-AP-wlan0-1"],
                "adapters": ["wlan0"],
                "ssids": ["GMY1-2.4G"],
                "adapter": "wlan0",
                "ssid": "GMY1-2.4G",
                "source": "eth0",
                "band": "2.4G",
            }), encoding="utf-8")
            with patch.object(hotspot, "STATE_DIR", state_dir), patch.object(hotspot, "STATE_FILE", state_file):
                backend.start_hotspots(
                    [adapter], "eth0", "GMY2-5G", "12345678", "5G", False, lambda _: None
                )
                state = json.loads(state_file.read_text(encoding="utf-8"))
        self.assertEqual(state["adapters"], ["wlan0", "wlan1"])
        self.assertEqual(state["ssids"], ["GMY1-2.4G", "GMY2-5G"])
        self.assertEqual(state["bands"], ["2.4G", "5G"])
        self.assertFalse(any(cmd[:4] == ["nmcli", "connection", "down", "id"] for cmd in commands))

    def test_linux_stop_one_profile_does_not_touch_healthy_protected_profile(self):
        backend = LinuxHotspotBackend()
        backend._require_nmcli = lambda: None
        commands = []
        rows = [
            {"profile": "GMY-AP-wlan0-1", "adapter": "wlan0", "ssid": "GMY1-2.4G"},
            {"profile": "GMY-AP-wlan1-2", "adapter": "wlan1", "ssid": "GMY2-2.4G"},
        ]
        backend._discover_profiles = lambda active_only=False: list(rows)
        backend._interface_mode = lambda name: "AP"
        backend._run = lambda args, timeout=30: commands.append((args, timeout)) or (0, "")
        backend._cmd = lambda args, timeout=30: commands.append((args, timeout)) or ""
        target = WifiAdapter(2, "wlan1", "WiFi 2", "connected", 2, "")
        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir)
            state_file = state_dir / "runtime_state.json"
            state_file.write_text(json.dumps({
                "platform": "linux",
                "profiles": ["GMY-AP-wlan0-1", "GMY-AP-wlan1-2"],
                "adapters": ["wlan0", "wlan1"],
                "ssids": ["GMY1-2.4G", "GMY2-2.4G"],
                "channels": [1, 6],
                "bands": ["2.4G", "2.4G"],
            }), encoding="utf-8")
            with patch.object(hotspot, "STATE_DIR", state_dir), patch.object(hotspot, "STATE_FILE", state_file):
                backend.stop_hotspots([target], restore=True, log=lambda _: None)
                state = json.loads(state_file.read_text(encoding="utf-8"))
        changed_profiles = [args[-1] for args, _ in commands if args[:3] in (
            ["nmcli", "connection", "down"], ["nmcli", "connection", "delete"],
        )]
        self.assertEqual(set(changed_profiles), {"GMY-AP-wlan1-2"})
        self.assertFalse(any(args[:4] == ["nmcli", "connection", "up", "id"] for args, _ in commands))
        self.assertEqual(state["profiles"], ["GMY-AP-wlan0-1"])

    def test_linux_stop_one_profile_recovers_other_profile_if_driver_drops_it(self):
        backend = LinuxHotspotBackend()
        backend._require_nmcli = lambda: None
        commands = []
        logs = []
        active_calls = 0
        all_rows = [
            {"profile": "GMY-AP-wlan0-1", "adapter": "wlan0", "ssid": "GMY1-5G"},
            {"profile": "GMY-AP-wlan1-2", "adapter": "wlan1", "ssid": "GMY2-2.4G"},
        ]

        def discover(active_only=False):
            nonlocal active_calls
            if not active_only:
                return list(all_rows)
            active_calls += 1
            return list(all_rows) if active_calls == 1 else []

        backend._discover_profiles = discover
        backend._interface_mode = lambda name: ""
        backend._run = lambda args, timeout=30: commands.append((args, timeout)) or (0, "")
        backend._cmd = lambda args, timeout=30: commands.append((args, timeout)) or ""
        backend._wait_for_hotspots_active = lambda expected, timeout=12.0: (
            [{"profile": "GMY-AP-wlan0-1", "adapter": "wlan0", "ssid": "GMY1-5G"}],
            {"wlan0": "AP"},
        )
        target = WifiAdapter(2, "wlan1", "WiFi 2", "connected", 2, "")
        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir)
            state_file = state_dir / "runtime_state.json"
            state_file.write_text(json.dumps({
                "platform": "linux",
                "profiles": ["GMY-AP-wlan0-1", "GMY-AP-wlan1-2"],
                "adapters": ["wlan0", "wlan1"],
                "ssids": ["GMY1-5G", "GMY2-2.4G"],
                "channels": [52, 6],
                "bands": ["5G", "2.4G"],
            }), encoding="utf-8")
            with patch.object(hotspot, "STATE_DIR", state_dir), patch.object(hotspot, "STATE_FILE", state_file):
                backend.stop_hotspots([target], restore=True, log=logs.append)
                state = json.loads(state_file.read_text(encoding="utf-8"))
        protected_up = [
            (args, timeout) for args, timeout in commands
            if args == ["nmcli", "connection", "up", "id", "GMY-AP-wlan0-1"]
        ]
        self.assertEqual(protected_up, [
            (["nmcli", "connection", "up", "id", "GMY-AP-wlan0-1"], hotspot.DFS_ACTIVATION_TIMEOUT)
        ])
        self.assertTrue(any("连带影响" in message for message in logs))
        self.assertTrue(any("已重新激活" in message for message in logs))
        self.assertEqual(state["profiles"], ["GMY-AP-wlan0-1"])

    def test_linux_5g_prefers_low_channel_without_dfs_timeout(self):
        backend = LinuxHotspotBackend()
        backend._require_nmcli = lambda: None
        backend._ensure_cn_regulatory_domain = lambda log=None, allow_elevation=False: True
        backend._default_route_devices = lambda: ["eth0"]
        backend._discover_profiles = lambda active_only=False: []
        backend._run = lambda args, timeout=30: (0, "")
        commands = []
        backend._cmd = lambda args, timeout=30: commands.append((args, timeout)) or ""
        wait_timeouts = []
        backend._wait_for_hotspots_active = lambda expected, timeout=12.0: (
            wait_timeouts.append(timeout) or
            ([{"profile": profile, "adapter": name, "ssid": "AAA1-5G"}
              for profile, name in expected.items()], {name: "AP" for name in expected.values()})
        )
        backend._interface_channel = lambda name: 149
        logs = []
        adapter = WifiAdapter(1, "wlan0", "WiFi", "disconnected", 1, "", True, ("5G",))
        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir)
            state_file = state_dir / "runtime_state.json"
            with patch.object(hotspot, "STATE_DIR", state_dir), patch.object(hotspot, "STATE_FILE", state_file):
                backend.start_hotspots(
                    [adapter], "eth0", "AAA1-5G", "12345678", "5G", False,
                    logs.append, channels={"wlan0": 149},
                )
        up_calls = [
            (args, timeout) for args, timeout in commands
            if args[:4] == ["nmcli", "connection", "up", "id"]
        ]
        self.assertEqual(up_calls[0][1], hotspot.NORMAL_ACTIVATION_TIMEOUT)
        self.assertEqual(wait_timeouts, [hotspot.NORMAL_VERIFY_TIMEOUT])
        self.assertFalse(any("CAC" in message for message in logs))
        self.assertTrue(any("实际发射信道" in message for message in logs))
        modify_commands = [
            args for args, _ in commands
            if args[:3] == ["nmcli", "connection", "modify"]
            and "802-11-wireless.mode" in args
        ]
        self.assertEqual(
            modify_commands[0][modify_commands[0].index("802-11-wireless.channel") + 1],
            "36",
        )

    def test_linux_5g_low_channel_failure_falls_back_to_auto_channel(self):
        backend = LinuxHotspotBackend()
        backend._require_nmcli = lambda: None
        backend._ensure_cn_regulatory_domain = lambda log=None, allow_elevation=False: True
        backend._default_route_devices = lambda: ["eth0"]
        backend._discover_profiles = lambda active_only=False: []
        backend._run = lambda args, timeout=30: (0, "")
        commands = []
        up_attempts = 0

        def fake_cmd(args, timeout=30):
            nonlocal up_attempts
            commands.append((args, timeout))
            if args[:4] == ["nmcli", "connection", "up", "id"]:
                up_attempts += 1
                if up_attempts == 1:
                    raise HotspotError("Error: Connection activation failed")
            return ""

        backend._cmd = fake_cmd
        wait_timeouts = []
        backend._wait_for_hotspots_active = lambda expected, timeout=12.0: (
            wait_timeouts.append(timeout) or
            ([{"profile": profile, "adapter": name, "ssid": "AAA1-5G"}
              for profile, name in expected.items()], {name: "AP" for name in expected.values()})
        )
        backend._interface_channel = lambda name: 161
        logs = []
        adapter = WifiAdapter(1, "wlan0", "WiFi", "disconnected", 1, "", True, ("5G",))
        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir)
            state_file = state_dir / "runtime_state.json"
            with patch.object(hotspot, "STATE_DIR", state_dir), patch.object(hotspot, "STATE_FILE", state_file):
                backend.start_hotspots(
                    [adapter], "eth0", "AAA1-5G", "12345678", "5G", False, logs.append,
                )
                state = json.loads(state_file.read_text(encoding="utf-8"))
        self.assertEqual(up_attempts, 2)
        self.assertIn(
            (["nmcli", "connection", "modify", "GMY-AP-wlan0-1", "802-11-wireless.channel", "0"], 20),
            commands,
        )
        self.assertEqual(state["channels"], [161])
        self.assertTrue(any("退回由系统和网卡自动协商信道" in message for message in logs))

    def test_linux_command_timeout_is_translated_to_hotspot_error(self):
        backend = LinuxHotspotBackend()
        timeout_error = hotspot.subprocess.TimeoutExpired(
            ["nmcli", "connection", "up"], 180, output=b"waiting for activation",
        )
        with patch.object(hotspot, "run_process", side_effect=timeout_error):
            with self.assertRaisesRegex(HotspotError, "等待超过 180 秒"):
                backend._run(["nmcli", "connection", "up"], timeout=180)

    def test_linux_supplicant_timeout_soft_resets_target_adapter_before_retry(self):
        backend = LinuxHotspotBackend()
        backend._require_nmcli = lambda: None
        backend._ensure_cn_regulatory_domain = lambda log=None, allow_elevation=False: True
        backend._default_route_devices = lambda: ["eth0"]
        backend._discover_profiles = lambda active_only=False: []
        backend._wait_for_hotspots_active = lambda expected, timeout=12.0: (
            [
                {"profile": profile, "adapter": adapter, "ssid": "AAA1-5G"}
                for profile, adapter in expected.items()
            ],
            {adapter: "AP" for adapter in expected.values()},
        )
        backend._interface_channel = lambda name: 161
        run_commands = []

        def fake_run(args, timeout=30):
            run_commands.append(args)
            if args[:4] == ["nmcli", "-g", "GENERAL.STATE", "device"]:
                return 0, "30 (disconnected)"
            return 0, ""

        up_attempts = 0
        cmd_commands = []

        def fake_cmd(args, timeout=30):
            nonlocal up_attempts
            cmd_commands.append(args)
            if args[:4] == ["nmcli", "connection", "up", "id"]:
                up_attempts += 1
                if up_attempts == 1:
                    raise HotspotError(
                        "Error: Connection activation failed: "
                        "802.1X supplicant took too long to authenticate"
                    )
            return ""

        backend._run = fake_run
        backend._cmd = fake_cmd
        logs = []
        adapter = WifiAdapter(1, "wlan0", "WiFi", "disconnected", 1, "", True, ("5G",))
        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir)
            state_file = state_dir / "runtime_state.json"
            with patch.object(hotspot, "STATE_DIR", state_dir), \
                 patch.object(hotspot, "STATE_FILE", state_file), \
                 patch.object(hotspot.time, "sleep"):
                backend.start_hotspots(
                    [adapter], "eth0", "AAA1-5G", "12345678", "5G", False,
                    logs.append, channels={"wlan0": 161},
                )
        self.assertEqual(up_attempts, 2)
        self.assertIn(["nmcli", "device", "set", "wlan0", "managed", "no"], run_commands)
        self.assertIn(["nmcli", "device", "set", "wlan0", "managed", "yes"], run_commands)
        self.assertTrue(any("软复位" in message for message in logs))

    def test_linux_status_discovers_active_profile_without_state(self):
        backend = LinuxHotspotBackend()
        backend._require_nmcli = lambda: None
        backend._discover_profiles = lambda active_only=False: [
            {"profile": "GMY-AP-wlan0-1", "adapter": "wlan0", "ssid": "GMY1-2.4G"}
        ] if active_only else []
        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir)
            state_file = state_dir / "runtime_state.json"
            with patch.object(hotspot, "STATE_DIR", state_dir), patch.object(hotspot, "STATE_FILE", state_file):
                status = backend.get_hotspot_status()
        self.assertTrue(status["started"])
        self.assertEqual(status["adapters"], ["wlan0"])

    def test_linux_status_reports_partial_dropout(self):
        backend = LinuxHotspotBackend()
        backend._require_nmcli = lambda: None
        backend._discover_profiles = lambda active_only=False: [
            {"profile": "GMY-AP-wlan0-1", "adapter": "wlan0", "ssid": "GMY1-2.4G"}
        ] if active_only else []
        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir)
            state_file = state_dir / "runtime_state.json"
            state_file.write_text(json.dumps({
                "platform": "linux",
                "profiles": ["GMY-AP-wlan0-1", "GMY-AP-wlan1-2"],
                "adapters": ["wlan0", "wlan1"],
                "ssids": ["GMY1-2.4G", "GMY2-2.4G"],
                "band": "2.4G",
            }), encoding="utf-8")
            with patch.object(hotspot, "STATE_DIR", state_dir), \
                 patch.object(hotspot, "STATE_FILE", state_file), \
                 patch.object(hotspot, "DEFAULT_STATE_FILE", state_file), \
                 patch.object(hotspot, "LEGACY_STATE_FILE", state_dir / "legacy.json"):
                status = backend.get_hotspot_status()
        self.assertTrue(status["started"])
        self.assertTrue(status["degraded"])
        self.assertEqual(status["active_count"], 1)
        self.assertEqual(status["expected_count"], 2)
        self.assertEqual(status["missing_adapters"], ["wlan1"])

    def test_linux_status_treats_active_profile_without_channel_as_dropout(self):
        backend = LinuxHotspotBackend()
        backend._require_nmcli = lambda: None
        backend._discover_profiles = lambda active_only=False: [
            {"profile": "GMY-AP-wlan0-1", "adapter": "wlan0", "ssid": "GMY1-2.4G"},
            {"profile": "GMY-AP-wlan1-2", "adapter": "wlan1", "ssid": "GMY2-2.4G"},
        ] if active_only else []
        backend._interface_mode = lambda name: "AP" if name == "wlan0" else "AP（未分配工作信道）"
        backend._device_health = lambda name: "设备状态：已连接并激活（代码 100）"
        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir)
            state_file = state_dir / "runtime_state.json"
            state_file.write_text(json.dumps({
                "platform": "linux",
                "profiles": ["GMY-AP-wlan0-1", "GMY-AP-wlan1-2"],
                "adapters": ["wlan0", "wlan1"],
                "ssids": ["GMY1-2.4G", "GMY2-2.4G"],
                "band": "2.4G",
            }), encoding="utf-8")
            with patch.object(hotspot, "STATE_DIR", state_dir), \
                 patch.object(hotspot, "STATE_FILE", state_file), \
                 patch.object(hotspot, "DEFAULT_STATE_FILE", state_file), \
                 patch.object(hotspot, "LEGACY_STATE_FILE", state_dir / "legacy.json"):
                status = backend.get_hotspot_status()
        self.assertTrue(status["started"])
        self.assertTrue(status["degraded"])
        self.assertEqual(status["active_count"], 1)
        self.assertEqual(status["missing_adapters"], ["wlan1"])
        self.assertIn("未分配工作信道", status["dropout_details"]["wlan1"])

    def test_linux_adapter_toggle_changes_managed_state(self):
        backend = LinuxHotspotBackend()
        commands = []
        backend._require_nmcli = lambda: None
        backend._cmd = lambda args, timeout=30: commands.append(args) or "100 (connected)"
        backend.set_adapter_enabled("wlan0", False)
        self.assertEqual(commands[0], ["nmcli", "device", "set", "wlan0", "managed", "no"])

    def test_restore_band_supports_legacy_state(self):
        backend = hotspot.WindowsHotspotBackend()
        scripts = []
        with patch.object(
            hotspot, "run_powershell",
            side_effect=lambda script, timeout=30: scripts.append(script) or "",
        ), patch.object(backend, "_restart_adapter") as restart:
            backend._restore_band("WLAN 2", {
                "Applied": True,
                "Property": "Wireless Mode",
                "Previous": ["16"],
            })
        self.assertIn("DisplayName -eq $displayName", scripts[0])
        self.assertIn("'16'", scripts[0])
        restart.assert_called_once_with("WLAN 2")

    def test_windows_channel_setter_uses_only_explicit_driver_channel_properties(self):
        backend = hotspot.WindowsHotspotBackend()
        scripts = []
        response = json.dumps({
            "Applied": True,
            "Property": "Ad Hoc Channel 802.11b/g",
            "RegistryKeyword": "AdHocChannel",
            "Value": "6",
            "Previous": [1],
        })
        with patch.object(
            hotspot, "run_powershell",
            side_effect=lambda script, timeout=30: scripts.append(script) or response,
        ):
            result = backend._set_channel("WLAN 2", "2.4G", 6)
        self.assertTrue(result["Applied"])
        self.assertIn("$wanted=6", scripts[0])
        self.assertIn("soft.?ap", scripts[0])
        self.assertNotIn("channel.*width", scripts[0].lower())

    def test_windows_channel_setter_rejects_channel_from_wrong_band(self):
        backend = hotspot.WindowsHotspotBackend()
        with self.assertRaisesRegex(HotspotError, "不属于 5G"):
            backend._set_channel("WLAN 2", "5G", 6)

    def test_runtime_state_falls_back_to_legacy_location(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            primary = root / "new" / "runtime_state.json"
            legacy = root / "runtime_state.json"
            legacy.write_text('{"platform":"windows","adapter":"WLAN 2"}', encoding="utf-8")
            with patch.object(hotspot, "STATE_FILE", primary), \
                 patch.object(hotspot, "DEFAULT_STATE_FILE", primary), \
                 patch.object(hotspot, "LEGACY_STATE_FILE", legacy):
                self.assertEqual(hotspot.load_runtime_state()["adapter"], "WLAN 2")

    def test_runtime_state_ignores_non_object_primary_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            primary = root / "new" / "runtime_state.json"
            legacy = root / "runtime_state.json"
            primary.parent.mkdir()
            primary.write_text('["unexpected"]', encoding="utf-8")
            legacy.write_text('{"platform":"windows","adapter":"WLAN 2"}', encoding="utf-8")
            with patch.object(hotspot, "STATE_FILE", primary), \
                 patch.object(hotspot, "DEFAULT_STATE_FILE", primary), \
                 patch.object(hotspot, "LEGACY_STATE_FILE", legacy):
                self.assertEqual(hotspot.load_runtime_state()["adapter"], "WLAN 2")

    def test_ics_restore_script_restores_saved_roles(self):
        backend = hotspot.WindowsHotspotBackend()
        scripts = []
        with patch.object(hotspot, "run_powershell", side_effect=lambda script, timeout=30: scripts.append(script) or ""):
            backend._restore_ics([
                {"Name": "Ethernet", "Type": 0},
                {"Name": "Local Area Connection* 1", "Type": 1},
            ])
        self.assertIn("Sort-Object Type", scripts[0])
        self.assertIn("'Ethernet'", scripts[0])
        self.assertIn("Type=1", scripts[0])

    def test_windows_stop_failure_preserves_runtime_state(self):
        backend = hotspot.WindowsHotspotBackend()
        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir)
            state_file = state_dir / "runtime_state.json"
            state_file.write_text(json.dumps({
                "platform": "windows",
                "adapter": "WLAN 2",
                "disabled_adapters": ["WLAN"],
                "ics_names": ["Ethernet", "Local Area Connection* 1"],
            }), encoding="utf-8")
            with patch.object(hotspot, "STATE_DIR", state_dir), \
                 patch.object(hotspot, "STATE_FILE", state_file), \
                 patch.object(hotspot, "run_netsh", return_value=(1, "stop failed")), \
                 patch.object(backend, "get_hotspot_status", return_value={"started": True, "returncode": 0}):
                with self.assertRaises(HotspotError):
                    backend.stop_hotspot(restore=True, log=lambda _: None)
            self.assertTrue(state_file.exists())

    def test_windows_start_failure_invokes_full_rollback(self):
        backend = hotspot.WindowsHotspotBackend()
        adapter = WifiAdapter(1, "WLAN 2", "USB WiFi", "Up", 2, "", True, ("2.4G",))
        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir)
            state_file = state_dir / "runtime_state.json"
            with patch.object(hotspot, "STATE_DIR", state_dir), \
                 patch.object(hotspot, "STATE_FILE", state_file), \
                 patch.object(backend, "stop_hotspot") as stop, \
                 patch.object(backend, "_adapter_is_enabled", return_value=True), \
                 patch.object(backend, "set_adapter_enabled"), \
                 patch.object(backend, "_list_other_wifi", return_value=["WLAN"]), \
                 patch.object(backend, "_disable_wifi_adapters"), \
                 patch.object(backend, "_set_band", return_value={"Applied": False}), \
                 patch.object(backend, "_start_modern_hotspot", side_effect=HotspotError("modern failed")), \
                 patch.object(hotspot, "run_netsh", return_value=(1, "set failed")):
                with self.assertRaises(HotspotError):
                    backend.start_hotspot(
                        adapter, "Ethernet", "GMY1-2.4G", "12345678", "2.4G", True, lambda _: None
                    )
            self.assertEqual(stop.call_count, 2)

    def test_windows_legacy_failure_falls_back_to_modern_hotspot(self):
        backend = hotspot.WindowsHotspotBackend()
        adapter = WifiAdapter(1, "WLAN 2", "USB WiFi", "Disconnected", 2, "", False, ("2.4G",))
        logs = []
        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir)
            state_file = state_dir / "runtime_state.json"
            with patch.object(hotspot, "STATE_DIR", state_dir), \
                 patch.object(hotspot, "STATE_FILE", state_file), \
                 patch.object(backend, "stop_hotspot") as stop, \
                 patch.object(backend, "_adapter_is_enabled", return_value=True), \
                 patch.object(backend, "set_adapter_enabled"), \
                 patch.object(backend, "_set_band", return_value={"Applied": False}), \
                  patch.object(
                     backend, "_start_modern_hotspot",
                     return_value={"Success": True, "Ssid": "GMY1-2.4G"},
                 ) as modern, \
                 patch.object(hotspot, "run_netsh", return_value=(1, "模拟配置失败")) as netsh:
                backend.start_hotspot(
                    adapter, "Ethernet", "GMY1-2.4G", "12345678", "2.4G", False, logs.append,
                )
            self.assertEqual(stop.call_count, 1)
            self.assertTrue(any("报告旧式 Hosted Network 不受支持" in message for message in logs))
            self.assertTrue(any("自动切换到 Windows 现代移动热点" in message for message in logs))
            self.assertEqual(netsh.call_args.args[0][0:4], ["netsh", "wlan", "set", "hostednetwork"])
            modern.assert_called_once_with("Ethernet", "GMY1-2.4G", "12345678", "2.4G")
            saved = json.loads(state_file.read_text(encoding="utf-8"))
            self.assertEqual(saved["hotspot_backend"], "modern")
            self.assertEqual(saved["channel"], 0)
            self.assertIsNone(saved["channel_setting"])

    def test_windows_status_reports_requested_channel_as_unconfirmed(self):
        backend = hotspot.WindowsHotspotBackend()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state_file = root / "runtime_state.json"
            state_file.write_text(json.dumps({
                "platform": "windows", "adapter": "WLAN 2", "source_name": "Ethernet",
                "hotspot_backend": "legacy", "band": "2.4G", "channel": 11,
            }), encoding="utf-8")
            with patch.object(hotspot, "STATE_FILE", state_file), \
                 patch.object(hotspot, "DEFAULT_STATE_FILE", state_file), \
                 patch.object(hotspot, "LEGACY_STATE_FILE", root / "legacy.json"), \
                 patch.object(
                     hotspot, "run_netsh",
                     return_value=(0, 'Status : Started\nSSID name : "GMY1-2.4G"'),
                 ), \
                 patch.object(backend, "_get_modern_hotspot_status", return_value={
                     "available": True, "started": False, "state": "Off",
                 }):
                status = backend.get_hotspot_status()
        self.assertEqual(status["channels"], [11])
        self.assertEqual(status["channel"], 11)
        self.assertTrue(status["channels_requested"])
        self.assertFalse(status["channels_confirmed"])

    def test_windows_legacy_status_reports_actual_channel(self):
        backend = hotspot.WindowsHotspotBackend()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state_file = root / "runtime_state.json"
            state_file.write_text(json.dumps({
                "platform": "windows", "adapter": "WLAN 2", "source_name": "Ethernet",
                "hotspot_backend": "legacy", "band": "2.4G", "channel": 6,
            }), encoding="utf-8")
            with patch.object(hotspot, "STATE_FILE", state_file), \
                 patch.object(hotspot, "DEFAULT_STATE_FILE", state_file), \
                 patch.object(hotspot, "LEGACY_STATE_FILE", root / "legacy.json"), \
                 patch.object(
                     hotspot, "run_netsh",
                     return_value=(
                         0,
                         'Status : Started\nSSID name : "GMY1-2.4G"\nChannel : 11\n',
                     ),
                 ), \
                 patch.object(backend, "_get_modern_hotspot_status", return_value={
                     "available": True, "started": False, "state": "Off",
                 }):
                status = backend.get_hotspot_status()
        self.assertEqual(status["channels"], [11])
        self.assertEqual(status["channel"], 11)
        self.assertTrue(status["channels_confirmed"])
        self.assertTrue(status["channel_confirmed"])

    def test_windows_not_present_target_is_rejected(self):
        backend = hotspot.WindowsHotspotBackend()
        adapter = WifiAdapter(1, "WLAN", "Internal WiFi", "Not Present", 20, "", None, ())
        with self.assertRaisesRegex(HotspotError, "Not Present"):
            backend.start_hotspot(
                adapter, "Ethernet", "GMY1-2.4G", "12345678", "2.4G", False, lambda _: None
            )

    def test_windows_other_adapter_list_excludes_not_present_hardware(self):
        backend = hotspot.WindowsHotspotBackend()
        scripts = []
        with patch.object(
            hotspot, "run_powershell", side_effect=lambda script, timeout=30: scripts.append(script) or ""
        ):
            self.assertEqual(backend._list_other_wifi("WLAN 2"), [])
        self.assertIn("'Disabled','Not Present'", scripts[0])

    def test_windows_adapter_toggle_retries_status_and_uses_wmi_fallback(self):
        backend = hotspot.WindowsHotspotBackend()
        scripts = []
        with patch.object(
            hotspot, "run_powershell",
            side_effect=lambda script, timeout=30: scripts.append(script) or "Enabled（WMI）",
        ), patch.object(hotspot, "is_admin", return_value=True):
            status = backend.set_adapter_enabled("WLAN 3", True)
        self.assertEqual(status, "Enabled（WMI）")
        self.assertIn("$wantEnabled=$true", scripts[0])
        self.assertIn("Get-CimInstance Win32_NetworkAdapter", scripts[0])
        self.assertIn("命令已提交，驱动状态仍在刷新", scripts[0])

    def test_windows_modern_status_parses_active_hotspot(self):
        backend = hotspot.WindowsHotspotBackend()
        payload = json.dumps({"Rows": [{
            "Source": "Ethernet",
            "Profile": "Ethernet",
            "Capability": "Enabled",
            "State": "On",
            "Ssid": "GMY3-2.4G",
            "Band": "TwoPointFourGigahertz",
            "Authentication": "Wpa2",
        }]})
        with patch.object(hotspot, "run_powershell", return_value=payload):
            status = backend._get_modern_hotspot_status()
        self.assertTrue(status["available"])
        self.assertTrue(status["started"])
        self.assertEqual(status["ssid"], "GMY3-2.4G")
        self.assertEqual(status["authentication"], "Wpa2")

    def test_windows_combined_status_marks_modern_adapter_unconfirmed(self):
        backend = hotspot.WindowsHotspotBackend()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state_file = root / "runtime_state.json"
            state_file.write_text(json.dumps({
                "platform": "windows", "adapter": "WLAN 3", "source_name": "Ethernet",
                "hotspot_backend": "modern",
            }), encoding="utf-8")
            with patch.object(hotspot, "STATE_FILE", state_file), \
                 patch.object(hotspot, "DEFAULT_STATE_FILE", state_file), \
                 patch.object(hotspot, "LEGACY_STATE_FILE", root / "legacy.json"), \
                 patch.object(hotspot, "run_netsh", return_value=(0, "Status : Not available")), \
                 patch.object(backend, "_get_modern_hotspot_status", return_value={
                     "available": True, "started": True, "state": "On", "ssid": "GMY3-2.4G",
                     "source": "Ethernet", "band": "TwoPointFourGigahertz",
                     "authentication": "Wpa2",
                 }):
                status = backend.get_hotspot_status()
        self.assertTrue(status["started"])
        self.assertEqual(status["backend"], "modern")
        self.assertEqual(status["adapter"], "WLAN 3")
        self.assertFalse(status["adapter_confirmed"])
        self.assertTrue(status["band_confirmed"])
        self.assertEqual(status["band"], "TwoPointFourGigahertz")
        self.assertEqual(status["status"], "已启动")
        self.assertEqual(status["backend_label"], "Windows 现代移动热点")

    def test_windows_legacy_status_does_not_claim_requested_band_is_confirmed(self):
        backend = hotspot.WindowsHotspotBackend()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state_file = root / "runtime_state.json"
            state_file.write_text(json.dumps({
                "platform": "windows", "adapter": "WLAN 3", "source_name": "Ethernet",
                "hotspot_backend": "legacy", "band": "5G",
            }), encoding="utf-8")
            with patch.object(hotspot, "STATE_FILE", state_file), \
                 patch.object(hotspot, "DEFAULT_STATE_FILE", state_file), \
                 patch.object(hotspot, "LEGACY_STATE_FILE", root / "legacy.json"), \
                 patch.object(hotspot, "run_netsh", return_value=(0, 'Status : Started\nSSID name : "GMY1-5G"')), \
                 patch.object(backend, "_get_modern_hotspot_status", return_value={
                     "available": True, "started": False, "state": "Off",
                 }):
                status = backend.get_hotspot_status()
        self.assertTrue(status["started"])
        self.assertFalse(status["band_confirmed"])
        self.assertEqual(status["requested_band"], "5G")

    def test_windows_failed_restore_moves_state_to_pending(self):
        backend = hotspot.WindowsHotspotBackend()
        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir)
            state_file = state_dir / "runtime_state.json"
            pending_file = state_dir / "pending_recovery.json"
            state_file.write_text(json.dumps({
                "platform": "windows",
                "adapter": "Missing WLAN",
                "disabled_adapters": [],
                "ics_names": [],
                "ics_snapshot": None,
                "band_setting": {"Applied": True, "Property": "Wireless Mode", "Previous": ["16"]},
            }), encoding="utf-8")
            with patch.object(hotspot, "STATE_DIR", state_dir), \
                 patch.object(hotspot, "STATE_FILE", state_file), \
                 patch.object(hotspot, "PENDING_STATE_FILE", pending_file), \
                 patch.object(hotspot, "run_netsh", return_value=(0, "stopped")), \
                 patch.object(backend, "get_hotspot_status", return_value={"started": False, "returncode": 0}), \
                 patch.object(backend, "_restore_band", side_effect=HotspotError("网卡不存在")):
                with self.assertRaises(PendingRecoveryError):
                    backend.stop_hotspot(restore=True, log=lambda _: None)
            self.assertFalse(state_file.exists())
            self.assertTrue(pending_file.exists())
            pending = json.loads(pending_file.read_text(encoding="utf-8"))
            self.assertEqual(pending["adapter"], "Missing WLAN")
            self.assertIsNotNone(pending["band_setting"])

    def test_windows_pending_recovery_clears_after_adapter_returns(self):
        backend = hotspot.WindowsHotspotBackend()
        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir)
            pending_file = state_dir / "pending_recovery.json"
            pending_file.write_text(json.dumps({
                "platform": "windows",
                "adapter": "WLAN 2",
                "disabled_adapters": ["WLAN"],
                "ics_names": [],
                "ics_snapshot": None,
                "band_setting": {"Applied": True, "Property": "Wireless Mode", "Previous": ["16"]},
            }), encoding="utf-8")
            with patch.object(hotspot, "PENDING_STATE_FILE", pending_file), \
                 patch.object(backend, "get_hotspot_status", return_value={"started": False, "returncode": 0}), \
                 patch.object(backend, "_restore_band") as restore_band, \
                 patch.object(backend, "_enable_adapters") as enable_adapters:
                backend.retry_pending_recovery(log=lambda _: None)
            restore_band.assert_called_once()
            enable_adapters.assert_called_once_with(["WLAN"])
            self.assertFalse(pending_file.exists())

    def test_windows_appending_pending_recovery_keeps_older_record(self):
        backend = hotspot.WindowsHotspotBackend()
        with tempfile.TemporaryDirectory() as temp_dir:
            pending_file = Path(temp_dir) / "pending_recovery.json"
            pending_file.write_text(
                '{"platform":"windows","adapter":"Old WLAN","disabled_adapters":[]}',
                encoding="utf-8",
            )
            with patch.object(hotspot, "PENDING_STATE_FILE", pending_file):
                backend._append_pending_recovery({
                    "platform": "windows", "adapter": "New WLAN", "disabled_adapters": []
                })
            pending = json.loads(pending_file.read_text(encoding="utf-8"))
            self.assertEqual(
                [item["adapter"] for item in pending["recoveries"]],
                ["Old WLAN", "New WLAN"],
            )

    def test_windows_restores_originally_disabled_target(self):
        backend = hotspot.WindowsHotspotBackend()
        state = {
            "platform": "windows",
            "adapter": "WLAN 2",
            "target_was_enabled": False,
            "disabled_adapters": [],
            "ics_names": [],
            "ics_snapshot": None,
            "band_setting": {"Applied": False},
        }
        with patch.object(backend, "_restore_band"), \
             patch.object(backend, "set_adapter_enabled", return_value="Disabled") as set_enabled:
            failures = backend._restore_saved_settings(state, log=lambda _: None)
        self.assertEqual(failures, [])
        set_enabled.assert_called_once_with("WLAN 2", False)
        self.assertNotIn("target_was_enabled", state)

    def test_windows_saves_disable_list_before_disabling_adapters(self):
        backend = hotspot.WindowsHotspotBackend()
        adapter = WifiAdapter(1, "WLAN 2", "USB WiFi", "Up", 2, "", True, ("2.4G",))
        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir)
            state_file = state_dir / "runtime_state.json"
            observed = {}

            def fail_after_check(names):
                observed.update(json.loads(state_file.read_text(encoding="utf-8")))
                raise HotspotError("模拟禁用中断")

            with patch.object(hotspot, "STATE_DIR", state_dir), \
                 patch.object(hotspot, "STATE_FILE", state_file), \
                 patch.object(backend, "stop_hotspot"), \
                 patch.object(backend, "_adapter_is_enabled", return_value=False), \
                 patch.object(backend, "set_adapter_enabled"), \
                 patch.object(backend, "_list_other_wifi", return_value=["WLAN"]), \
                 patch.object(backend, "_disable_wifi_adapters", side_effect=fail_after_check):
                with self.assertRaises(HotspotError):
                    backend.start_hotspot(
                        adapter, "Ethernet", "GMY1-2.4G", "12345678", "2.4G", True, lambda _: None
                    )
            self.assertEqual(observed["disabled_adapters"], ["WLAN"])
            self.assertFalse(observed["target_was_enabled"])

    def test_windows_old_pending_failure_does_not_block_new_start_attempt(self):
        backend = hotspot.WindowsHotspotBackend()
        adapter = WifiAdapter(1, "WLAN 3", "USB WiFi", "Up", 3, "", True, ("2.4G",))
        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir)
            state_file = state_dir / "runtime_state.json"
            with patch.object(hotspot, "STATE_DIR", state_dir), \
                 patch.object(hotspot, "STATE_FILE", state_file), \
                 patch.object(
                     backend, "stop_hotspot",
                     side_effect=[PendingRecoveryError("旧网卡缺失"), None],
                 ) as stop, \
                 patch.object(backend, "_adapter_is_enabled", return_value=True), \
                 patch.object(backend, "set_adapter_enabled") as set_enabled, \
                 patch.object(backend, "_set_band", return_value={"Applied": False}), \
                 patch.object(backend, "_start_modern_hotspot", side_effect=HotspotError("modern failed")), \
                 patch.object(hotspot, "run_netsh", return_value=(1, "模拟配置失败")):
                with self.assertRaises(HotspotError):
                    backend.start_hotspot(
                        adapter, "Ethernet", "GMY1-2.4G", "12345678", "2.4G", False, lambda _: None
                    )
            set_enabled.assert_called_once_with("WLAN 3", True)
            self.assertEqual(stop.call_count, 2)

    def test_windows_status_reports_pending_recovery(self):
        backend = hotspot.WindowsHotspotBackend()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state_file = root / "runtime_state.json"
            pending_file = root / "pending_recovery.json"
            pending_file.write_text('{"platform":"windows","adapter":"WLAN 2"}', encoding="utf-8")
            with patch.object(hotspot, "STATE_FILE", state_file), \
                 patch.object(hotspot, "DEFAULT_STATE_FILE", state_file), \
                 patch.object(hotspot, "LEGACY_STATE_FILE", root / "legacy.json"), \
                 patch.object(hotspot, "PENDING_STATE_FILE", pending_file), \
                 patch.object(hotspot, "run_netsh", return_value=(0, "Status : Not started")):
                status = backend.get_hotspot_status()
        self.assertTrue(status["pending_recovery"])
        self.assertEqual(status["pending_recovery_count"], 1)

    def test_english_supported_dual_band(self):
        text = """
        Hosted network supported  : Yes
        Number of supported bands : 2
          2.4 GHz
          5 GHz
        """
        self.assertEqual(parse_driver_capabilities(text), (True, ("2.4G", "5G")))

    def test_english_not_supported(self):
        self.assertEqual(parse_driver_capabilities("Hosted network supported : No"), (False, ()))

    def test_band_parser_prefers_explicit_5ghz_driver_report(self):
        text = """
        Radio types supported     : 802.11ac 802.11n 802.11a
        Number of supported bands : 1
                                    5 GHz [ 0 MHz - 0 MHz]
        """
        self.assertEqual(parse_driver_capabilities(text), (None, ("5G",)))

    def test_band_parser_uses_radio_type_as_fallback(self):
        text = "Radio types supported : 802.11ac 802.11n 802.11a"
        self.assertEqual(parse_driver_capabilities(text), (None, ("5G",)))

    def test_user_facing_status_text_is_chinese(self):
        self.assertEqual(localized_adapter_status("Disconnected"), "已启用（未连接）")
        self.assertEqual(localized_adapter_status("Disabled"), "已禁用")
        self.assertEqual(localized_tethering_status("InTransition"), "正在切换")
        self.assertEqual(localized_tethering_status("On (Windows 现代移动热点)"), "已启动 (Windows 现代移动热点)")
        self.assertEqual(localized_band("FiveGigahertz"), "5G")

    def test_chinese_hosted_network_result_is_line_scoped(self):
        text = "支持的承载网络  : 否\n支持 FIPS 模式  : 是"
        self.assertEqual(parse_driver_capabilities(text), (False, ()))

    def test_unknown(self):
        self.assertEqual(parse_driver_capabilities("unrelated output"), (None, ()))


if __name__ == "__main__":
    unittest.main()
