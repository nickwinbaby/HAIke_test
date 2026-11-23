"""GNSS 综合工具箱主窗口。"""

from pathlib import Path
import ctypes
from datetime import datetime, timedelta, timezone
import sys
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageDraw, ImageTk

from config import APP_TITLE, APP_USER_MODEL_ID, APP_VERSION
from ui.panels import (
    ColdStartPanel,
    CoordinatePanel,
    CepPanel,
    ElectronicFencePanel,
    KmlGenerationPanel,
    MapPointPanel,
    TrackViewerPanel,
)


class GpsToolsApp(tk.Tk):
    def __init__(self):
        self._set_windows_app_id()
        super().__init__()
        china_today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
        self.title(
            f"Richlink GNSS Comprehensive Toolbox {china_today} "
            "※瑞联内部工具，谢绝外发※ guomengyao@gosuncn.com"
        )
        self.geometry("980x720")
        self.minsize(760, 480)
        self.configure(bg="#eef3f8")
        self._window_icon_image = None
        self._native_icon_handles = []
        self._header_logo_image = None
        self._header_logo_label = None
        self._header_logo_height = 0
        self._checkmark_images = []
        self._configure_window_icon()
        self._configure_style()
        self._build_ui()

    @staticmethod
    def _set_windows_app_id():
        """让任务栏把本工具识别为独立应用，而不是 Python 进程。"""
        if sys.platform != "win32":
            return
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
        except (AttributeError, OSError):
            pass

    @staticmethod
    def _resource_path(*parts):
        """获取开发环境或 PyInstaller 打包后的资源路径。"""
        base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
        return base_dir.joinpath(*parts)

    def _configure_window_icon(self):
        """同时设置标题栏、小窗口和 Windows 任务栏运行图标。"""
        icon_path = self._resource_path("photo", "gps_tools_all.ico")
        if not icon_path.is_file():
            return
        try:
            # iconphoto 作为 Tk/PyInstaller 环境的补充，并保持对象生命周期。
            icon_image = Image.open(icon_path).convert("RGBA")
            self._window_icon_image = ImageTk.PhotoImage(icon_image)
            self.iconphoto(True, self._window_icon_image)
        except (OSError, ValueError, tk.TclError):
            pass
        if sys.platform == "win32":
            try:
                # Tk 的 iconbitmap 在部分 Windows/Tk 版本中只设置默认图标，
                # 不会更新当前 HWND。因此再通过 Win32 WM_SETICON 直接设置当前窗口。
                user32 = ctypes.windll.user32
                load_image = user32.LoadImageW
                load_image.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint,
                                       ctypes.c_int, ctypes.c_int, ctypes.c_uint]
                load_image.restype = ctypes.c_void_p
                send_message = user32.SendMessageW
                send_message.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                         ctypes.c_void_p, ctypes.c_void_p]
                send_message.restype = ctypes.c_void_p
                # IMAGE_ICON=1, LR_LOADFROMFILE=0x10；分别给标题栏和任务栏加载合适尺寸。
                handles = [
                    load_image(None, str(icon_path), 1, 16, 16, 0x10),
                    load_image(None, str(icon_path), 1, 32, 32, 0x10),
                ]
                self._native_icon_handles = [h for h in handles if h]
                self._apply_native_window_icons()
                # Tk 的外层顶级窗口通常在空闲阶段才完成创建，再补设一次。
                self.after_idle(self._apply_native_window_icons)
            except (AttributeError, OSError, TypeError):
                pass

    def _apply_native_window_icons(self):
        """将已加载的图标句柄写入 Tk 子窗口和真正的 Windows 顶级窗口。"""
        if sys.platform != "win32" or len(self._native_icon_handles) < 2:
            return
        try:
            user32 = ctypes.windll.user32
            get_ancestor = user32.GetAncestor
            get_ancestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
            get_ancestor.restype = ctypes.c_void_p
            send_message = user32.SendMessageW
            send_message.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                     ctypes.c_void_p, ctypes.c_void_p]
            send_message.restype = ctypes.c_void_p
            child_hwnd = self.winfo_id()
            root_hwnd = get_ancestor(child_hwnd, 2)  # GA_ROOT
            targets = {child_hwnd, root_hwnd}
            for target_hwnd in targets:
                if not target_hwnd:
                    continue
                for icon_handle, icon_type in zip(self._native_icon_handles, (0, 1)):
                    send_message(target_hwnd, 0x0080, icon_type, icon_handle)  # WM_SETICON
        except (AttributeError, OSError, TypeError, tk.TclError):
            pass

    def _load_header_logo(self, header_height):
        """按 Header 可用高度等比缩放 Mangetic 透明图。"""
        image_path = self._resource_path("photo", "Mangetic.png")
        if not image_path.is_file():
            return None
        try:
            image = Image.open(image_path).convert("RGBA")
            # 仅剔除近乎透明的外围像素，并保留安全边距；不裁切有效笔触。
            alpha = image.getchannel("A")
            visible_mask = alpha.point(lambda value: 255 if value >= 40 else 0)
            box = visible_mask.getbbox()
            if box:
                padding = max(8, int(min(image.size) * 0.015))
                box = (
                    max(0, box[0] - padding),
                    max(0, box[1] - padding),
                    min(image.width, box[2] + padding),
                    min(image.height, box[3] + padding),
                )
                image = image.crop(box)

            # 高度与 Header 实际高度匹配，宽度完全按原图比例计算。
            target_height = min(84, max(32, header_height - 16))
            scale = target_height / image.height
            target_width = max(1, round(image.width * scale))
            image = image.resize((target_width, target_height), Image.Resampling.LANCZOS)
            return ImageTk.PhotoImage(image)
        except (OSError, ValueError):
            return None

    def _refresh_header_logo(self, event=None):
        """窗口完成布局后按当前 Header 高度刷新 Logo，避免上下被裁切。"""
        if self._header_logo_label is None:
            return
        header_height = event.height if event is not None else self._header_logo_label.master.winfo_height()
        if header_height <= 0 or header_height == self._header_logo_height:
            return
        image = self._load_header_logo(header_height)
        if image is None:
            return
        self._header_logo_height = header_height
        self._header_logo_image = image
        self._header_logo_label.configure(image=image)

    def _configure_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", font=("Microsoft YaHei UI", 10))
        style.configure("Root.TFrame", background="#eef3f8")
        style.configure("Page.TFrame", background="#f8fafc")
        # 普通文字直接融入页面底色，避免每个字段名和结果文字都出现灰色块。
        style.configure("TLabel", background="#f8fafc", foreground="#243746")
        style.configure("Hint.TLabel", background="#f8fafc", foreground="#7b8794")
        # 只读下拉框保持白色输入区域，不使用 clam 主题默认的灰底。
        style.configure(
            "TCombobox",
            fieldbackground="#ffffff",
            background="#ffffff",
            foreground="#243746",
            arrowcolor="#475569",
        )
        style.configure(
            "ProtocolReadonly.TEntry",
            fieldbackground="#f8fafc",
            foreground="#334155",
            borderwidth=0,
            relief="flat",
        )
        style.map(
            "ProtocolReadonly.TEntry",
            fieldbackground=[("readonly", "#f8fafc"), ("focus", "#f8fafc")],
            foreground=[("readonly", "#334155"), ("focus", "#334155")],
            bordercolor=[("readonly", "#f8fafc"), ("focus", "#f8fafc")],
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", "#ffffff")],
            background=[("readonly", "#ffffff")],
            foreground=[("readonly", "#243746")],
            selectbackground=[("readonly", "#ffffff")],
            selectforeground=[("readonly", "#243746")],
        )
        style.configure("Header.TFrame", background="#12344d")
        style.configure(
            "HeaderTitle.TLabel", background="#12344d", foreground="#ffffff",
            font=("Microsoft YaHei UI", 20, "bold"),
        )
        style.configure(
            "HeaderSub.TLabel", background="#12344d", foreground="#bcd8e8",
            font=("Microsoft YaHei UI", 10),
        )
        style.configure(
            "PageTitle.TLabel", background="#f8fafc", foreground="#12344d",
            font=("Microsoft YaHei UI", 17, "bold"),
        )
        style.configure("PageSubtitle.TLabel", background="#f8fafc", foreground="#64748b")
        style.configure("Section.TLabelframe", background="#f8fafc", borderwidth=1, relief="solid")
        style.configure(
            "Section.TLabelframe.Label", background="#f8fafc", foreground="#23445c",
            font=("Microsoft YaHei UI", 10, "bold"),
        )
        style.configure("Status.TLabel", background="#f8fafc", foreground="#087f5b")
        style.configure("Primary.TButton", font=("Microsoft YaHei UI", 10, "bold"), padding=(16, 8))

        # clam 主题会在获得键盘焦点的按钮文字周围画虚线框。
        # 保留按钮边框、按压和键盘操作，只移除这层焦点虚线绘制。
        button_layout = [
            ("Button.border", {
                "sticky": "nswe",
                "border": "1",
                "children": [
                    ("Button.padding", {
                        "sticky": "nswe",
                        "children": [("Button.label", {"sticky": "nswe"})],
                    }),
                ],
            }),
        ]
        style.layout("TButton", button_layout)
        style.layout("Primary.TButton", button_layout)

        # 页签去掉系统默认的虚线焦点框；选中与未选中保持同一高度，
        # 仅用配色、粗体和轻微宽度变化区分状态，避免页签上下错位。
        style.layout(
            "Tools.TNotebook.Tab",
            [("Notebook.tab", {
                "sticky": "nswe",
                "children": [("Notebook.padding", {
                    "side": "top", "sticky": "nswe",
                    "children": [("Notebook.label", {"side": "top", "sticky": ""})],
                })],
            })],
        )
        style.configure("Tools.TNotebook", background="#eef3f8", borderwidth=0, tabmargins=(0, 8, 0, 0))
        style.configure(
            "Tools.TNotebook.Tab",
            padding=(12, 9),
            font=("Microsoft YaHei UI", 10),
            background="#e6ebf1",
            foreground="#334155",
            borderwidth=1,
            relief="flat",
        )
        style.map(
            "Tools.TNotebook.Tab",
            padding=[("selected", (15, 9)), ("!selected", (12, 9))],
            font=[
                ("selected", ("Microsoft YaHei UI", 10, "bold")),
                ("!selected", ("Microsoft YaHei UI", 10)),
            ],
            background=[("selected", "#1677a8"), ("active", "#d8e8f2"), ("!selected", "#e6ebf1")],
            foreground=[("selected", "#ffffff"), ("active", "#0f4c6e"), ("!selected", "#475569")],
            bordercolor=[("selected", "#1677a8"), ("active", "#9abed2"), ("!selected", "#c6ced8")],
            lightcolor=[("selected", "#1677a8"), ("!selected", "#e6ebf1")],
            darkcolor=[("selected", "#1677a8"), ("!selected", "#c6ced8")],
        )
        # 单选框、复选框保留指示器，但移除获得焦点时包住文字的虚线框。
        style.layout(
            "Clean.TRadiobutton",
            [("Radiobutton.padding", {
                "sticky": "nswe",
                "children": [
                    ("Radiobutton.indicator", {"side": "left", "sticky": ""}),
                    ("Radiobutton.label", {"side": "left", "sticky": "nswe"}),
                ],
            })],
        )
        style.configure("Clean.TRadiobutton", background="#f8fafc", font=("Microsoft YaHei UI", 10))
        style.map("Clean.TRadiobutton", background=[("active", "#f8fafc")])
        # clam 主题默认用“×”表示复选框选中。创建一套标准的“✓”指示器，
        # 并由 Clean.TCheckbutton 统一使用。
        unchecked = Image.new("RGBA", (18, 18), (0, 0, 0, 0))
        unchecked_draw = ImageDraw.Draw(unchecked)
        unchecked_draw.rounded_rectangle(
            (2, 2, 15, 15), radius=2, fill="#ffffff", outline="#64748b", width=1
        )
        checked = Image.new("RGBA", (18, 18), (0, 0, 0, 0))
        checked_draw = ImageDraw.Draw(checked)
        checked_draw.rounded_rectangle(
            (2, 2, 15, 15), radius=2, fill="#1677a8", outline="#1677a8", width=1
        )
        checked_draw.line(
            ((5, 9), (8, 12), (13, 6)), fill="#ffffff", width=2, joint="curve"
        )
        unchecked_image = ImageTk.PhotoImage(unchecked)
        checked_image = ImageTk.PhotoImage(checked)
        self._checkmark_images = [unchecked_image, checked_image]
        try:
            style.element_create(
                "Checkmark.indicator", "image", unchecked_image, ("selected", checked_image)
            )
        except tk.TclError:
            # 同一 Tcl 解释器中重复初始化窗口时，元素可能已经存在。
            pass

        style.layout(
            "Clean.TCheckbutton",
            [("Checkbutton.padding", {
                "sticky": "nswe",
                "children": [
                    ("Checkmark.indicator", {"side": "left", "sticky": ""}),
                    ("Checkbutton.label", {"side": "left", "sticky": "nswe"}),
                ],
            })],
        )
        style.configure("Clean.TCheckbutton", background="#f8fafc", font=("Microsoft YaHei UI", 10))
        style.map("Clean.TCheckbutton", background=[("active", "#f8fafc")])

    def _build_ui(self):
        root = ttk.Frame(self, style="Root.TFrame")
        root.pack(fill="both", expand=True)

        header = ttk.Frame(root, style="Header.TFrame", padding=(24, 16))
        header.pack(fill="x")
        ttk.Label(header, text=APP_TITLE, style="HeaderTitle.TLabel").pack(anchor="w")
        ttk.Label(
            header, text="GNSS 数据处理 · 地图选点 · 电子围栏 · 功能完整内置",
            style="HeaderSub.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        # 直接悬浮在 Header 深蓝底色上，不参与 pack/grid，不额外占用布局空间。
        self.update_idletasks()
        self._header_logo_image = self._load_header_logo(72)
        if self._header_logo_image is not None:
            logo = tk.Label(
                header,
                image=self._header_logo_image,
                background="#12344d",
                borderwidth=0,
                highlightthickness=0,
            )
            logo.place(relx=1.0, rely=0.5, x=-4, y=0, anchor="e")
            self._header_logo_label = logo
            header.bind("<Configure>", self._refresh_header_logo, add="+")
            self.after_idle(self._refresh_header_logo)

        notebook = ttk.Notebook(root, style="Tools.TNotebook", takefocus=False)
        notebook.pack(fill="both", expand=True, padx=16, pady=16)
        pages = [
            ("KML生成", KmlGenerationPanel(notebook)),
            ("CEP 分析", CepPanel(notebook)),
            ("冷热启动", ColdStartPanel(notebook)),
            ("电子围栏", ElectronicFencePanel(notebook)),
            ("地图标点", MapPointPanel(notebook)),
            ("轨迹查看", TrackViewerPanel(notebook)),
            ("坐标转换", CoordinatePanel(notebook)),
        ]
        for label, page in pages:
            notebook.add(page, text=label)


def run():
    GpsToolsApp().mainloop()

