import math
import tkinter as tk
from tkinter import ttk, messagebox
import sys, os

def resource_path(relative_path):
    """获取资源文件的绝对路径（兼容打包后和开发模式）"""
    try:
        # PyInstaller 创建的临时文件夹
        base_path = sys._MEIPASS
    except Exception:
        # 开发模式下的路径
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


# 坐标转换核心常量
PI = 3.1415926535897932384626
A = 6378245.0              # 长半轴
EE = 0.00669342162296594323  # 扁率

# ===================== 核心转换函数 =====================
def _out_of_china(lat, lon):
    """判断是否在中国（大致矩形范围），在中国外则不做转换。"""
    return not (lat > 0.8293 and lat < 55.8271 and lon > 72.004 and lon < 137.8347)

def _transform_lat(x, y):
    ret = -100.0 + 2.0*x + 3.0*y + 0.2*y*y + 0.1*x*y + 0.2*math.sqrt(abs(x))
    ret += (20.0*math.sin(6.0*x*PI) + 20.0*math.sin(2.0*x*PI)) * 2.0/3.0
    ret += (20.0*math.sin(y*PI) + 40.0*math.sin(y/3.0*PI)) * 2.0/3.0
    ret += (160.0*math.sin(y/12.0*PI) + 320*math.sin(y*PI/30.0)) * 2.0/3.0
    return ret

def _transform_lon(x, y):
    ret = 300.0 + x + 2.0*y + 0.1*x*x + 0.1*x*y + 0.1*math.sqrt(abs(x))
    ret += (20.0*math.sin(6.0*x*PI) + 20.0*math.sin(2.0*x*PI)) * 2.0/3.0
    ret += (20.0*math.sin(x*PI) + 40.0*math.sin(x/3.0*PI)) * 2.0/3.0
    ret += (150.0*math.sin(x/12.0*PI) + 300.0*math.sin(x/30.0*PI)) * 2.0/3.0
    return ret

def wgs84_to_gcj02(lat, lon):
    """WGS84转GCJ02"""
    if _out_of_china(lat, lon):
        return lat, lon

    dLat = _transform_lat(lon - 105.0, lat - 35.0)
    dLon = _transform_lon(lon - 105.0, lat - 35.0)
    radLat = lat / 180.0 * PI
    magic = math.sin(radLat)
    magic = 1 - EE * magic * magic
    sqrtMagic = math.sqrt(magic)
    dLat = (dLat * 180.0) / ((A * (1 - EE)) / (magic * sqrtMagic) * PI)
    dLon = (dLon * 180.0) / (A / sqrtMagic * math.cos(radLat) * PI)
    mgLat = lat + dLat
    mgLon = lon + dLon
    return mgLat, mgLon

def gcj02_to_wgs84(lat, lon):
    """GCJ02转WGS84"""
    if _out_of_china(lat, lon):
        return lat, lon

    # 先正向算出偏移值
    dLat, dLon = _transform_lat(lon - 105.0, lat - 35.0), _transform_lon(lon - 105.0, lat - 35.0)
    radLat = lat / 180.0 * PI
    magic = math.sin(radLat)
    magic = 1 - EE * magic * magic
    sqrtMagic = math.sqrt(magic)
    dLat = (dLat * 180.0) / ((A * (1 - EE)) / (magic * sqrtMagic) * PI)
    dLon = (dLon * 180.0) / (A / sqrtMagic * math.cos(radLat) * PI)

    # 反推WGS84
    wgsLat = lat - dLat
    wgsLon = lon - dLon
    return wgsLat, wgsLon

