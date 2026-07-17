import tkinter as tk
from tkinter import ttk, messagebox
from decimal import Decimal, ROUND_DOWN


class KLVPacketBuilder(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("电子围栏KLV 数据组包工具 - Mangetic 2026-5-7")
        self.geometry("1450x760")
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
        frame.pack(side="left", fill="x", expand=True)

        note_frame = ttk.LabelFrame(container, text="字段说明")
        note_frame.pack(side="right", fill="y", padx=(10, 0))

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
            ("此消息中围栏总数", ttk.Combobox(frame, textvariable=self.msg_fence_count_var, values=[str(i) for i in range(1, 11)], state="readonly")),
        ]

        for r, (label, widget) in enumerate(fields):
            ttk.Label(frame, text=label, width=18).grid(row=r, column=0, padx=8, pady=6, sticky="w")
            widget.grid(row=r, column=1, padx=8, pady=6, sticky="w")
            widget.configure(width=24)

        self.msg_fence_count_var.trace_add("write", lambda *_: self.rebuild_klv_rows())

        note_text = tk.Text(note_frame, width=42, height=14, wrap="word")
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

【围栏类型】
01：圆形
02：矩形

【经纬度方向】
经度：东经 / 西经
纬度：南纬 / 北纬

【KEY 自动规则】
围栏类型 01 → KEY=404
围栏类型 02 → KEY=405
"""

        note_text.insert("1.0", note_content)
        note_text.configure(state="disabled")

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

        canvas.pack(side="left", fill="both", expand=True)
        y_scroll.pack(side="right", fill="y")
        x_scroll.pack(side="bottom", fill="x")

    def _build_output_area(self):
        frame = ttk.LabelFrame(self, text="组包输出")
        frame.pack(fill="x", padx=10, pady=8)

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill="x", pady=4)

        ttk.Button(btn_frame, text="生成完整大包", command=self.build_packet).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="复制结果", command=self.copy_result).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="清空输出", command=lambda: self.output_text.delete("1.0", "end")).pack(side="left", padx=5)

        self.output_text = tk.Text(frame, height=8, wrap="word")
        self.output_text.pack(fill="x", padx=5, pady=6)

    def rebuild_klv_rows(self):
        for child in self.klv_table.winfo_children():
            child.destroy()
        self.klv_rows.clear()

        headers = [
            "围栏ID", "上报方式", "围栏类型", "KEY",
            "经度", "经度/经度(圆)", "纬度", "纬度/纬度(圆)",
            "半径/经度", "经度(方)", "纬度", "纬度(方)"
        ]

        for c, h in enumerate(headers):
            ttk.Label(self.klv_table, text=h, relief="ridge", padding=5).grid(row=0, column=c, sticky="nsew")

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
            "key": tk.StringVar(),
            "lon_dir1": tk.StringVar(value="东经"),
            "lon1": tk.StringVar(),
            "lat_dir1": tk.StringVar(value="北纬"),
            "lat1": tk.StringVar(),
            "radius_or_lon_dir2": tk.StringVar(),
            "lon2": tk.StringVar(),
            "lat_dir2": tk.StringVar(value="北纬"),
            "lat2": tk.StringVar(),
            "widgets": {}
        }

        def entry(col, var, width=12):
            w = ttk.Entry(self.klv_table, textvariable=var, width=width)
            w.grid(row=row_index, column=col, padx=3, pady=3, sticky="ew")
            return w

        def combo(col, var, values, width=10):
            w = ttk.Combobox(self.klv_table, textvariable=var, values=values, state="readonly", width=width)
            w.grid(row=row_index, column=col, padx=3, pady=3, sticky="ew")
            return w

        entry(0, row["fence_id"], 10)
        combo(1, row["report_type"], ["00", "01", "02", "03"], 8)
        fence_type_box = combo(2, row["fence_type"], ["01", "02"], 8)
        key_entry = entry(3, row["key"], 10)
        key_entry.configure(state="readonly")
        combo(4, row["lon_dir1"], ["东经", "西经"], 8)
        row["widgets"]["lon1"] = entry(5, row["lon1"], 14)
        combo(6, row["lat_dir1"], ["南纬", "北纬"], 8)
        row["widgets"]["lat1"] = entry(7, row["lat1"], 14)

        row["widgets"]["col8"] = ttk.Entry(self.klv_table, textvariable=row["radius_or_lon_dir2"], width=12)
        row["widgets"]["col8"].grid(row=row_index, column=8, padx=3, pady=3, sticky="ew")

        row["widgets"]["lon2"] = entry(9, row["lon2"], 14)
        row["widgets"]["lat_dir2"] = combo(10, row["lat_dir2"], ["南纬", "北纬"], 8)
        row["widgets"]["lat2"] = entry(11, row["lat2"], 14)

        def on_type_change(*_):
            self.refresh_row_by_type(row)

        row["fence_type"].trace_add("write", on_type_change)
        self.klv_rows.append(row)
        self.refresh_row_by_type(row)

    def refresh_row_by_type(self, row):
        fence_type = row["fence_type"].get()

        # KEY 不再手动输入：围栏类型 01 => 404，围栏类型 02 => 405
        row["key"].set("404" if fence_type == "01" else "405")

        for child in self.klv_table.grid_slaves(row=self.klv_rows.index(row) + 1, column=8):
            child.destroy()

        if fence_type == "01":
            row["radius_or_lon_dir2"].set(row["radius_or_lon_dir2"].get())
            w = ttk.Entry(self.klv_table, textvariable=row["radius_or_lon_dir2"], width=12)
            w.grid(row=self.klv_rows.index(row) + 1, column=8, padx=3, pady=3, sticky="ew")
            row["widgets"]["col8"] = w

            for key in ["lon2", "lat_dir2", "lat2"]:
                row["widgets"][key].grid_remove()
        else:
            if row["radius_or_lon_dir2"].get() not in ["东经", "西经"]:
                row["radius_or_lon_dir2"].set("东经")
            w = ttk.Combobox(self.klv_table, textvariable=row["radius_or_lon_dir2"], values=["东经", "西经"], state="readonly", width=8)
            w.grid(row=self.klv_rows.index(row) + 1, column=8, padx=3, pady=3, sticky="ew")
            row["widgets"]["col8"] = w

            for key in ["lon2", "lat_dir2", "lat2"]:
                row["widgets"][key].grid()

    # ===================== 转换逻辑 =====================
    @staticmethod
    def dec_to_hex(value, byte_len, field_name):
        if value == "":
            raise ValueError(f"{field_name} 不能为空")
        n = int(value, 10)
        if n < 0 or n >= 256 ** byte_len:
            raise ValueError(f"{field_name} 超出 {byte_len} byte 范围")
        return f"{n:0{byte_len * 2}X}"

    @staticmethod
    def gps_to_hex(value, direction, is_lat=True):
        if value == "":
            raise ValueError("经纬度不能为空")

        # 经纬度处理规则：
        # 1. 不四舍五入，直接截取到小数点后 5 位；不足 5 位补 0
        # 2. 去掉小数点作为整数
        # 示例：34.1234567 => 34.12345 => 3412345
        # 示例：34.123 => 34.12300 => 3412300
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

    def build_one_klv(self, row, idx):
        fence_id = self.dec_to_hex(row["fence_id"].get(), 1, f"第{idx}行 围栏ID")
        report_type = self.dec_to_hex(row["report_type"].get(), 1, f"第{idx}行 上报方式")
        fence_type = self.dec_to_hex(row["fence_type"].get(), 1, f"第{idx}行 围栏类型")
        key = self.dec_to_hex(row["key"].get(), 2, f"第{idx}行 KEY")

        if row["fence_type"].get() == "01":
            lon = self.gps_to_hex(row["lon1"].get(), row["lon_dir1"].get(), is_lat=False)
            lat = self.gps_to_hex(row["lat1"].get(), row["lat_dir1"].get(), is_lat=True)
            radius = self.dec_to_hex(row["radius_or_lon_dir2"].get(), 3, f"第{idx}行 半径")

            first_packet = "0B" + lon + lat + radius
            second_packet = fence_id + "10" + report_type + fence_type + key + first_packet
            return second_packet

        if row["fence_type"].get() == "02":
            lon1 = self.gps_to_hex(row["lon1"].get(), row["lon_dir1"].get(), is_lat=False)
            lat1 = self.gps_to_hex(row["lat1"].get(), row["lat_dir1"].get(), is_lat=True)
            lon2 = self.gps_to_hex(row["lon2"].get(), row["radius_or_lon_dir2"].get(), is_lat=False)
            lat2 = self.gps_to_hex(row["lat2"].get(), row["lat_dir2"].get(), is_lat=True)

            first_packet = "10" + lon1 + lat1 + lon2 + lat2
            second_packet = fence_id + "15" + report_type + fence_type + key + first_packet
            return second_packet

        raise ValueError(f"第{idx}行 围栏类型非法")

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
