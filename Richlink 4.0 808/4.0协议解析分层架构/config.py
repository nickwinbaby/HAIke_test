DATA_TYPE_OPTIONS = [
    "Select Type",
    "RAW DATA & Protocol",
    "0 - Connect or disconnect",
    "1 - Trip data",
    "2 - Driving behavior",
    "3 - Location data",
    "4 - Vehicle data",
    "5 - Secure data",
    "6 - Device state",
    "7 - Device request message",
    "8 - Active server request",
    "9 - Accessories information",
]

SUBTYPE_OPTIONS = {
    # RAW DATA
    "RAW DATA & Protocol": [
        "RAW DATA",
        "Protocol consistency",
    ],

    # Chapter 0 - Connect or disconnect
    "0 - Connect or disconnect": [
        "Connect",
        "Disconnect",
    ],

    # Chapter 1 - Trip data
    "1 - Trip data": [
        "1.1 - trip summary",
        "1.2 - Ignition on",
        "1.3 - Ignition off",
        "1.4 - trip start",
        "1.5 - trip end",
    ],

    # Chapter 2 - Driving behavior
    "2 - Driving behavior": [
        "2.1 - Sudden acc",
        "2.2 - Sudden dec",
        "2.3 - Sharp turn",
        "2.4 - Exceed idle",
        "2.5 - Driving tired",
        "2.6 - Over speed",
        "2.7 - Sudden Lane Change",
    ],

    # Chapter 3 - Location data
    "3 - Location data": [
        "3.1 - GPS data",
        "3.2 - LBS data",
    ],

    # Chapter 4 - Vehicle data
    "4 - Vehicle data": [
        "4.1 - VIN Cold",
        "4.2 - Data flow",
        "4.3 - CAN parameter support status",
        "4.4 - Raw can frame",
        "4.5 - Config data flow",
        "4.6 - Vehicle Information KLV",
    ],

    # Chapter 5 - Secure data
    "5 - Secure data": [
        "5.1 - DTC code",
        "5.2 - Battery low",
        "5.3 - Vibration event",
        "5.4 - Suspected collision",
        "5.5 - Unplug warning",
        "5.6 - Jamming detection",
        "5.7 - Device tamper warning",
        "5.8 - Temperature warning",
        "5.9 - Air pressure warning",
        "5.10 - Shock warning",
        "5.12 - Humidity warning",
        "5.13 - Device warning message",
        "5.15 - Fence warning",
    ],

    # Chapter 6 - Device state
    "6 - Device state": [
        "6.1 - Sleep state",
        "6.2 - Wakeup state",
        "6.3 - GPS not fix",
        "6.4 - Reboot event",
        "6.5 - Mcu upgrade state",
        "6.6 - SMS",
        "6.7 - Device info",
        "6.8 - Sensor normal",
        "6.9 - Sensor event",
        "6.11 - Relay control status",
        "6.12 - Self learning status",
        "Bosch crash data",
    ],

    # Chapter 7 - Device request message
    "7 - Device request message": [
        "7.1 -Request MCU update package(TCP)",
        "7.2 - Request AGPS data",
        "7.3 - MCU Update package verification(TCP)",
        "7.4 - MCU Log Report",
        "7.5 - Check new update package(Router)-暂不开发",
        "7.6 - Response to the New Update Package(Router)-暂不开发",
    ],

    # Chapter 8 - Active server request
    "8 - Active server request": [
        "8.2 - Set parameters",
        "8.3 - Inquiry parameters",
        "8.8 - whitelist management",
        "8.9 - whitelist query",
        "8.11.2 - Management fence device response",
        "8.12.2 - Query fence device response",
    ],

    # Chapter 9 - Accessories information
    "9 - Accessories information": [
        "9.1 - Ibutton id",
        "9.2 - Ble sensor data",
        "9.3 - Rs485 temperature humidity",
        "9.4 - Ble sensor warning",
        "9.5 - Rfid data",
        "9.7 - Ble tag",
    ],
}

