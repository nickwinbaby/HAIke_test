import tkinter as tk
from tkinter import ttk, messagebox
import re
import webbrowser


class KLVPacketBuilder(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("电子围栏 KLV 数据组包工具 - Mangetic - 2026-5-8")
        self.geometry("1580x820")
        self.klv_rows = []

        self._build_base_form()
        self._build_klv_area()
        self._build_output_area()
        self.rebuild_klv_rows()

    # ===================== 界面 =====================
    def _build_base_form(self):
        container = ttk.Frame(self)
        container.pack(fill="x", padx=10, pady=8)

        frame = ttk.LabelFrame(container, text="大包基础字段")
        frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        convert_frame = ttk.LabelFrame(container, text="经纬度辅助转换-十进制")
        convert_frame.grid(row=0, column=1, sticky="nsew", padx=(0, 8))

        note_frame = ttk.LabelFrame(container, text="字段说明")
        note_frame.grid(row=0, column=2, sticky="nsew")

        container.grid_columnconfigure(0, weight=1)
        container.grid_columnconfigure(1, weight=1)
        container.grid_columnconfigure(2, weight=1)

        self.major_minor_var = tk.StringVar(value="F10F")
        self.op_type_var = tk.StringVar(value="01")
        self.total_fence_var = tk.StringVar()
        self.msg_index_var = tk.StringVar()
        self.msg_fence_count_var = tk.StringVar(value="1")

        fields = [
            ("major_minor", ttk.Entry(frame, textvariable=self.major_minor_var, state="readonly")),
            ("操作类型", ttk.Combobox(frame, textvariable=self.op_type_var, values=["01", "02", "03", "00"], state="readonly")),
            ("待操作围栏总数", ttk.Entry(frame, textvariable=self.total_fence_var)),
            ("此消息索引开始", ttk.Entry(frame, textvariable=self.msg_index_var)),
            ("此消息中围栏总数", ttk.Combobox(frame, textvariable=self.msg_fence_count_var, values=[str(i) for i in range(1, 41)], state="readonly")),
        ]

        for r, (label, widget) in enumerate(fields):
            ttk.Label(frame, text=label, width=18).grid(row=r, column=0, padx=8, pady=6, sticky="w")
            widget.grid(row=r, column=1, padx=8, pady=6, sticky="ew")
            widget.configure(width=30)

        frame.grid_columnconfigure(1, minsize=260)
        self.msg_fence_count_var.trace_add("write", lambda *_: self.rebuild_klv_rows())

        # 字段说明
        note_text = tk.Text(note_frame, width=44, height=11, wrap="word")
        note_text.pack(fill="both", expand=True, padx=6, pady=6)

        note_content = """【操作类型】
00：添加新的
01：删除所有
02：覆盖全部
03：覆盖部分

【上报方式】
00：禁用
01：进入区域
02：离开区域
03：进入和离开区域

【围栏类型 / Location Point Number】
01：圆形，KEY=404，1组GPS+半径
02：矩形，KEY=405，2组GPS
03~10：多边形，KEY=406，选择几就生成几组GPS

【经纬度方向】
经度：东经 / 西经
纬度：南纬 / 北纬
"""
        note_text.insert("1.0", note_content)
        note_text.configure(state="disabled")

        # 经纬度辅助转换
        ttk.Label(convert_frame, text="输入：度分秒 或 度分分 [34°11′21.77″ 3411.3625]").grid(row=0, column=0, columnspan=3, padx=6, pady=(6, 2), sticky="w")

        self.coord_input_var = tk.StringVar()
        self.coord_output_var = tk.StringVar()

        ttk.Entry(convert_frame, textvariable=self.coord_input_var, width=30).grid(row=1, column=0, columnspan=3, padx=6, pady=4, sticky="ew")
        ttk.Button(convert_frame, text="转换", command=self.convert_coordinate).grid(row=2, column=0, padx=6, pady=4, sticky="ew")
        ttk.Button(convert_frame, text="复制", command=self.copy_coordinate).grid(row=2, column=1, padx=6, pady=4, sticky="ew")
        ttk.Button(convert_frame, text="清空", command=self.clear_coordinate).grid(row=2, column=2, padx=6, pady=4, sticky="ew")
        ttk.Entry(convert_frame, textvariable=self.coord_output_var, width=30, state="readonly").grid(row=3, column=0, columnspan=3, padx=6, pady=4, sticky="ew")

        link = ttk.Label(convert_frame, text="坐标拾取器-网页", foreground="#2563eb", cursor="hand2")
        link.grid(row=4, column=0, columnspan=3, padx=6, pady=(4, 8), sticky="w")
        link.bind("<Button-1>", lambda e: webbrowser.open("https://www.ufreetools.com/zh/tool/coordinate-picker-and-latitude-longitude-query-tool"))

        convert_frame.grid_columnconfigure(0, weight=1)
        convert_frame.grid_columnconfigure(1, weight=1)
        convert_frame.grid_columnconfigure(2, weight=1)

    def _build_klv_area(self):
        outer = ttk.LabelFrame(self, text="KLV 数据行")
        outer.pack(fill="both", expand=True, padx=10, pady=8)

        canvas = tk.Canvas(outer)
        x_scroll = ttk.Scrollbar(outer, orient="horizontal", command=canvas.xview)
        y_scroll = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        self.klv_table = ttk.Frame(canvas)

        self.klv_table.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=self.klv_table, anchor="nw")
        canvas.configure(xscrollcommand=x_scroll.set, yscrollcommand=y_scroll.set)

        y_scroll.pack(side="right", fill="y")
        canvas.pack(side="top", fill="both", expand=True)
        x_scroll.pack(side="bottom", fill="x")

    def _build_output_area(self):
        frame = ttk.LabelFrame(self, text="组包输出")
        frame.pack(fill="x", padx=10, pady=8)

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill="x", pady=4)

        ttk.Button(btn_frame, text="生成完整大包", command=self.build_packet).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="复制结果", command=self.copy_result).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="清空输出", command=lambda: self.output_text.delete("1.0", "end")).pack(side="left", padx=5)

        self.output_text = tk.Text(frame, height=11, wrap="word")
        self.output_text.pack(fill="x", padx=5, pady=6)

    def rebuild_klv_rows(self):
        for child in self.klv_table.winfo_children():
            child.destroy()
        self.klv_rows.clear()

        headers = [
            "围栏ID", "上报方式", "围栏类型/点数", "KEY",
            "经度", "经度值-1", "纬度", "纬度值-1",
            "半径/经度", "经度值-2", "纬度", "纬度值-2",
            "说明"
        ]
        self.base_header_labels = []

        for c, h in enumerate(headers):
            label = ttk.Label(self.klv_table, text=h, relief="ridge", padding=5)
            label.grid(row=0, column=c, sticky="nsew")
            self.base_header_labels.append(label)

        try:
            count = int(self.msg_fence_count_var.get())
        except ValueError:
            count = 1

        for r in range(count):
            self.add_klv_row(r + 1)

    def add_klv_row(self, row_index):
        row = {
            "fence_id": tk.StringVar(),
            "report_type": tk.StringVar(value="00"),
            "fence_type": tk.StringVar(value="01"),
            "key": tk.StringVar(value="404"),
            "radius": tk.StringVar(),
            "gps": [],
            "widgets": {},
            "extra_widgets": [],
            "row_index": row_index,
        }

        for _ in range(11):
            row["gps"].append({
                "lon_dir": tk.StringVar(value="东经"),
                "lon": tk.StringVar(),
                "lat_dir": tk.StringVar(value="北纬"),
                "lat": tk.StringVar(),
            })

        def entry(col, var, width=12, state="normal"):
            w = ttk.Entry(self.klv_table, textvariable=var, width=width, state=state)
            w.grid(row=row_index, column=col, padx=3, pady=3, sticky="ew")
            return w

        def combo(col, var, values, width=10):
            w = ttk.Combobox(self.klv_table, textvariable=var, values=values, state="readonly", width=width)
            w.grid(row=row_index, column=col, padx=3, pady=3, sticky="ew")
            return w

        entry(0, row["fence_id"], 10)
        combo(1, row["report_type"], ["00", "01", "02", "03"], 8)
        combo(2, row["fence_type"], [f"{i:02d}" for i in range(1, 12)], 10)
        entry(3, row["key"], 10, state="readonly")

        # 第 1 组 GPS，所有类型都需要
        combo(4, row["gps"][0]["lon_dir"], ["东经", "西经"], 8)
        entry(5, row["gps"][0]["lon"], 14)
        combo(6, row["gps"][0]["lat_dir"], ["南纬", "北纬"], 8)
        entry(7, row["gps"][0]["lat"], 14)

        # 第 8 列：01 时是半径；02/03~10 时是第 2 组经度方向
        row["widgets"]["col8_container"] = ttk.Frame(self.klv_table)
        row["widgets"]["col8_container"].grid(row=row_index, column=8, padx=3, pady=3, sticky="ew")

        # 第 2 组 GPS 的其它字段
        row["widgets"]["gps2_lon"] = entry(9, row["gps"][1]["lon"], 14)
        row["widgets"]["gps2_lat_dir"] = combo(10, row["gps"][1]["lat_dir"], ["南纬", "北纬"], 8)
        row["widgets"]["gps2_lat"] = entry(11, row["gps"][1]["lat"], 14)

        row["widgets"]["desc_container"] = ttk.Frame(self.klv_table)
        row["widgets"]["desc_container"].grid(row=row_index, column=12, padx=3, pady=3, sticky="ew")

        row["fence_type"].trace_add("write", lambda *_: self.refresh_row_by_type(row))
        self.klv_rows.append(row)
        self.refresh_row_by_type(row)

    def clear_container(self, widget):
        for child in widget.winfo_children():
            child.destroy()

    def clear_extra_gps_widgets(self, row):
        for widget in row["extra_widgets"]:
            widget.destroy()
        row["extra_widgets"].clear()

        row_index = row["row_index"]
        for col in range(13, 45):
            for child in self.klv_table.grid_slaves(row=row_index, column=col):
                child.destroy()
            for child in self.klv_table.grid_slaves(row=0, column=col):
                child.destroy()

    def refresh_row_by_type(self, row):
        fence_type = row["fence_type"].get()
        row_index = row["row_index"]

        col8 = row["widgets"]["col8_container"]
        desc_col = row["widgets"]["desc_container"]
        self.clear_container(col8)
        self.clear_container(desc_col)
        self.clear_extra_gps_widgets(row)

        if fence_type == "01":
            row["key"].set("404")

            self.base_header_labels[5].configure(text="经度(圆)")
            self.base_header_labels[7].configure(text="纬度(圆)")
            self.base_header_labels[8].configure(text="半径")
            self.base_header_labels[9].configure(text="")
            self.base_header_labels[10].configure(text="")
            self.base_header_labels[11].configure(text="")
            self.base_header_labels[12].configure(text="说明")

            ttk.Entry(col8, textvariable=row["radius"], width=12).pack(fill="x")

            for key in ["gps2_lon", "gps2_lat_dir", "gps2_lat"]:
                row["widgets"][key].grid_remove()

            ttk.Label(desc_col, text="圆形：1组GPS+半径").pack()

        elif fence_type == "02":
            row["key"].set("405")

            self.base_header_labels[5].configure(text="经度(方)-1")
            self.base_header_labels[7].configure(text="纬度(方)-1")
            self.base_header_labels[8].configure(text="经度")
            self.base_header_labels[9].configure(text="经度(方)-2")
            self.base_header_labels[10].configure(text="纬度")
            self.base_header_labels[11].configure(text="纬度(方)-2")
            self.base_header_labels[12].configure(text="说明")

            ttk.Combobox(col8, textvariable=row["gps"][1]["lon_dir"], values=["东经", "西经"], state="readonly", width=8).pack(fill="x")
            for key in ["gps2_lon", "gps2_lat_dir", "gps2_lat"]:
                row["widgets"][key].grid()

            ttk.Label(desc_col, text="矩形：2组GPS").pack()

        else:
            row["key"].set("406")
            point_count = int(fence_type)

            self.base_header_labels[5].configure(text="经度(多)-1")
            self.base_header_labels[7].configure(text="纬度(多)-1")
            self.base_header_labels[8].configure(text="经度")
            self.base_header_labels[9].configure(text="经度(多)-2")
            self.base_header_labels[10].configure(text="纬度")
            self.base_header_labels[11].configure(text="纬度(多)-2")
            self.base_header_labels[12].configure(text="说明")

            ttk.Combobox(col8, textvariable=row["gps"][1]["lon_dir"], values=["东经", "西经"], state="readonly", width=8).pack(fill="x")
            for key in ["gps2_lon", "gps2_lat_dir", "gps2_lat"]:
                row["widgets"][key].grid()

            col = 13
            for gps_no in range(3, point_count + 1):
                h1 = ttk.Label(self.klv_table, text="经度", relief="ridge", padding=5)
                h1.grid(row=0, column=col, sticky="nsew")
                w1 = ttk.Combobox(self.klv_table, textvariable=row["gps"][gps_no - 1]["lon_dir"], values=["东经", "西经"], state="readonly", width=8)
                w1.grid(row=row_index, column=col, padx=3, pady=3)
                col += 1

                h2 = ttk.Label(self.klv_table, text=f"经度(多)-{gps_no}", relief="ridge", padding=5)
                h2.grid(row=0, column=col, sticky="nsew")
                w2 = ttk.Entry(self.klv_table, textvariable=row["gps"][gps_no - 1]["lon"], width=14)
                w2.grid(row=row_index, column=col, padx=3, pady=3)
                col += 1

                h3 = ttk.Label(self.klv_table, text="纬度", relief="ridge", padding=5)
                h3.grid(row=0, column=col, sticky="nsew")
                w3 = ttk.Combobox(self.klv_table, textvariable=row["gps"][gps_no - 1]["lat_dir"], values=["南纬", "北纬"], state="readonly", width=8)
                w3.grid(row=row_index, column=col, padx=3, pady=3)
                col += 1

                h4 = ttk.Label(self.klv_table, text=f"纬度(多)-{gps_no}", relief="ridge", padding=5)
                h4.grid(row=0, column=col, sticky="nsew")
                w4 = ttk.Entry(self.klv_table, textvariable=row["gps"][gps_no - 1]["lat"], width=14)
                w4.grid(row=row_index, column=col, padx=3, pady=3)
                col += 1

                row["extra_widgets"].extend([h1, w1, h2, w2, h3, w3, h4, w4])

            ttk.Label(desc_col, text=f"多边形：{point_count}组GPS").pack(anchor="w")

    # ===================== 经纬度辅助转换 =====================
    def convert_coordinate(self):
        try:
            text = self.coord_input_var.get().strip()
            if not text:
                raise ValueError("请输入需要转换的经纬度")

            result = self.coordinate_to_decimal(text)
            self.coord_output_var.set(f"{result:.6f}")
        except Exception as e:
            messagebox.showerror("转换失败", str(e))

    def copy_coordinate(self):
        value = self.coord_output_var.get().strip()
        if not value:
            messagebox.showinfo("提示", "当前没有可复制的转换结果")
            return
        self.clipboard_clear()
        self.clipboard_append(value)
        messagebox.showinfo("提示", "转换结果已复制")

    def clear_coordinate(self):
        self.coord_input_var.set("")
        self.coord_output_var.set("")

    @staticmethod
    def coordinate_to_decimal(text):
        s = text.strip()
        negative = any(x in s for x in ["S", "s", "W", "w", "南", "西"])
        s = s.replace("°", " ").replace("′", " ").replace("'", " ").replace("″", " ").replace(chr(34), " ")
        s = s.replace("度", " ").replace("分", " ").replace("秒", " ")
        nums = re.findall("[0-9]+(?:[.][0-9]+)?", s)

        if len(nums) >= 3:
            degree = float(nums[0])
            minute = float(nums[1])
            second = float(nums[2])
            value = degree + minute / 60 + second / 3600
            return -value if negative else value

        if len(nums) == 1:
            raw = nums[0]
            if "." in raw:
                left, right = raw.split(".", 1)
            else:
                left, right = raw, ""

            if len(left) == 4:
                degree_part = left[:2]
                minute_part = left[2:]
            elif len(left) == 5:
                degree_part = left[:3]
                minute_part = left[3:]
            else:
                raise ValueError("度分分格式请使用 DDMM.mmmm 或 DDDMM.mmmm，例如：3411.3625 或 10852.76950")

            degree = float(degree_part)
            minute = float(minute_part + ("." + right if right else ""))
            value = degree + minute / 60
            return -value if negative else value

        if len(nums) == 2:
            degree = float(nums[0])
            minute = float(nums[1])
            value = degree + minute / 60
            return -value if negative else value

        raise ValueError("无法识别格式，支持：34°11′21.77″、34 11 21.77、3411.3625、34 11.3625")

    # ===================== 组包转换逻辑 =====================
    @staticmethod
    def dec_to_hex(value, byte_len, field_name):
        if value == "":
            raise ValueError(f"{field_name} 不能为空")
        n = int(value, 10)
        if n < 0 or n >= 256 ** byte_len:
            raise ValueError(f"{field_name} 超出 {byte_len} byte 范围")
        return f"{n:0{byte_len * 2}X}"

    @staticmethod
    def byte_len_hex(hex_string):
        if len(hex_string) % 2 != 0:
            raise ValueError("HEX 字符串长度必须为偶数")
        byte_len = len(hex_string) // 2
        if byte_len > 255:
            raise ValueError("长度超过1字节可表示范围")
        return f"{byte_len:02X}"

    @staticmethod
    def gps_to_hex(value, direction, is_lat=True):
        if value == "":
            raise ValueError("经纬度不能为空")

        text = value.strip()
        if text.startswith("+"):
            text = text[1:]
        if text.startswith("-"):
            raise ValueError("经纬度请输入正数，方向由东经/西经/南纬/北纬选择")

        if "." in text:
            int_part, frac_part = text.split(".", 1)
        else:
            int_part, frac_part = text, ""

        if not int_part.isdigit() or (frac_part and not frac_part.isdigit()):
            raise ValueError("经纬度格式非法")

        frac_part = (frac_part + "00000")[:5]
        n = int(int_part + frac_part)

        if n < 0 or n >= 2 ** 31:
            raise ValueError("经纬度数值超出范围")

        bits = bin(n)[2:].zfill(32)
        if is_lat:
            sign_bit = "0" if direction == "南纬" else "1"
        else:
            sign_bit = "0" if direction == "东经" else "1"

        bits = sign_bit + bits[1:]
        return f"{int(bits, 2):08X}"

    def gps_pair_hex(self, row, gps_index):
        gps = row["gps"][gps_index]
        lon = self.gps_to_hex(gps["lon"].get(), gps["lon_dir"].get(), is_lat=False)
        lat = self.gps_to_hex(gps["lat"].get(), gps["lat_dir"].get(), is_lat=True)
        return lon + lat

    def build_one_klv(self, row, idx):
        fence_id = self.dec_to_hex(row["fence_id"].get(), 1, f"第{idx}行 围栏ID")
        report_type = self.dec_to_hex(row["report_type"].get(), 1, f"第{idx}行 上报方式")
        fence_type_value = row["fence_type"].get()
        fence_type_hex = self.dec_to_hex(fence_type_value, 1, f"第{idx}行 围栏类型/点数")
        key = self.dec_to_hex(row["key"].get(), 2, f"第{idx}行 KEY")

        if fence_type_value == "01":
            gps1 = self.gps_pair_hex(row, 0)
            radius = self.dec_to_hex(row["radius"].get(), 3, f"第{idx}行 半径")
            first_packet = "0B" + gps1 + radius
            return fence_id + "10" + report_type + fence_type_hex + key + first_packet

        if fence_type_value == "02":
            gps_data = self.gps_pair_hex(row, 0) + self.gps_pair_hex(row, 1)
            first_packet = "10" + gps_data
            return fence_id + "15" + report_type + fence_type_hex + key + first_packet

        point_count = int(fence_type_value)
        gps_data = ""
        for gps_index in range(point_count):
            gps_data += self.gps_pair_hex(row, gps_index)

        first_len = self.byte_len_hex(gps_data)
        first_packet = first_len + gps_data

        second_body = report_type + fence_type_hex + key + first_packet
        second_len = self.byte_len_hex(second_body)
        return fence_id + second_len + second_body

    def build_packet(self):
        try:
            major_minor = self.major_minor_var.get().strip().upper()
            op_type = self.op_type_var.get().strip().upper()
            total_fence = self.dec_to_hex(self.total_fence_var.get(), 1, "待操作围栏总数")
            msg_index = self.dec_to_hex(self.msg_index_var.get(), 1, "此消息索引开始")
            msg_fence_count = self.dec_to_hex(self.msg_fence_count_var.get(), 1, "此消息中围栏总数")

            klv_packet = ""
            line_outputs = []
            for i, row in enumerate(self.klv_rows, start=1):
                one = self.build_one_klv(row, i)
                klv_packet += one
                line_outputs.append(f"第{i}行KLV: {one}")

            full_packet = major_minor + op_type + total_fence + msg_index + msg_fence_count + klv_packet

            self.output_text.delete("1.0", "end")
            self.output_text.insert("end", "\n".join(line_outputs))
            self.output_text.insert("end", "\n\n完整大包:\n")
            self.output_text.insert("end", full_packet)

        except Exception as e:
            messagebox.showerror("组包失败", str(e))

    def copy_result(self):
        text = self.output_text.get("1.0", "end").strip()
        if not text:
            messagebox.showinfo("提示", "当前没有可复制的结果")
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        messagebox.showinfo("提示", "结果已复制到剪贴板")


if __name__ == "__main__":
    app = KLVPacketBuilder()
    app.mainloop()
