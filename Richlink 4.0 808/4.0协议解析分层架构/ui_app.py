import re
from datetime import timezone, timedelta
from PyQt5.QtWidgets import QFrame, QSpinBox, QMessageBox
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLineEdit, QDateTimeEdit, QPushButton,
    QLabel, QTextEdit, QComboBox, QCheckBox, QHBoxLayout, QGroupBox, QGridLayout
)
from PyQt5.QtCore import QDateTime, QTimer

from config import DATA_TYPE_OPTIONS, SUBTYPE_OPTIONS, CHECKBOX_GROUP_BY_SUBTYPE, PROCESS_HANDLER_BY_SELECTION
from parsers_common import *
from parsers_protocol import bind_parser_methods
from services_utils import export_to_excel as services_export_to_excel, server_get_data as services_server_get_data

class DataFetcherApp(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("4.0协议服务器数据批量解析 - Mangetic - 260617 ★★★★★ 广告位招租 ★★★★★")
        self.setGeometry(400, 300, 600, 600)

        self.imei_input = QLineEdit(self)
        self.imei_input.setPlaceholderText("Enter IMEI number(s), comma separated")

        self.start_time_input = QDateTimeEdit(self)
        self.start_time_input.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.start_time_input.setDateTime(QDateTime.currentDateTime())

        self.stop_time_input = QDateTimeEdit(self)
        self.stop_time_input.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.stop_time_input.setDateTime(QDateTime.currentDateTime())

        self.fetch_button = QPushButton("Fetch Data", self)
        self.fetch_button.clicked.connect(self.fetch_data)

        self.clear_button = QPushButton("Clear Output", self)
        self.clear_button.clicked.connect(self.clear_output)

        # 添加导出EXCEL按键
        self.export_button = QPushButton("导出为 Excel", self)
        self.export_button.clicked.connect(self.export_to_excel)

        self.dropdown1 = QComboBox(self)
        # self.dropdown1.addItems(["Select Type", "RAW DATA", "Trip data", "2 - Driving behavior", "3 - Location data",
        #                          "4 - Vehicle data", "5 - Secure data", "6 - Device state", "8 - Active server request",
        #                          "9 - Accessories information"])
        self.dropdown1.addItems(DATA_TYPE_OPTIONS)



        self.dropdown1.currentIndexChanged.connect(self.update_dropdown2)

        self.dropdown2 = QComboBox(self)
        self.dropdown2.addItem("Select Option")
        # 定义一个下拉的可选复选框
        self.dropdown2.currentIndexChanged.connect(self.update_checkbox_visibility)

        # 协议码显示框，只显示，不允许手动输入
        self.protocol_code_display = QLineEdit(self)
        self.protocol_code_display.setReadOnly(True)
        self.protocol_code_display.setFixedWidth(100)
        self.protocol_code_display.setPlaceholderText("协议")


        self.result_label = QLabel("Results will appear here.", self)
        self.result_label.setWordWrap(True)

        self.raw_data_display = QTextEdit(self)
        self.raw_data_display.setReadOnly(True)

        # 显示字段复选框
        self.checkbox_group = QGroupBox("显示字段")
        # 创建网格布局
        self.checkbox_layout = QGridLayout()
        self.checkbox_sets = {}

        # ════════════════════════════════════════════════════════
        #       第零章：复选框合集
        # ════════════════════════════════════════════════════════
        # connect 专用复选框
        connect_fields = {
            "imei":("IMEI",True),
            "time":("时间",True),
            "hardware_version":("硬件版本",True),
            "mcu_ap_version":("MCU/AP版本",True),
            "mdm_version":("MDM版本",True),
            "cfg_version":("配置版本",True),
            "support_status_fota":("支持状态FOTA",True),
            "ap_version":("AP版本",True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(connect_fields, "connect_{key}_checkbox")

        # disconnect专用复选框
        disconnect_fields = {
            "imei": ("IMEI", True),
            "time": ("时间", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(disconnect_fields, "disconnect_{key}_checkbox")


        # ════════════════════════════════════════════════════════
        #       第一章：复选框合集
        # ════════════════════════════════════════════════════════

        # trip summary 专用复选框
        trip_fields = {
            "imei": ("IMEI", True),
            "start_time": ("点火时间", True),
            "end_time": ("熄火时间", True),
            "source": ("统计来源", True),
            "mileage": ("行驶里程", True),
            "fuel_consumption": ("行程油耗", True),
            "max_speed": ("最高车速", True),
            "idle_time": ("怠速时间", True),
            "idle_fuel_consumption": ("怠速油耗", True),
            "num_of_acceleration": ("急加速次数", True),
            "num_of_deceleration": ("急减速次数", True),
            "num_of_sharp_turn": ("急转弯次数", True),
            "histor_total_mil": ("历史总里程", True),
            "histor_total_fuel": ("历史总油耗", True),
            "histor_total_driving_time": ("历史总行驶时间", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(trip_fields, "trip_{key}_checkbox")

        # 点熄火专用复选框
        eng_fields = {
            "imei": ("IMEI", True),
            "type": ("协议类型", True),
            "time": ("触发时间", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(eng_fields, "eng_{key}_checkbox")

        # 拖车功能专用复选框
        passive_trip_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(passive_trip_fields, "passive_trip_{key}_checkbox")

        # ════════════════════════════════════════════════════════
        #       第二章：复选框合集
        # ════════════════════════════════════════════════════════

        # 急加减速专用复选框
        sudden_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "before_speed": ("触发前车速", True),
            "after_speed": ("触发后车速", True),
            "value": ("触发值", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(sudden_fields, "sudden_{key}_checkbox")

        # 急转弯专用复选框
        sharp_turn_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "Turn": ("触发值", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(sharp_turn_fields, "sharp_turn_{key}_checkbox")

        # 怠速专用复选框
        exceed_idle_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(exceed_idle_fields, "exceed_idle_{key}_checkbox")

        # 疲劳驾驶专用复选框
        driving_tired_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(driving_tired_fields, "driving_tired_{key}_checkbox")

        # 超速专用复选框
        over_speed_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "value": ("触发值", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(over_speed_fields, "over_speed_{key}_checkbox")

        # 急变道专用复选框
        sudden_lane_change = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "value": ("触发值", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(sudden_lane_change, "sudden_lane_change_{key}_checkbox")

        # ════════════════════════════════════════════════════════
        #       第三章：复选框合集
        # ════════════════════════════════════════════════════════

        # GPS专用复选框
        gps_location_data_fields = {
            "imei": ("IMEI", True),
            "num": ("GPS数", True),
            "time": ("GPS时间", True),
            "source": ("位置源", True),
            "validity": ("有效性", True),
            "longitude": ("经度", True),
            "latitude": ("纬度", True),
            "sate_num": ("卫星数", True),
            "height": ("高度", True),
            "longitude_value": ("经度值", True),
            "latitude_value": ("纬度值", True),
            "gps_speed": ("GPS速度", True),
            "heading": ("航向角", True),
            "pdop": ("PDOP", True),
            "hdop": ("HDOP", True),
            "vdop": ("VDOP", True),
            "hacc": ("HACC", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(gps_location_data_fields, "gps_location_data_{key}_checkbox")

        # LBS 专用复选框
        lbs_location_data_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "mcc_mnc": ("PLMN", True),
            "radio_type": ("类型", True),
            "carrier_name": ("运营商", True),
            "consider_ip": ("参考IP", True),
            # "cell_num": ("小区个数", True),
            "cell_list": ("小区列表", True),
            # "wifi_num": ("WIFI列表", True),
            "wifi_list": ("WIFI列表", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(lbs_location_data_fields, "lbs_location_data_{key}_checkbox")

        # ════════════════════════════════════════════════════════
        #       第四章：复选框合集
        # ════════════════════════════════════════════════════════

        # VIN码专用复选框
        vin_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "type": ("协议类型", True),
            "length": ("VIN长度", True),
            "vin_value": ("VIN码", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(vin_fields, "vin_{key}_checkbox")

        # 数据流专用复选框
        dataflow_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "rpm": ("转速", True),
            "speed": ("车速", True),
            "engine_coolant_temperature": ("发动机冷却液温度 - A", True),
            "throttle_position": ("节气门位置 - B", True),
            "engine_duty": ("发动机负荷 - C", True),
            "intake_air_flow": ("进气流量 - D", True),
            "intake_air_temperature": ("进气温度 - E", True),
            "intake_air_pressure": ("进气压力 - F", True),
            "battery_voltage": ("电池电压 - G", True),
            "fuel_level": ("油量 - H", True),
            "distance_dtcs_cleared": ("DTC清除后距离 - I", True),
            "distance_mil": ("故障灯点亮后距离 - J", True),
            "historical_total_mileage": ("历史总里程 - K1", True),
            "historical_total_fuel_consumption": ("历史总油耗 - K2", True),
            "historical_total_driving_time": ("历史总行驶时间 - K3", True),
            "seatbelt_status": ("安全带状态 - L", True),
            "odometer": ("里程表- M", True),
            "average_fuel_consumption": ("平均油耗 - N", True),
            "odometer_unit": ("里程单位 - O", True),
            "soc": ("SOC - P", True),
            "soh": ("SOH - Q", True),
            "battery_pack_current": ("电池电流 - R", True),
            "battery_pack_voltage": ("电池电压 - S", True),
            "battery_pack_charging": ("充电状态 - T", True),
            "remaining_distance": ("剩余里程 - U", True),
            "battery_pack_temperature": ("电池包温度 - V", True),
            "distance_till_next_servicing": ("下次保养里程 - W", True),
            "engine_run_time": ("发动机运行时间 - X", True),
            "fuel_type": ("油品类型 - Y", True),
            "turn_signals_status": ("转向灯状态 - Z", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(dataflow_fields, "dataflow_{key}_checkbox")

        # can 支持参数状态专用复选框
        can_parameter_support_status_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "vin": ("vin", True),
            "gasoline_ev": ("gasoline_ev", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(can_parameter_support_status_fields, "can_parameter_support_status_{key}_checkbox")

        # 原始CAN消息帧
        raw_can_frame_fields = {
            "imei": ("IMEI", True),
            "time": ("IMEI", True),
            "canbuspins": ("canbuspins", True),
            "num_canframe": ("num", True),
            "canframeid_raw": ("canframeid_raw", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(raw_can_frame_fields, "raw_can_frame_{key}_checkbox")

        # config 数据流专用复选框
        config_dataflow_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "klv": ("数据流", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(config_dataflow_fields, "config_dataflow_{key}_checkbox")

        # 动态数据流 KLV
        vehicle_Information_klv_fields = {
            "imei": ("IMEI", True),
            # "time": ("触发时间", True),
            "klv_data": ("消息内容", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(vehicle_Information_klv_fields, "vehicle_Information_klv_{key}_checkbox")

        # ════════════════════════════════════════════════════════
        #       第五章：复选框合集
        # ════════════════════════════════════════════════════════

        # DTC码专用复选框
        dtc_code_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "obd_dtc_num": ("DTC个数", True),
            "obd_dtc_data": ("DTC码", True),
            "private_code_num": ("私有DTC个数", False),
            "private_code_data": ("私有DTC", False),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(dtc_code_fields, "dtc_code_{key}_checkbox")

        # 低电压专用复选框
        battery_low_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "battery_voltage": ("电压", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(battery_low_fields, "battery_low_{key}_checkbox")

        # 震动事件专用复选框
        vibration_event_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "vibration_value": ("震动值", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(vibration_event_fields, "vibration_event_{key}_checkbox")

        # 疑似碰撞专用复选框
        suspected_collision_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "collision_value": ("碰撞值", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(suspected_collision_fields, "suspected_collision_{key}_checkbox")

        # 拔出告警专用复选框
        unplug_warning_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "unplug_state": ("拔出状态", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(unplug_warning_fields, "unplug_warning_{key}_checkbox")

        # 干扰检测专用复选框
        jamming_detection_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "jamming_status": ("干扰状态", True),
            "jamming_type": ("干扰类型", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(jamming_detection_fields, "jamming_detection_{key}_checkbox")

        # 设备防拆告警
        device_tamper_warning_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(device_tamper_warning_fields, "device_tamper_warning_{key}_checkbox")

        # 温度告警
        temperature_warning_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "temperature_value": ("温度值", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(temperature_warning_fields, "temperature_warning_{key}_checkbox")

        # Humidity warning
        humidity_warning_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "humidity_value": ("湿度值", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(humidity_warning_fields, "humidity_warning_{key}_checkbox")

        # 气压告警
        air_pressure_warning_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(air_pressure_warning_fields, "air_pressure_warning_{key}_checkbox")

        # 冲击告警
        shock_warning_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "num": ("NUM", True),
            "sensor_data": ("冲击值", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(shock_warning_fields, "shock_warning_{key}_checkbox")

        # 设备告警信息
        device_warning_message_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "klv_data": ("告警信息", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(device_warning_message_fields, "device_warning_message_{key}_checkbox")

        # 电子围栏告警 5.15 - Fence warning
        fence_warning_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "id": ("ID", True),
            "type": ("Type", True),
            "location": ("Location", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(fence_warning_fields, "fence_warning_{key}_checkbox")

        # ════════════════════════════════════════════════════════
        #       第六章：复选框合集
        # ════════════════════════════════════════════════════════

        # 休眠状态专用复选框
        sleep_state_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "sleep_voltage": ("电压", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(sleep_state_fields, "sleep_state_{key}_checkbox")

        # 唤醒状态专用复选框
        wakeup_state_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "wakeup_voltage": ("电压", True),
            "wakeup_type": ("唤醒类型", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(wakeup_state_fields, "wakeup_state_{key}_checkbox")

        # 长时间无法定位专用复选框
        gps_not_fix_fielad = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(gps_not_fix_fielad, "gps_not_fix_{key}_checkbox")

        # 重启事件专用复选框
        reboot_event_fields = {
            "imei": ("IMEI", True),
            "power_on_time": ("上电时间", True),
            "power_off_time": ("断电时间", True),
            "reboot_reason": ("重启原因", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(reboot_event_fields, "reboot_event_{key}_checkbox")

        # MCU升级状态专用复选框
        mcu_upgrade_state_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "upgrade_state": ("升级状态", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(mcu_upgrade_state_fields, "mcu_upgrade_state_{key}_checkbox")
            
        # SMS专用复选框
        sms_fields = {
            "imei": ("IMEI", True),
            "utc_time": ("触发时间", True),
            "sms_time": ("短信时间", True),
            "phone_num": ("电话号码", True),
            "encoding": ("编码格式", True),
            "message": ("消息", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(sms_fields, "sms_{key}_checkbox")

        # 设备信息专用复选框
        device_info_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            # "length_of_phone_number": ("手机号长度", True),
            "phone_number": ("手机号", True),
            # "length_of_iccid": ("ICCID长度", True),
            "iccid": ("ICCID", True),
            # "length_of_imsi": ("IMSI长度", True),
            "imsi": ("IMSI", True),
            # "length_of_wifi_mac": ("WiFi MAC长度", True),
            "wifi_mac": ("WiFi MAC", True),
            # "length_of_bt_mac": ("蓝牙MAC长度", True),
            "bt_mac": ("蓝牙MAC", True),
            # "length_of_wifi_mac_5g": ("5G WiFi MAC长度", True),
            "wifi_mac_5g": ("5G WiFi MAC", True),
            "softerware_ble_version": ("BLE版本", True),
            "softerware_gnss_version": ("GNSS版本", True),
            "softerware_boot_version": ("BOOT版本", True),
            "softerware_ap_version": ("AP版本", True),
            "mcc": ("MCC", True),
            # "length_of_mnc": ("MNC长度", True),
            "mnc": ("MNC", True),
            "cfg_file_version": ("配置版本", True),
            "gl103_workmode": ("GL103模式", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(device_info_fields, "device_info_{key}_checkbox")

        # sensor_normal事件专用复选框
        sensor_normal_fields = {
            "imei": ("IMEI", True),
            "time": ("上报时间", True),
            "time_interval": ("时间间隔", True),
            "sensor_status": ("sensor状态", True),
            "number": ("sensor数量", True),
            "x_axis": ("X轴", True),
            "y_axis": ("Y轴", True),
            "z_axis": ("Z轴", True),
            "rpm": ("转速", True),
            "speed": ("车速", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(sensor_normal_fields, "sensor_normal_{key}_checkbox")

        # sensor_event 事件专用复选框
        sensor_event_fields = {
            "imei": ("IMEI", True),
            "time": ("上报时间", True),
            "happen_time": ("发生时间", True),
            "event_time": ("事件时间", True),
            "collection_time": ("采集时间", True),
            "collection_time_ms": ("采集时间(ms)", True),
            "time_interval": ("时间间隔", True),
            "event_type": ("事件类型", True),
            "sensor_state": ("sensor状态", True),
            "sensor_num": ("sensor数量", True),
            "x_axis": ("X轴", True),
            "y_axis": ("Y轴", True),
            "z_axis": ("Z轴", True),
            "rpm": ("转速", True),
            "speed": ("车速", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(sensor_event_fields, "sensor_event_{key}_checkbox")

        # 继电器控制状态专用复选框
        relay_control_status_fields = {
            "imei": ("IMEI", True),
            "time": ("上报时间", True),
            "relay_control_status": ("控制状态", True),
            "event_trigger_reason": ("原因", True),
            "ibutton_id": ("iButton ID", True),
            "rfid_id": ("RFID ID", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(relay_control_status_fields, "relay_control_status_{key}_checkbox")

        # 自学习专用复选框
        self_learning_status_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "calibration_status": ("学习状态", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(self_learning_status_fields, "self_learning_status_{key}_checkbox")

        # 博世碰撞专用复选框
        bosch_collision_fields = {
            "imei": ("IMEI", True),
            "report_time": ("触发时间", True),
            "event_time": ("事件时间", True),
            "crash_index": ("碰撞指数", True),
            "crash_status": ("碰撞状态", True),
            "crash_event_counter": ("事件计数器", True),
            "crash_frame_counter": ("事件结构", True),
            "error_status": ("错误状态", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(bosch_collision_fields, "bosch_crash_{key}_checkbox")


        # ════════════════════════════════════════════════════════
        #       第七章：复选框合集
        # ════════════════════════════════════════════════════════

        # 请求MCU更新包（TCP）专用复选框
        request_mcu_update_package_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "file_name_length": ("长度", True),
            "file_name": ("文件名", True),
            "staring_position": ("起始位置", True),
            "request_length_bytes": ("数据长度", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(request_mcu_update_package_fields, "request_mcu_update_package_tcp_{key}_checkbox")

    # 请求AGPS专用复选框
        request_agps_data_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "longitude": ("经度", True),
            "longitude_value": ("经度数值", True),
            "latitude": ("纬度", True),
            "latitude_value": ("纬度数值", True),
            "ages_service_type": ("服务器类型", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(request_agps_data_fields, "request_agps_data_{key}_checkbox")

    # MCU更新包验证（TCP）专用复选框
        mcu_update_package_validation_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "file_name_length": ("长度", True),
            "file_name": ("文件名称", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(mcu_update_package_validation_fields, "mcu_update_package_verification_tcp_{key}_checkbox")

    # MCU日志上报 专用复选框
        mcu_log_report_fields = {
            "imei": ("IMEI", True),
            "log_type": ("日志类型", True),
            "log_id": ("日志ID", True),
            "offset": ("日志偏移", True),
            "logdata": ("日志数据", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(mcu_log_report_fields, "mcu_log_report_{key}_checkbox")

    # 检查新的更新包（路由器） 专用复选框
        check_new_update_package_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "mdm_version": ("MDM版本", True),
            "ap_version": ("AP版本", True),
            "cfg_version": ("CFG版本", True),
            "request_type": ("请求类型", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(check_new_update_package_fields, "check_new_update_package_router_{key}_checkbox")

    #  对新更新包的响应（适用于路由器) 专用复选框
        response_new_update_package_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "fota_task_id": ("任务ID", True),
            "response_fota_task": ("响应结果", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(response_new_update_package_fields, "response_to_new_update_package_router_{key}_checkbox")

        # ════════════════════════════════════════════════════════
        #       第八章：复选框合集
        # ════════════════════════════════════════════════════════

        # 设置参数专用复选框
        set_parameters_fields = {
            "imei": ("IMEI", True),
            "set_result": ("设置结果", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(set_parameters_fields, "set_parameters_{key}_checkbox")

        # 参数查询专用复选框
        inquiry_parameters_fields = {
            "imei": ("IMEI", True),
            "inquiry_result": ("查询结果", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(inquiry_parameters_fields, "inquiry_parameters_{key}_checkbox")

        # 白名单配置响应专用复选框
        whitelist_management_fields = {
            "imei": ("IMEI", True),
            "operation_result": ("操作结果", True),
            "type": ("类型", True),
            "num_of_ids": ("已有ID数量", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(whitelist_management_fields, "whitelist_management_{key}_checkbox")

        # 配件白名单查询-RFID-IBUTTON
        whitelist_query_fields = {
            "imei": ("IMEI", True),
            "type": ("类型", True),
            "length_id": ("ID长度", True),
            "multi_frame_flag": ("消息帧数", True),
            "current_response_message": ("消息索引", True),
            "number_of_ids": ("ID数量", True),
            "ids": ("ID列表", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(whitelist_query_fields, "whitelist_query_{key}_checkbox")

        # 电子围栏 响应 8.11.2
        message_fence_device_response_fields = {
            "imei": ("IMEI", True),
            "operation_result": ("操作结果", True),
            "num": ("围栏个数", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(message_fence_device_response_fields, "message_fence_device_response_{key}_checkbox")

        # 电子围栏 查询
        query_fence_to_device_fields = {
            "imei": ("IMEI", True),
            "total_num": ("围栏总数", True),
            "start_id": ("开始ID", True),
            "message_num": ("消息数", True),
            "fence_data": ("围栏消息", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(query_fence_to_device_fields, "query_fence_to_device_{key}_checkbox")

        # ════════════════════════════════════════════════════════
        #       第九章：复选框合集
        # ════════════════════════════════════════════════════════

        # ibutton 上报
        ibutton_id_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "ibutton_id": ("iButton ID", True),
            "authentication_status": ("身份验证状态", True),
            "gps_data": ("GPS数据", False),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(ibutton_id_fields, "ibutton_id_{key}_checkbox")

        # 胎压上报
        ble_sensor_data_fields = {
            "imei": ("IMEI", True),
            "time": ("上报时间", True),
            "front_left_pressure": ("左前胎压", True),
            "front_right_pressure": ("右前胎压", True),
            "rear_left_pressure": ("左后胎压", True),
            "rear_right_pressure": ("右后胎压", True),
            "front_left_temperature": ("左前胎温", True),
            "front_right_temperature": ("右前胎温", True),
            "rear_left_temperature": ("左后胎温", True),
            "rear_right_temperature": ("右后胎温", True),
            "front_left_battery": ("左前电池", True),
            "front_right_battery": ("右前电池", True),
            "rear_left_battery": ("左后电池", True),
            "rear_right_battery": ("右后电池", True),
            "tire_status_of_tire": ("胎压状态", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(ble_sensor_data_fields, "ble_sensor_data_{key}_checkbox")

        # 胎压告警
        ble_sensor_warning_fields = {
            "imei": ("IMEI", True),
            "time": ("上报时间", True),
            "warning_type": ("告警类型", True),
            "warning_position": ("告警位置", True),
            "warning_pressure": ("告警胎压", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(ble_sensor_warning_fields, "ble_sensor_warning_{key}_checkbox")

        # 温湿度传感器
        rs485_temperature_humidity_fields = {
            "imei": ("IMEI", True),
            "num": ("传感器数量", True),
            "time": ("上报时间", True),
            "temperature": ("温度", True),
            "humidity": ("湿度", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(rs485_temperature_humidity_fields, "rs485_temperature_humidity_{key}_checkbox")

        # RFID数据上报
        rfid_data_fields = {
            "imei": ("IMEI", True),
            "time": ("上报时间", True),
            "rfid_id": ("RFID ID", True),
            "authentication_status": ("身份验证状态", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(rfid_data_fields, "rfid_data_{key}_checkbox")

        # BLE TAG 数据上报
        ble_tag_data_fields = {
            "imei": ("IMEI", True),
            "tag_num": ("标签数量", True),
            "UUID": ("UUID", True),
            "major": ("Major", True),
            "minor": ("Minor", True),
            "RSSI": ("RSSI", True),
            "battery": ("电池电量", True),
            "anti_tamper_status": ("防拆状态", True),
            "asensor_status": ("传感器状态", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(ble_tag_data_fields, "ble_tag_data_{key}_checkbox")







        # EXCEL按键
        # 把导出EXCEL 这个按键添加到checkbox 这个布局中
        self.checkbox_layout.addWidget(self.export_button)

        # 把上面这个布局（包含按钮和其他控件）设置为复选框组 self.checkbox_group 的内部布局。
        self.checkbox_group.setLayout(self.checkbox_layout)
        # 设置复选框组的可见性为 False，初始时不显示
        self.checkbox_group.setVisible(False)
        # 创建一个新的垂直布局对象 layout，用于后续把整个窗口的控件按垂直顺序排列
        layout = QVBoxLayout()

        # IMEI 输入框单独一行
        imei_layout = QHBoxLayout()
        imei_layout.addWidget(QLabel("IMEI Number(s):"))
        imei_layout.addWidget(self.imei_input)
        layout.addLayout(imei_layout)

        # 添加 "Auto EX" 按钮
        self.auto_timer = QTimer(self)
        self.auto_timer.setInterval(5000)  # 5秒
        self.auto_timer_running = False  # 标志位
        # 新增：记录自动启动时刻，用于判断是否满1小时
        self.auto_timer.timeout.connect(self.auto_execute)
        self.auto_timer.timeout.connect(self.auto_execute)

        # 时间选择框：Start Time 和 Stop Time 一行
        time_layout = QHBoxLayout()
        time_layout.addWidget(QLabel("Start Time:"))
        time_layout.addWidget(self.start_time_input)
        time_layout.addWidget(QLabel("Stop Time:"))
        time_layout.addWidget(self.stop_time_input)

        # 添加 "Real Time" 按钮
        real_time_button = QPushButton("Real Time")
        real_time_button.clicked.connect(self.update_stop_time_to_now)
        time_layout.addWidget(real_time_button)

        # Auto EX 按钮
        self.auto_ex_button = QPushButton("Auto EX")
        self.auto_ex_button.clicked.connect(self.toggle_auto_execution)
        time_layout.addWidget(self.auto_ex_button)

        layout.addLayout(time_layout)

        # 定义按钮点击事件的槽函数
        def update_stop_time_to_current(self):
            self.stop_time_input.setDateTime(QDateTime.currentDateTime())

        # # 数据类型选择框：Select Data Type 和 Select Subtype 一行
        # data_layout = QHBoxLayout()
        # data_layout.addWidget(QLabel("Select Data Type:"))
        # data_layout.addWidget(self.dropdown1)
        # data_layout.addWidget(QLabel("Select Subtype:"))
        # data_layout.addWidget(self.dropdown2)
        # layout.addLayout(data_layout)

        # 自定义 宽度
        data_layout = QHBoxLayout()

        # 最后加一个 stretch，防止布局被拉伸
        # 全部左对齐：addStretch() 放最后
        # 全部右对齐：addStretch() 放最前
        data_layout.addStretch()

        # ========== 全部左对齐：标签1 + 下拉框1 ==========
        type_label = QLabel("Select Data Type:")
        type_label.setFixedWidth(130)
        data_layout.addWidget(type_label)

        self.dropdown1.setFixedWidth(220)
        self.dropdown1.setFixedHeight(28)
        data_layout.addWidget(self.dropdown1)

        # ========== 标签2 + 下拉框2 也靠左 ==========
        subtype_label = QLabel("Select Subtype:")
        subtype_label.setFixedWidth(110)
        data_layout.addWidget(subtype_label)

        self.dropdown2.setFixedWidth(250)
        self.dropdown2.setFixedHeight(28)
        data_layout.addWidget(self.dropdown2)

        # 在 Select Subtype 右侧增加协议码显示框
        code_label = QLabel("Code:")
        code_label.setFixedWidth(45)
        data_layout.addWidget(code_label)

        data_layout.addWidget(self.protocol_code_display)



        layout.addLayout(data_layout)

        # 显示字段复选框
        layout.addWidget(self.checkbox_group)

        # 按钮行
        action_layout = QHBoxLayout()
        action_layout.addWidget(self.fetch_button)
        action_layout.addWidget(self.clear_button)
        layout.addLayout(action_layout)

        # 结果显示
        layout.addWidget(self.result_label)
        layout.addWidget(QLabel("Output:"))
        layout.addWidget(self.raw_data_display)

        # ===== 主布局：左侧原功能 + 右侧展开按钮 + 隐藏工具栏 =====
        main_layout = QHBoxLayout()

        # 左侧原来的主界面
        main_layout.addLayout(layout, 4)

        # 右侧展开/收起按钮
        # self.command_panel_toggle_btn = QPushButton("展开\n发送\n工具")
        self.command_panel_toggle_btn = QPushButton("协\n议\n下\n发\n查\n询\n工\n具")
        self.command_panel_toggle_btn.setFixedWidth(25)
        self.command_panel_toggle_btn.clicked.connect(self.toggle_command_panel)
        main_layout.addWidget(self.command_panel_toggle_btn)

        # 右侧发送工具栏，默认隐藏
        self.command_panel = self.create_command_panel()
        self.command_panel.setVisible(False)
        main_layout.addWidget(self.command_panel, 1)

        self.setLayout(main_layout)
    def _create_checkboxes(self, fields, attr_template):
        group_name = attr_template.split("{key}", 1)[0].rstrip("_")
        widgets = []
        for key, (label, checked) in fields.items():
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, attr_template.format(key=key), checkbox)
            widgets.append(checkbox)
        self.checkbox_sets[group_name] = widgets

    def _clear_checkbox_layout(self):
        while self.checkbox_layout.count():
            item = self.checkbox_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)

    def _add_checkbox_group(self, group_name, max_columns=4):
        widgets = self.checkbox_sets.get(group_name, [])
        for index, checkbox in enumerate(widgets):
            row = index // max_columns
            col = index % max_columns
            self.checkbox_layout.addWidget(checkbox, row, col)
        return (len(widgets) + max_columns - 1) // max_columns

    def _auto_parse_str(self):
        raw_txt = self.parse_input.toPlainText()
        txt = re.sub(r'\s+', '', raw_txt)

        # txt = self.parse_input.toPlainText().strip()
        if len(txt) < 48:
            self.parse_result.setText("长度不足48位")
            return
        # 你要的核心：截取 18~48
        slice_str = txt[18:48]
        res = ascii_to_decimal(slice_str)
        self.parse_result.setText(str(res))

    # 更新结束时间代码
    def update_stop_time_to_now(self):
        current_time = QDateTime.currentDateTime()
        self.stop_time_input.setDateTime(current_time)

    # 实现自动更新时间执行获取数据
    def auto_execute(self):
        # 先判断是否运行满1小时（3600秒）
        if self.auto_start_datetime is not None:
            now = QDateTime.currentDateTime()
            # 计算已运行总秒数
            run_seconds = self.auto_start_datetime.secsTo(now)
            if run_seconds >= 3600:
            # if run_seconds >= 20:
                # 达到一小时，自动停止
                self.auto_timer.stop()
                self.auto_timer_running = False
                self.auto_start_datetime = None
                self.auto_ex_button.setText("Auto EX")
                # 一小时到了弹出提示框
                QMessageBox.information(self, "提示", "Auto EX已自动运行满1小时，已停止")
                return  # 直接退出，不再执行本次数据获取逻辑

        # 正常未超时，执行原有业务逻辑
        self.update_stop_time_to_now()
        self.fetch_data()

    def update_protocol_code_display(self):
        """
        根据当前选择的二级菜单，显示对应的协议码
        """
        sub_type = self.dropdown2.currentText()

        protocol_code_map = {

            # ════════════════ 第0章 ════════════════
            # "Connect": "00 01",
            # "Disconnect": "00 01",

            # ════════════════ 第1章 Trip data ════════════════
            "1.1 - trip summary": "00 00",
            "1.2 - Ignition on": "00 01",
            "1.3 - Ignition off": "00 02",
            "1.4 - trip start": "00 03",
            "1.5 - trip end": "00 04",

            # ════════════════ 第2章 Driving behavior ════════════════
            "2.1 - Sudden acc": "01 00",
            "2.2 - Sudden dec": "01 01",
            "2.3 - Sharp turn": "01 02",
            "2.4 - Exceed idle": "01 03",
            "2.5 - Driving tired": "01 04",
            "2.6 - Over speed": "01 05",
            "2.7 - Sudden Lane Change": "01 07",

            # ════════════════ 第3章 Location data ════════════════
            "3.1 - GPS data": "02 00",
            "3.2 - LBS data": "02 01",

            # ════════════════ 第4章 Vehicle data ════════════════
            "4.1 - VIN Cold": "03 00",
            "4.2 - Data flow": "03 01",
            "4.3 - CAN parameter support status": "03 04",
            "4.4 - Raw can frame": "03 05",
            "4.5 - Config data flow": "03 06",
            "4.6 - Vehicle Information KLV": "03 07",

            # ════════════════ 第5章 Secure data ════════════════
            "5.1 - DTC code": "05 00",
            "5.2 - Battery low": "05 01",
            "5.3 - Vibration event": "05 02",
            "5.4 - Suspected collision": "05 05",
            "5.5 - Unplug warning": "05 07",
            "5.6 - Jamming detection": "05 0B",
            "5.7 - Device tamper warning": "05 0C",
            "5.8 - Temperature warning": "05 0D",
            "5.9 - Air pressure warning": "05 0E",
            "5.10 - Shock warning": "05 0F",
            "5.12 - Humidity warning": "05 11",
            "5.13 - Device warning message": "05 12",
            "5.15 - Fence warning": "05 13",

            # ════════════════ 第6章 Device state ════════════════
            "6.1 - Sleep state": "04 02",
            "6.2 - Wakeup state": "04 03",
            "6.3 - GPS not fix": "04 04",
            "6.4 - Reboot event": "04 05",
            "6.5 - Mcu upgrade state": "04 06",
            "6.6 - SMS": "04 0B",
            "6.7 - Device info": "04 0C",
            "6.8 - Sensor normal": "04 0D",
            "6.9 - Sensor event": "04 0E",
            "6.11 - Relay control status": "04 14",
            "6.12 - Self learning status": "04 07",
            "Bosch crash data": "",

            # ════════════════ 第7章 Device request message ════════════════
            "7.1 -Request MCU update package(TCP)": "F0 01",
            "7.2 - Request AGPS data": "F0 02",
            "7.3 - MCU Update package verification(TCP)": "F0 03",
            "7.4 - MCU Log Report": "F0 04",
            "7.5 - Check new update package(Router)-暂不开发": "F0 05",
            "7.6 - Response to the New Update Package(Router)-暂不开发": "F0 06",

            # ════════════════ 第8章 Active server request ════════════════
            "8.2 - Set parameters": "F1 02",
            "8.3 - Inquiry parameters": "F1 03",
            "8.8 - whitelist management": "F1 0C",
            "8.9 - whitelist query": "F1 0D",
            "8.11.2 - Management fence device response": "F1 0F",
            "8.12.2 - Query fence device response": "F1 10",

            # ════════════════ 第9章 Accessories information ════════════════
            "9.1 - Ibutton id": "06 01",
            "9.2 - Ble sensor data": "06 02",
            "9.3 - Rs485 temperature humidity": "06 03",
            "9.4 - Ble sensor warning": "06 04",
            "9.5 - Rfid data": "06 05",
            "9.7 - Ble tag": "06 07",
        }

        code = protocol_code_map.get(sub_type, "")
        self.protocol_code_display.setText(code)

    def toggle_auto_execution(self):
        if self.auto_timer_running:
            # 正在运行 → 手动停止
            self.auto_timer.stop()
            self.auto_timer_running = False
            self.auto_start_datetime = None  # 清空计时起点
            self.auto_ex_button.setText("Auto EX")
        else:
            # 未运行 → 开启自动执行，记录启动时间
            self.auto_start_datetime = QDateTime.currentDateTime()
            self.auto_timer.start()
            self.auto_timer_running = True
            self.auto_ex_button.setText("Stop Auto EX")

    # 导出EXCEL函数
    # def export_to_excel(self):
    #     text = self.raw_data_display.toPlainText()
    #     if not text.strip():
    #         self.result_label.setText("没有数据可导出")
    #         return
    #
    #     # 分行解析
    #     lines = text.strip().split('\n')
    #     if not lines or len(lines) < 2:
    #         self.result_label.setText("数据不足，无法导出")
    #         return
    #
    #     # 第一行为表头，其他为数据
    #     print("1111")
    #     headers = re.split(r'\s{2,}', lines[0].strip())  # 多个空格分隔
    #     print("2222")
    #     data_rows = [re.split(r'\s{2,}', line.strip()) for line in lines[1:]]
    #     print("666666")
    #
    #     clean_data_rows = [row for row in data_rows if len(row) == len(headers)]
    #     df = pd.DataFrame(clean_data_rows, columns=headers)
    #     # df = pd.DataFrame(data_rows, columns=headers)
    #     print("777777")
    #
    #     # 弹出保存文件对话框
    #     print("33333")
    #     file_path, _ = QFileDialog.getSaveFileName(self, "保存 Excel 文件", "", "Excel 文件 (*.xlsx)")
    #     print("444444")
    #     if file_path:
    #         try:
    #             df.to_excel(file_path, index=False)
    #             self.result_label.setText(f"导出成功: {file_path}")
    #         except Exception as e:
    #             self.result_label.setText(f"导出失败: {str(e)}")
    # 导出EXCEL函数-新
    def export_to_excel(self):
        return services_export_to_excel(self)

    def update_dropdown2(self):
        selected = self.dropdown1.currentText()
        self.dropdown2.clear()
        self.dropdown2.addItems(SUBTYPE_OPTIONS.get(selected, ["Select Option"]))

    def update_checkbox_visibility(self):
        sub_type = self.dropdown2.currentText()

        self.update_protocol_code_display()
        self.checkbox_group.setVisible(True)
        self._clear_checkbox_layout()

        group_name = CHECKBOX_GROUP_BY_SUBTYPE.get(sub_type)
        next_row = 0
        if group_name:
            next_row = self._add_checkbox_group(group_name)

        self.checkbox_layout.addWidget(self.export_button, next_row, 0, 1, 4)

    def fetch_data(self):
        data_type = self.dropdown1.currentText()
        sub_type = self.dropdown2.currentText()

        if data_type not in SUBTYPE_OPTIONS:
            self.result_label.setText("Please select a valid data type.")
            return

        imei_num_list = [self.clean_imei(imei.strip()) for imei in self.imei_input.text().split(",")]
        imei_num_list = [imei for imei in imei_num_list if imei]

        start_dt = self.start_time_input.dateTime().toPyDateTime() - timedelta(hours=8)
        stop_dt = self.stop_time_input.dateTime().toPyDateTime() - timedelta(hours=8)

        start_timestamp = int(start_dt.replace(tzinfo=timezone.utc).timestamp() * 1000)
        stop_timestamp = int(stop_dt.replace(tzinfo=timezone.utc).timestamp() * 1000)

        raw_data = self.server_get_data(imei_num_list, start_timestamp, stop_timestamp)
        handler_name = PROCESS_HANDLER_BY_SELECTION.get((data_type, sub_type))
        if handler_name:
            getattr(self, handler_name)(raw_data)

    def clean_imei(self, imei):
        return re.sub(r'[^0-9]+$', '', imei)

    def server_get_data(self, imei_num_list, start_timestamp, stop_timestamp):
        return services_server_get_data(self, imei_num_list, start_timestamp, stop_timestamp)

    def clear_output(self):
        self.raw_data_display.clear()
        self.result_label.setText("Results will appear here.")

    # 以前内容全部是 右侧发送命令栏的窗口  =======================================
    def create_command_panel(self):
        """
        创建右侧参数下发/查询工具栏
        """
        panel = QFrame(self)
        panel.setFrameShape(QFrame.StyledPanel)
        panel.setFixedWidth(420)

        panel_layout = QVBoxLayout(panel)

        title = QLabel("参数下发 / 查询工具")
        panel_layout.addWidget(title)

        # IMEI 输入
        self.cmd_imei_input = QLineEdit()
        self.cmd_imei_input.setPlaceholderText("例如：864114070683622,864114070683623")
        panel_layout.addWidget(self.cmd_imei_input)

        # 命令输入区域
        self.cmd_rows_layout = QVBoxLayout()
        panel_layout.addLayout(self.cmd_rows_layout)

        self.cmd_rows = []
        self.add_cmd_row()

        add_cmd_btn = QPushButton("增加命令行")
        add_cmd_btn.clicked.connect(self.add_cmd_row)
        panel_layout.addWidget(add_cmd_btn)

        # 每条命令间隔
        interval_layout = QHBoxLayout()
        interval_layout.addWidget(QLabel("每条间隔(秒)："))
        self.auto_send_interval = QSpinBox()
        self.auto_send_interval.setRange(1, 3600)
        self.auto_send_interval.setValue(1)
        self.auto_send_interval.setFixedWidth(80)
        interval_layout.addWidget(self.auto_send_interval)
        panel_layout.addLayout(interval_layout)

        # 循环次数
        loop_layout = QHBoxLayout()
        loop_layout.addWidget(QLabel("循环次数："))
        self.auto_send_loop_count = QSpinBox()
        self.auto_send_loop_count.setRange(1, 9999)
        self.auto_send_loop_count.setValue(1)
        self.auto_send_loop_count.setFixedWidth(80)
        loop_layout.addWidget(self.auto_send_loop_count)
        panel_layout.addLayout(loop_layout)

        # 自动发送按钮
        self.auto_send_btn = QPushButton("开始自动发送")
        self.auto_send_btn.clicked.connect(self.toggle_auto_send_cmd)
        panel_layout.addWidget(self.auto_send_btn)

        # 状态与定时器
        self.cmd_auto_running = False
        self.auto_cmd_queue = []
        self.auto_cmd_index = 0
        self.auto_current_loop = 1
        self.auto_total_loop = 1
        self.auto_imei_list = []
        self.cmd_auto_timer = QTimer(self)
        self.cmd_auto_timer.timeout.connect(self.send_next_cmd)

        # ========== 底部字符串解析区 无按钮，输入实时解析 ==========
        parse_group = QGroupBox("ASCII截取解析 [18:48]")
        parse_layout = QVBoxLayout()

        # 粘贴输入框
        self.parse_input = QTextEdit()
        self.parse_input.setPlaceholderText("粘贴原始字符串，自动截取18~48位转为十进制")
        self.parse_input.setMaximumHeight(80)
        # 内容变化自动执行解析，不用单独函数
        self.parse_input.textChanged.connect(self._auto_parse_str)

        # 解析结果显示
        self.parse_result = QLineEdit()
        self.parse_result.setPlaceholderText("解析结果")
        self.parse_result.setReadOnly(True)

        parse_layout.addWidget(QLabel("原始报文："))
        parse_layout.addWidget(self.parse_input)
        parse_layout.addWidget(QLabel("转换结果："))
        parse_layout.addWidget(self.parse_result)

        parse_group.setLayout(parse_layout)
        panel_layout.addWidget(parse_group)

        panel_layout.addStretch()
        return panel

    def toggle_command_panel(self):
        """
        展开/收起右侧发送工具栏：
        只改变宽度，不改变高度；
        收起后强制恢复展开前宽度。
        """
        current_height = self.height()
        panel_width = 420  # 和 panel.setFixedWidth(420) 保持一致

        # 第一次展开前，记录原始宽度
        if not hasattr(self, "collapsed_window_width"):
            self.collapsed_window_width = self.width()

        if self.command_panel.isVisible():
            # ===== 收起 =====
            self.command_panel.setVisible(False)
            # self.command_panel_toggle_btn.setText("展开\n发送\n工具")
            self.command_panel_toggle_btn.setText("协\n议\n下\n发\n查\n询\n工\n具")

            if not self.isMaximized() and not self.isFullScreen():
                target_width = self.collapsed_window_width

                # 等Qt布局刷新后，再强制改回原始宽度
                QTimer.singleShot(
                    0,
                    lambda: self.resize(target_width, current_height)
                )

        else:
            # ===== 展开 =====
            # 只有在真正收起状态下，才更新原始宽度
            # 防止第二次展开时把1200误记成原始宽度
            if not self.isMaximized() and not self.isFullScreen():
                if not self.command_panel.isVisible():
                    # 这里不要每次覆盖，只在当前宽度明显小于展开宽度时更新
                    if self.width() < self.collapsed_window_width + panel_width:
                        self.collapsed_window_width = self.width()

            self.command_panel.setVisible(True)
            # self.command_panel_toggle_btn.setText("收起\n发送\n工具")
            self.command_panel_toggle_btn.setText("协\n议\n下\n发\n查\n询\n工\n具")

            if not self.isMaximized() and not self.isFullScreen():
                target_width = self.collapsed_window_width + panel_width

                QTimer.singleShot(
                    0,
                    lambda: self.resize(target_width, current_height)
                )

    def add_cmd_row(self):
        """
        增加命令输入行，最多10行
        """
        if len(self.cmd_rows) >= 10:
            self.result_label.setText("最多只能添加10个命令输入框")
            return

        row_layout = QHBoxLayout()

        type_display = QLineEdit()
        type_display.setReadOnly(True)
        type_display.setFixedWidth(55)
        type_display.setPlaceholderText("类型")

        cmd_input = QLineEdit()
        cmd_input.setPlaceholderText("例如：F1030428")

        send_btn = QPushButton("发送")
        send_btn.setFixedWidth(60)

        delete_btn = QPushButton("删除")
        delete_btn.setFixedWidth(60)

        row_layout.addWidget(type_display)
        row_layout.addWidget(cmd_input)
        row_layout.addWidget(send_btn)
        row_layout.addWidget(delete_btn)

        self.cmd_rows_layout.addLayout(row_layout)

        row_obj = {
            "layout": row_layout,
            "type_display": type_display,
            "cmd_input": cmd_input,
            "send_btn": send_btn,
            "delete_btn": delete_btn,
        }

        self.cmd_rows.append(row_obj)

        cmd_input.textChanged.connect(lambda: self.update_cmd_type_display(row_obj))
        send_btn.clicked.connect(lambda: self.send_single_cmd(row_obj))
        delete_btn.clicked.connect(lambda: self.delete_cmd_row(row_obj))

    def delete_cmd_row(self, row_obj):
        """
        删除一行命令输入
        """
        if row_obj not in self.cmd_rows:
            return

        # 至少保留一行
        if len(self.cmd_rows) <= 1:
            row_obj["cmd_input"].clear()
            row_obj["type_display"].clear()
            self.result_label.setText("至少保留一个命令输入框，已清空当前行")
            return

        self.cmd_rows.remove(row_obj)

        layout = row_obj["layout"]

        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        self.cmd_rows_layout.removeItem(layout)

        self.result_label.setText("已删除命令行")

    # def update_cmd_type_display(self, row_obj):
    #     """
    #     根据命令前4位显示 设置 / 查询
    #     """
    #     cmd = row_obj["cmd_input"].text().replace(" ", "").upper()
    #
    #     if cmd.startswith("F102"):
    #         row_obj["type_display"].setText("设置")
    #     elif cmd.startswith("F103"):
    #         row_obj["type_display"].setText("查询")
    #     else:
    #         row_obj["type_display"].setText("")

    def update_cmd_type_display(self, row_obj):
        """
        根据命令前4位显示命令类型
        """
        cmd = row_obj["cmd_input"].text().replace(" ", "").upper()

        if cmd.startswith("F102"):
            row_obj["type_display"].setText("设置")

        elif cmd.startswith("F103"):
            row_obj["type_display"].setText("查询")

        else:
            # 显示前4字节
            row_obj["type_display"].setText(cmd[:4])

    def get_cmd_imei_list(self):
        """
        获取右侧工具栏IMEI列表
        """
        imei_text = self.cmd_imei_input.text().strip()

        if not imei_text:
            return []

        imei_list = []

        for imei in imei_text.split(","):
            imei = imei.strip()
            if imei:
                imei_list.append(imei)

        return imei_list

    def is_valid_cmd(self, cmd):
        """
        判断命令是否合法：
        1. 不能为空
        2. 必须是F102或F103开头
        3. 必须是合法HEX
        """
        cmd = cmd.replace(" ", "").upper()

        if not cmd:
            return False

        # 限制F102 F103
        # if not (cmd.startswith("F102") or cmd.startswith("F103")):
        #     return False

        if len(cmd) % 2 != 0:
            return False

        try:
            bytes.fromhex(cmd)
        except Exception:
            return False

        return True

    def send_single_cmd(self, row_obj):
        """
        单行发送
        """
        imei_list = self.get_cmd_imei_list()
        cmd = row_obj["cmd_input"].text().replace(" ", "").upper()

        if not imei_list:
            self.result_label.setText("发送失败：IMEI为空")
            return

        if not self.is_valid_cmd(cmd):
            self.result_label.setText("发送失败：命令为空、不是F102/F103开头，或不是合法HEX")
            return

        self.send_cmd_to_server(imei_list, cmd)

    def start_auto_send(self):
        """
        开始自动循环发送：
        例如6条命令，循环10次，则总共发送60次。
        每条命令之间间隔 auto_send_interval 秒。
        """
        imei_list = self.get_cmd_imei_list()

        if not imei_list:
            self.result_label.setText("自动发送失败：IMEI为空")
            return

        valid_cmds = []

        for row_obj in self.cmd_rows:
            cmd = row_obj["cmd_input"].text().replace(" ", "").upper()

            if self.is_valid_cmd(cmd):
                valid_cmds.append(cmd)

        if not valid_cmds:
            self.result_label.setText("自动发送失败：没有有效命令")
            return

        self.auto_imei_list = imei_list
        self.auto_cmd_queue = valid_cmds
        self.auto_cmd_index = 0

        self.auto_current_loop = 1
        self.auto_total_loop = self.auto_send_loop_count.value()

        self.cmd_auto_running = True
        self.auto_send_btn.setText("停止自动发送")

        interval_sec = self.auto_send_interval.value()

        self.result_label.setText(
            f"开始自动发送：{len(valid_cmds)}条命令，循环{self.auto_total_loop}次，每条间隔{interval_sec}秒"
        )

        # 立即发送第一条
        self.send_next_cmd()

        # 后续按间隔发送
        self.cmd_auto_timer.start(interval_sec * 1000)

    def send_next_cmd(self):
        """
        每次只发送一条命令。
        一轮发完后，如果还有循环次数，则从第一条重新开始。
        """
        if not self.cmd_auto_running:
            return

        # 当前轮发完
        if self.auto_cmd_index >= len(self.auto_cmd_queue):
            self.auto_current_loop += 1

            # 所有循环结束
            if self.auto_current_loop > self.auto_total_loop:
                self.cmd_auto_timer.stop()
                self.cmd_auto_running = False
                self.auto_send_btn.setText("开始自动发送")
                self.result_label.setText("自动发送完成")
                return

            # 开始下一轮
            self.auto_cmd_index = 0

        cmd = self.auto_cmd_queue[self.auto_cmd_index]

        self.result_label.setText(
            f"自动发送中：第{self.auto_current_loop}/{self.auto_total_loop}轮，"
            f"第{self.auto_cmd_index + 1}/{len(self.auto_cmd_queue)}条 CMD:{cmd}"
        )

        self.send_cmd_to_server(self.auto_imei_list, cmd)

        self.auto_cmd_index += 1

    def send_cmd_to_server(self, imei_list, cmd):
        """
        POST发送命令，并显示服务器返回的 message 信息
        """
        url = "http://10.85.40.3:8088/client/send"

        success_count = 0
        fail_count = 0
        message_list = []

        for imei in imei_list:
            payload = {
                "imei": imei,
                "cmd": cmd
            }

            try:
                response = requests.post(url, json=payload, timeout=5)

                # 默认没有message
                callback_message = ""

                try:
                    resp_json = response.json()
                    callback_message = resp_json.get("message", "")
                    server_code = resp_json.get("code", "")
                    flow_id = ""

                    if isinstance(resp_json.get("data"), dict):
                        flow_id = resp_json.get("data", {}).get("flowId", "")

                except Exception:
                    server_code = ""
                    flow_id = ""
                    callback_message = ""

                if response.status_code == 200:
                    success_count += 1
                    send_status = "HTTP成功"
                else:
                    fail_count += 1
                    send_status = f"HTTP失败({response.status_code})"

                msg = f"IMEI:{imei} {send_status}"

                if server_code != "":
                    msg += f" code:{server_code}"

                if flow_id:
                    msg += f" flowId:{flow_id}"

                if callback_message:
                    msg += f" message:{callback_message}"

                message_list.append(msg)

            except Exception as e:
                fail_count += 1
                message_list.append(f"IMEI:{imei} 请求异常:{e}")

        self.result_label.setText(
            f"CMD:{cmd} 成功:{success_count} 失败:{fail_count} | " + " ; ".join(message_list)
        )

    def toggle_auto_send_cmd(self):
        """
        开始/停止自动发送
        """
        if self.cmd_auto_running:
            self.cmd_auto_timer.stop()
            self.cmd_auto_running = False

            self.auto_cmd_queue = []
            self.auto_cmd_index = 0
            self.auto_current_loop = 1
            self.auto_total_loop = 1
            self.auto_imei_list = []

            self.auto_send_btn.setText("开始自动发送")
            self.result_label.setText("自动发送已停止")
        else:
            self.start_auto_send()


bind_parser_methods(DataFetcherApp)