CHECKBOX_GROUP_BY_SUBTYPE = {
    # Chapter 0
    "Connect": "connect",
    "Disconnect": "disconnect",

    # Chapter 1
    "1.1 - trip summary": "trip",
    "1.2 - Ignition on": "eng",
    "1.3 - Ignition off": "eng",
    "1.4 - trip start": "passive_trip",
    "1.5 - trip end": "passive_trip",

    # Chapter 2
    "2.1 - Sudden acc": "sudden",
    "2.2 - Sudden dec": "sudden",
    "2.3 - Sharp turn": "sharp_turn",
    "2.4 - Exceed idle": "exceed_idle",
    "2.5 - Driving tired": "driving_tired",
    "2.6 - Over speed": "over_speed",
    "2.7 - Sudden Lane Change": "sudden_lane_change",

    # Chapter 3
    "3.1 - GPS data": "gps_location_data",
    "3.2 - LBS data": "lbs_location_data",

    # Chapter 4
    "4.1 - VIN Cold": "vin",
    "4.2 - Data flow": "dataflow",
    "4.3 - CAN parameter support status": "can_parameter_support_status",
    "4.4 - Raw can frame": "raw_can_frame",
    "4.5 - Config data flow": "config_dataflow",
    "4.6 - Vehicle Information KLV": "vehicle_Information_klv",

    # Chapter 5
    "5.1 - DTC code": "dtc_code",
    "5.2 - Battery low": "battery_low",
    "5.3 - Vibration event": "vibration_event",
    "5.4 - Suspected collision": "suspected_collision",
    "5.5 - Unplug warning": "unplug_warning",
    "5.6 - Jamming detection": "jamming_detection",
    "5.7 - Device tamper warning": "device_tamper_warning",
    "5.8 - Temperature warning": "temperature_warning",
    "5.9 - Air pressure warning": "air_pressure_warning",
    "5.10 - Shock warning": "shock_warning",
    "5.12 - Humidity warning": "humidity_warning",
    "5.13 - Device warning message": "device_warning_message",
    "5.15 - Fence warning": "fence_warning",

    # Chapter 6
    "6.1 - Sleep state": "sleep_state",
    "6.2 - Wakeup state": "wakeup_state",
    "6.3 - GPS not fix": "gps_not_fix",
    "6.4 - Reboot event": "reboot_event",
    "6.5 - Mcu upgrade state": "mcu_upgrade_state",
    "6.6 - SMS": "sms",
    "6.7 - Device info": "device_info",
    "6.8 - Sensor normal": "sensor_normal",
    "6.9 - Sensor event": "sensor_event",
    "6.11 - Relay control status": "relay_control_status",
    "6.12 - Self learning status": "self_learning_status",
    "Bosch crash data": "bosch_crash",

    # Chapter 7
    "7.1 -Request MCU update package(TCP)": "request_mcu_update_package_tcp",
    "7.2 - Request AGPS data": "request_agps_data",
    "7.3 - MCU Update package verification(TCP)": "mcu_update_package_verification_tcp",
    "7.4 - MCU Log Report": "mcu_log_report",

    # Chapter 8
    "8.2 - Set parameters": "set_parameters",
    "8.3 - Inquiry parameters": "inquiry_parameters",
    "8.8 - whitelist management": "whitelist_management",
    "8.9 - whitelist query": "whitelist_query",
    "8.11.2 - Management fence device response": "message_fence_device_response",
    "8.12.2 - Query fence device response": "query_fence_to_device",

    # Chapter 9
    "9.1 - Ibutton id": "ibutton_id",
    "9.2 - Ble sensor data": "ble_sensor_data",
    "9.3 - Rs485 temperature humidity": "rs485_temperature_humidity",
    "9.4 - Ble sensor warning": "ble_sensor_warning",
    "9.5 - Rfid data": "rfid_data",
    "9.7 - Ble tag": "ble_tag_data",
}

