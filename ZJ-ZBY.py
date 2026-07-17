#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MQTT 监听 + AES256CBC 解密 + 按 topic/小时存储
"""

import os
import json
import time
import threading
from datetime import datetime, timezone, timedelta

import paho.mqtt.client as mqtt
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad


# ==============================
# 日志输出
# ==============================
STORAGE_ROOT = "E:/MQTT_Data"

LOG_FILE = os.path.join(STORAGE_ROOT, "运行日志.txt")

log_lock = threading.Lock()

def log_print(*args):

    text = " ".join(str(a) for a in args)

    print(text)

    with log_lock:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(text + "\n")

# ==============================
# MQTT 配置
# ==============================

MQTT_SERVER = "zte-cid.com"  # 改成你的 broker 地址
MQTT_PORT = 1883
MQTT_USERNAME = 'admin'
MQTT_PASSWORD = 'Zbwd@010'

MQTT_TOPICS = [
    "loc/001068000000006"
]

# ==============================
# 存储目录
# ==============================

STORAGE_ROOT = "E:/MQTT_Data"


# ==============================
# AES KEY / IV
# ==============================

FIXED_KEY_HEX = "d3f67a2e5b8c901f4a6d0e3c7b291f5d8e4c2a1b0f9e8d7c6b5a493827161514"
IV_HEX = "19e4f7a83d0b6c25a81234567890abcd"

KEY_BYTES = bytes.fromhex(FIXED_KEY_HEX)
IV_BYTES = bytes.fromhex(IV_HEX)


# ==============================
# 全局变量
# ==============================

topic_files = {}
file_lock = threading.Lock()

tz = timezone(timedelta(hours=8))


# ==============================
# AES 解密
# ==============================

def decrypt_aes_cbc(data: bytes) -> str:
    cipher = AES.new(KEY_BYTES, AES.MODE_CBC, IV_BYTES)
    plain = cipher.decrypt(data)

    try:
        plain = unpad(plain, AES.block_size)
    except ValueError:
        pass

    return plain.decode("utf-8", errors="ignore")


# ==============================
# Topic 归类
# ==============================

def get_topic_category(topic: str):

    parts = topic.split("/")

    if parts[0] == "can" and len(parts) > 1:

        if parts[1] == "rx":
            return "can_rx"

        if parts[1] == "tx":
            return "can_tx"

    return parts[0]


# ==============================
# 获取文件句柄
# ==============================

def get_file(topic_name, dt):

    date_str = dt.strftime("%Y-%m-%d")
    hour_str = dt.strftime("%H")

    day_folder = os.path.join(STORAGE_ROOT, date_str)
    topic_folder = os.path.join(day_folder, topic_name)

    if not os.path.exists(topic_folder):
        os.makedirs(topic_folder, exist_ok=True)
        log_print(f"[INFO] 创建目录: {topic_folder}")

    file_name = f"{topic_name}-{hour_str}.txt"
    file_path = os.path.join(topic_folder, file_name)

    key = f"{topic_name}_{date_str}_{hour_str}"

    with file_lock:

        if key in topic_files:
            return topic_files[key]

        if not os.path.exists(file_path):
            log_print(f"[INFO] 创建文件: {file_path}")

        f = open(file_path, "a", encoding="utf-8")

        topic_files[key] = f

        return f


# ==============================
# 关闭旧文件
# ==============================

def close_old_files(dt):

    date_str = dt.strftime("%Y-%m-%d")
    hour_str = dt.strftime("%H")

    with file_lock:

        remove_keys = []

        for key, f in topic_files.items():

            if not key.endswith(f"{date_str}_{hour_str}"):

                try:
                    f.close()
                except:
                    pass

                remove_keys.append(key)

        for k in remove_keys:
            del topic_files[k]


# ==============================
# MQTT 回调
# ==============================

def on_connect(client, userdata, flags, rc):

    if rc == 0:

        log_print(f"[INFO] MQTT 连接成功 -> {MQTT_SERVER}:{MQTT_PORT}")

        for topic in MQTT_TOPICS:

            client.subscribe(topic)

            log_print("订阅:", topic)

    else:

        log_print("MQTT 连接失败:", rc)


def on_disconnect(client, userdata, rc):

    log_print(f"[WARN] MQTT 断开连接 rc={rc}")

    while True:

        try:

            log_print("[INFO] 尝试重新连接 MQTT...")

            client.reconnect()

            log_print("[INFO] MQTT 重连成功")

            return

        except Exception:

            time.sleep(5)


def on_message(client, userdata, msg):

    dt = datetime.now(tz)
    timestamp = dt.strftime("%Y-%m-%d %H:%M:%S")

    topic_name = get_topic_category(msg.topic)

    try:

        decrypted = decrypt_aes_cbc(msg.payload)

        try:
            obj = json.loads(decrypted)
            display = json.dumps(obj, indent=2, ensure_ascii=False)
        except:
            display = decrypted

    except Exception as e:

        display = f"[DECRYPT ERROR] {e}"

    # log_print(f"{timestamp} Topic: {msg.topic} QoS: {msg.qos}")
    # log_print(display)
    # log_print("-" * 60)

    close_old_files(dt)

    f = get_file(topic_name, dt)

    text = f"{timestamp} Topic: {msg.topic} QoS: {msg.qos}\n{display}\n\n"

    with file_lock:

        f.write(text)

        f.flush()

        os.fsync(f.fileno())


# ==============================
# 每小时创建空文件
# ==============================

def hourly_file_creator():

    while True:

        dt = datetime.now(tz)

        date_str = dt.strftime("%Y-%m-%d")
        hour_str = dt.strftime("%H")

        for topic in MQTT_TOPICS:

            topic_name = get_topic_category(topic.replace("/#", ""))

            folder = os.path.join(STORAGE_ROOT, date_str, topic_name)

            os.makedirs(folder, exist_ok=True)

            file_path = os.path.join(folder, f"{topic_name}-{hour_str}.txt")

            if not os.path.exists(file_path):
                open(file_path, "a").close()

                log_print(f"[INFO] 创建小时文件: {file_path}")

        time.sleep(3600)


# ==============================
# 主程序
# ==============================

def main():

    threading.Thread(target=hourly_file_creator, daemon=True).start()

    client = mqtt.Client()

    if MQTT_USERNAME:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect

    try:

        client.connect(MQTT_SERVER, MQTT_PORT, 60)

    except Exception as e:

        log_print("MQTT 连接失败:", e)

        return

    client.loop_forever()


if __name__ == "__main__":

    main()
