# launcher.py
import tkinter as tk
from tkinter import messagebox, Button

# 导入你的模块
from gps_tool import run_gui as run_gps_gui
from sensor_tool import create_gui as run_sensor_gui

def launch_gps():
    try:
        run_gps_gui()
    except Exception as e:
        tk.messagebox.showerror("GPS 错误", str(e))

def launch_sensor():
    try:
        run_sensor_gui()
    except Exception as e:
        tk.messagebox.showerror("SENSOR 错误", str(e))

def main_launcher():
    root = tk.Tk()
    root.title("程序启动器")
    root.geometry("300x200")

    tk.Label(root, text="选择启动程序").pack(pady=20)

    tk.Button(root, text="启动 GPS 分析", command=launch_gps, width=20, height=2, bg="skyblue").pack(pady=10)
    tk.Button(root, text="启动 SENSOR 分析", command=launch_sensor, width=20, height=2, bg="lightgreen").pack(pady=10)

    root.mainloop()

if __name__ == "__main__":
    main_launcher()