PROCESS_HANDLER_BY_SELECTION = {
    # RAW DATA
    ("RAW DATA & Protocol", "RAW DATA"): "display_raw_data",
    ("RAW DATA & Protocol", "Protocol consistency"): "display_protocol_consistency",

    # Chapter 0
    ("0 - Connect or disconnect", "Connect"): "process_connect_data",
    ("0 - Connect or disconnect", "Disconnect"): "process_disconnect_data",

    # Chapter 1
    ("1 - Trip data", "1.1 - trip summary"): "process_trip_summary",
    ("1 - Trip data", "1.2 - Ignition on"): "process_ignition_on",
    ("1 - Trip data", "1.3 - Ignition off"): "process_ignition_off",
    ("1 - Trip data", "1.4 - trip start"): "process_trip_start",
    ("1 - Trip data", "1.5 - trip end"): "process_trip_end",

    # Chapter 2
    ("2 - Driving behavior", "2.1 - Sudden acc"): "process_sudden_acc",
    ("2 - Driving behavior", "2.2 - Sudden dec"): "process_sudden_dec",
    ("2 - Driving behavior", "2.3 - Sharp turn"): "process_sharp_turn",
    ("2 - Driving behavior", "2.4 - Exceed idle"): "process_exceed_idle",
    ("2 - Driving behavior", "2.5 - Driving tired"): "process_driving_tired",
    ("2 - Driving behavior", "2.6 - Over speed"): "process_over_speed",
    ("2 - Driving behavior", "2.7 - Sudden Lane Change"): "process_sudden_lane_change",

    # Chapter 3
    ("3 - Location data", "3.1 - GPS data"): "process_gps_data_3",
    ("3 - Location data", "3.2 - LBS data"): "process_lbs_data",

    # Chapter 4
    ("4 - Vehicle data", "4.1 - VIN Cold"): "process_vin_code",
    ("4 - Vehicle data", "4.2 - Data flow"): "process_data_flow",
    ("4 - Vehicle data", "4.3 - CAN parameter support status"): "process_can_parameter_support_status",
    ("4 - Vehicle data", "4.4 - Raw can frame"): "process_raw_can_frame",
    ("4 - Vehicle data", "4.5 - Config data flow"): "process_config_data_flow",
    ("4 - Vehicle data", "4.6 - Vehicle Information KLV"): "process_vehicle_Information_klv",

    # Chapter 5
    ("5 - Secure data", "5.1 - DTC code"): "process_dtc_code",
    ("5 - Secure data", "5.2 - Battery low"): "process_battery_low",
    ("5 - Secure data", "5.3 - Vibration event"): "process_vibration_event",
    ("5 - Secure data", "5.4 - Suspected collision"): "process_suspected_collision",
    ("5 - Secure data", "5.5 - Unplug warning"): "process_unplug_warning",
    ("5 - Secure data", "5.6 - Jamming detection"): "process_jamming_detection",
    ("5 - Secure data", "5.7 - Device tamper warning"): "process_device_tamper_warning",
    ("5 - Secure data", "5.8 - Temperature warning"): "process_temperature_warning",
    ("5 - Secure data", "5.9 - Air pressure warning"): "process_air_pressure_warning",
    ("5 - Secure data", "5.10 - Shock warning"): "process_shock_warning",
    ("5 - Secure data", "5.12 - Humidity warning"): "process_humidity_warning",
    ("5 - Secure data", "5.13 - Device warning message"): "process_device_warning_message",
    ("5 - Secure data", "5.15 - Fence warning"): "process_fence_warning",

    # Chapter 6
    ("6 - Device state", "6.1 - Sleep state"): "process_sleep_state",
    ("6 - Device state", "6.2 - Wakeup state"): "process_wakeup_state",
    ("6 - Device state", "6.3 - GPS not fix"): "process_gps_not_fix",
    ("6 - Device state", "6.4 - Reboot event"): "process_reboot_event",
    ("6 - Device state", "6.5 - Mcu upgrade state"): "process_mcu_upgrade_state",
    ("6 - Device state", "6.6 - SMS"): "process_sms",
    ("6 - Device state", "6.7 - Device info"): "process_device_info",
    ("6 - Device state", "6.8 - Sensor normal"): "process_sensor_normal",
    ("6 - Device state", "6.9 - Sensor event"): "process_sensor_event",
    ("6 - Device state", "6.11 - Relay control status"): "process_relay_control_status",
    ("6 - Device state", "6.12 - Self learning status"): "process_self_learning_status",
    ("6 - Device state", "Bosch crash data"): "process_bosch_crash_data",

    # Chapter 7
    ("7 - Device request message", "7.1 -Request MCU update package(TCP)"): "process_request_mcu_update_package_tcp",
    ("7 - Device request message", "7.2 - Request AGPS data"): "process_request_agps_data",
    ("7 - Device request message", "7.3 - MCU Update package verification(TCP)"): "process_mcu_update_package_verification_tcp",
    ("7 - Device request message", "7.4 - MCU Log Report"): "process_mcu_log_report",

    # Chapter 8
    ("8 - Active server request", "8.2 - Set parameters"): "process_set_parameters",
    ("8 - Active server request", "8.3 - Inquiry parameters"): "process_inquiry_parameters",
    ("8 - Active server request", "8.8 - whitelist management"): "process_whitelist_management",
    ("8 - Active server request", "8.9 - whitelist query"): "process_whitelist_query",
    ("8 - Active server request", "8.11.2 - Management fence device response"): "process_message_fence_response",
    ("8 - Active server request", "8.12.2 - Query fence device response"): "process_query_fence_to_device",

    # Chapter 9
    ("9 - Accessories information", "9.1 - Ibutton id"): "process_ibutton_id",
    ("9 - Accessories information", "9.2 - Ble sensor data"): "process_ble_sensor_data",
    ("9 - Accessories information", "9.3 - Rs485 temperature humidity"): "process_rs485_temperature_humidity",
    ("9 - Accessories information", "9.4 - Ble sensor warning"): "process_ble_sensor_warning",
    ("9 - Accessories information", "9.5 - Rfid data"): "process_rfid_data",
    ("9 - Accessories information", "9.7 - Ble tag"): "process_ble_tag_data",
}