# ===================== GUI界面 =====================
class CoordConverterGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("WGS84 ↔ GCJ02 坐标转换工具 - Mangetic - 2026-6-17 ★★★★★ 广告位招租 ★★★★★★")
        self.root.geometry("500x400")
        self.root.resizable(False, False)

        # 样式配置
        self.style = ttk.Style()
        self.style.configure("TLabel", font=("微软雅黑", 10))
        self.style.configure("TButton", font=("微软雅黑", 10))
        self.style.configure("TEntry", font=("微软雅黑", 10))
        self.style.configure("TRadiobutton", font=("微软雅黑", 10))

        # 转换方向选择
        self.convert_direction = tk.StringVar(value="wgs2gcj")
        frame_direction = ttk.LabelFrame(root, text="转换方向", padding=10)
        frame_direction.pack(fill="x", padx=20, pady=10)

        rbtn1 = ttk.Radiobutton(frame_direction, text="WGS84 → GCJ02",
                                variable=self.convert_direction, value="wgs2gcj")
        rbtn1.pack(side="left", padx=20)

        rbtn2 = ttk.Radiobutton(frame_direction, text="GCJ02 → WGS84",
                                variable=self.convert_direction, value="gcj2wgs")
        rbtn2.pack(side="left", padx=20)

        # 输入坐标
        frame_input = ttk.LabelFrame(root, text="输入坐标", padding=10)
        frame_input.pack(fill="x", padx=20, pady=10)

        ttk.Label(frame_input, text="纬度(Latitude)：").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        self.input_lat = ttk.Entry(frame_input, width=30)
        self.input_lat.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(frame_input, text="经度(Longitude)：").grid(row=1, column=0, padx=5, pady=5, sticky="e")
        self.input_lon = ttk.Entry(frame_input, width=30)
        self.input_lon.grid(row=1, column=1, padx=5, pady=5)

        # 转换按钮
        btn_convert = ttk.Button(root, text="执行转换", command=self.on_convert)
        btn_convert.pack(pady=10)

        # 输出结果
        frame_output = ttk.LabelFrame(root, text="转换结果", padding=10)
        frame_output.pack(fill="x", padx=20, pady=10)

        ttk.Label(frame_output, text="转换后纬度：").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        self.output_lat = ttk.Entry(frame_output, width=30, state="readonly")
        self.output_lat.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(frame_output, text="转换后经度：").grid(row=1, column=0, padx=5, pady=5, sticky="e")
        self.output_lon = ttk.Entry(frame_output, width=30, state="readonly")
        self.output_lon.grid(row=1, column=1, padx=5, pady=5)

        # 清空按钮
        btn_clear = ttk.Button(root, text="清空内容", command=self.on_clear)
        btn_clear.pack(pady=5)

    def on_convert(self):
        """执行转换逻辑"""
        try:
            # 获取输入坐标
            lat = float(self.input_lat.get().strip())
            lon = float(self.input_lon.get().strip())

            # 校验坐标范围（基础校验）
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                messagebox.showerror("错误", "纬度范围需在[-90,90]，经度范围需在[-180,180]！")
                return

            # 根据方向执行转换
            if self.convert_direction.get() == "wgs2gcj":
                res_lat, res_lon = wgs84_to_gcj02(lat, lon)
            else:
                res_lat, res_lon = gcj02_to_wgs84(lat, lon)

            # 格式化输出（保留8位小数，符合GPS精度）
            self.set_readonly_text(self.output_lat, f"{res_lat:.8f}")
            self.set_readonly_text(self.output_lon, f"{res_lon:.8f}")

            # 提示境外坐标
            if _out_of_china(lat, lon):
                messagebox.showinfo("提示", "该坐标不在中国境内，返回原始坐标！")

        except ValueError:
            messagebox.showerror("错误", "请输入有效的数字格式坐标！")
        except Exception as e:
            messagebox.showerror("错误", f"转换失败：{str(e)}")

    def on_clear(self):
        """清空所有输入输出"""
        self.input_lat.delete(0, tk.END)
        self.input_lon.delete(0, tk.END)
        self.set_readonly_text(self.output_lat, "")
        self.set_readonly_text(self.output_lon, "")

    def set_readonly_text(self, entry, text):
        """设置只读输入框的内容"""
        entry.config(state="normal")
        entry.delete(0, tk.END)
        entry.insert(0, text)
        entry.config(state="readonly")

# 程序入口
if __name__ == "__main__":
    root = tk.Tk()
    # 窗口图标，ico和脚本放一起
    #root.iconbitmap("Gico.ico")
    ico_file = resource_path("Gico.ico")
    root.iconbitmap(ico_file)
    # root.title("WGS84 ↔ GCJ02 坐标转换工具")
    app = CoordConverterGUI(root)
    root.mainloop()
