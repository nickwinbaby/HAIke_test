"""数据分析综合工具箱主窗口。"""

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
from ui.general_tools import DataConversionPanel, FileComparisonPanel, Md5Panel


class AngledNavigation(tk.Canvas):
    """平行四边形主体加分离斜杠的一级功能导航。"""

    HEIGHT = 42
    SLOPE = 10

    def __init__(self, master, items, command):
        super().__init__(
            master,
            height=self.HEIGHT,
            background="#eef3f8",
            borderwidth=0,
            highlightthickness=0,
            takefocus=False,
        )
        self.items = tuple(items)
        self.command = command
        self.selected_key = self.items[0][0] if self.items else None
        self.hover_key = None
        self._hit_regions = []
        self._tab_images = []
        self.bind("<Configure>", self._redraw)
        self.bind("<Button-1>", self._on_click)
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", self._on_leave)

    def select(self, key):
        if key == self.selected_key:
            return
        self.selected_key = key
        self._redraw()

    def _tab_width(self, label):
        # 这里只返回主体宽度；右侧三道分离斜杠另占空间。
        text_units = sum(2 if ord(character) > 127 else 1 for character in label)
        return max(98, 38 + text_units * 7)

    def _redraw(self, _event=None):
        self.delete("all")
        self._hit_regions = []
        self._tab_images = []
        x = 5
        top, bottom = 3, self.HEIGHT - 3
        for key, label in self.items:
            body_width = self._tab_width(label)
            selected = key == self.selected_key
            hovered = key == self.hover_key and not selected
            fill = "#405fbd" if selected else "#e3edf5" if hovered else "#f7fafc"
            outline = "#405fbd" if selected else "#8faabd" if hovered else "#b8c7d2"
            text_color = "#ffffff" if selected else "#26475c"
            # 三道斜杠与主体分开，并使用由蓝到青绿的颜色序列。
            accent_colors = (
                ("#4967c8", "#42bed0", "#8ae6bd")
                if selected or hovered
                else ("#9aabc2", "#a8bec8", "#b7cfc8")
            )
            # 第一条斜杠贴近主体切边，只留约 1～3 px 的视觉缝隙。
            accent_start = body_width - 7
            accent_width = 5
            accent_gap = 2
            group_width = accent_start + 2 * (accent_width + accent_gap) + self.SLOPE + accent_width

            # Canvas多边形不做抗锯齿，因此先用4倍尺寸绘制透明位图，
            # 再通过LANCZOS缩回实际尺寸，获得平滑的斜边。
            scale = 4
            tab_image = Image.new(
                "RGBA", (group_width * scale + 2, self.HEIGHT * scale), (0, 0, 0, 0)
            )
            draw = ImageDraw.Draw(tab_image)

            def scaled(points):
                return [(round(px * scale), round(py * scale)) for px, py in points]

            body_points = [
                (self.SLOPE, top),
                (body_width, top),
                (body_width - self.SLOPE, bottom),
                (0, bottom),
            ]
            draw.polygon(scaled(body_points), fill=fill)
            draw.line(
                scaled(body_points + [body_points[0]]),
                fill=outline,
                width=scale,
                joint="curve",
            )
            for index, accent in enumerate(accent_colors):
                start_x = accent_start + index * (accent_width + accent_gap)
                accent_points = [
                    (start_x + self.SLOPE, top),
                    (start_x + self.SLOPE + accent_width, top),
                    (start_x + accent_width, bottom),
                    (start_x, bottom),
                ]
                draw.polygon(scaled(accent_points), fill=accent)
            tab_image = tab_image.resize(
                (group_width + 1, self.HEIGHT), Image.Resampling.LANCZOS
            )
            photo = ImageTk.PhotoImage(tab_image)
            self._tab_images.append(photo)
            self.create_image(x, 0, image=photo, anchor="nw")
            self.create_text(
                x + body_width / 2,
                (top + bottom) / 2,
                text=label,
                fill=text_color,
                font=("Microsoft YaHei UI", 9, "bold" if selected else "normal"),
            )
            group_right = x + group_width
            self._hit_regions.append((x, group_right, key))
            x = group_right + 5
        self.configure(scrollregion=(0, 0, max(x, self.winfo_width()), self.HEIGHT))

    def _key_at(self, x):
        for left, right, key in self._hit_regions:
            if left <= x <= right:
                return key
        return None

    def _on_click(self, event):
        key = self._key_at(event.x)
        if key is not None and key != self.selected_key:
            self.selected_key = key
            self._redraw()
            self.command(key)

    def _on_motion(self, event):
        key = self._key_at(event.x)
        if key != self.hover_key:
            self.hover_key = key
            self.configure(cursor="hand2" if key is not None else "")
            self._redraw()

    def _on_leave(self, _event):
        if self.hover_key is not None:
            self.hover_key = None
            self.configure(cursor="")
            self._redraw()


class GnssToolsPanel(ttk.Frame):
    """GNSS 工具一级菜单，承载原有工具目录和全部功能页面。"""

    def __init__(self, master):
        super().__init__(master, style="Page.TFrame")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.notebook = ttk.Notebook(self, style="Tools.TNotebook", takefocus=False)
        self.notebook.grid(row=0, column=0, sticky="nsew")
        self.pages = [
            ("KML生成", KmlGenerationPanel(self.notebook)),
            ("CEP 分析", CepPanel(self.notebook)),
            ("冷热启动", ColdStartPanel(self.notebook)),
            ("电子围栏", ElectronicFencePanel(self.notebook)),
            ("地图标点", MapPointPanel(self.notebook)),
            ("轨迹查看", TrackViewerPanel(self.notebook)),
            ("坐标转换", CoordinatePanel(self.notebook)),
        ]
        for label, page in self.pages:
            self.notebook.add(page, text=label)


class GpsToolsApp(tk.Tk):
    def __init__(self):
        self._set_windows_app_id()
        super().__init__()
        china_today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
        self.title(
            f"Richlink Data Toolbox {china_today} "
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
        icon_path = self._resource_path("photo", "All_purpose_tool.ico")
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
        # LabelFrame内部使用的普通容器必须显式指定底色，否则clam主题会退回灰底。
        style.configure("Section.TFrame", background="#f8fafc")
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
        style.configure(
            "Hash.Horizontal.TProgressbar",
            background="#1677a8",
            troughcolor="#e6edf3",
            bordercolor="#e6edf3",
            lightcolor="#1677a8",
            darkcolor="#1677a8",
            thickness=8,
        )
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
        # 一级菜单由 AngledNavigation 自绘；Notebook 仅负责承载页面，隐藏系统页签。
        style.configure("PrimaryPages.TNotebook", background="#eef3f8", borderwidth=0, tabmargins=0)
        style.layout("PrimaryPages.TNotebook.Tab", [])
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
            header, text="数据处理 · 文件对比 · 校验计算 · GNSS 工具",
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

        # 最外层使用独立斜角一级菜单；下方系统Notebook只负责页面切换且隐藏页签。
        # GNSS内部仍使用矩形二级页签，使一、二级菜单在形态和配色上明确区分。
        main_area = ttk.Frame(root, style="Root.TFrame")
        main_area.pack(fill="both", expand=True, padx=16, pady=(12, 16))
        main_area.columnconfigure(0, weight=1)
        main_area.rowconfigure(1, weight=1)

        primary_items = (
            ("gnss", "GNSS工具"),
            ("convert", "数据处理"),
            ("compare", "文件对比"),
            ("md5", "哈希算法"),
        )
        self.primary_navigation = AngledNavigation(main_area, primary_items, self._show_primary_page)
        self.primary_navigation.grid(row=0, column=0, sticky="ew")

        self.main_notebook = ttk.Notebook(main_area, style="PrimaryPages.TNotebook", takefocus=False)
        self.main_notebook.grid(row=1, column=0, sticky="nsew")
        self.gnss_tools_panel = GnssToolsPanel(self.main_notebook)
        self.data_conversion_panel = DataConversionPanel(self.main_notebook)
        self.file_comparison_panel = FileComparisonPanel(self.main_notebook)
        self.md5_panel = Md5Panel(self.main_notebook)
        self.main_notebook.add(self.gnss_tools_panel, text="GNSS工具")
        self.main_notebook.add(self.data_conversion_panel, text="数据转换")
        self.main_notebook.add(self.file_comparison_panel, text="文件对比")
        self.main_notebook.add(self.md5_panel, text="哈希算法")
        self.primary_pages = {
            "gnss": self.gnss_tools_panel,
            "convert": self.data_conversion_panel,
            "compare": self.file_comparison_panel,
            "md5": self.md5_panel,
        }
        self._show_primary_page("gnss")

    def _show_primary_page(self, key):
        page = self.primary_pages[key]
        self.main_notebook.select(page)
        self.primary_navigation.select(key)

    def open_external_comparison(self, paths):
        """供资源管理器右键菜单调用：直接打开独立对比窗口。"""
        paths = tuple(path for path in paths if path)
        if len(paths) != 2:
            from tkinter import messagebox
            messagebox.showwarning("无法对比", "请在资源管理器中同时选择两个文件或两个文件夹。", parent=self)
            return
        left, right = (Path(path) for path in paths)
        if left.is_file() and right.is_file():
            mode = FileComparisonPanel.TYPE_FILE
        elif left.is_dir() and right.is_dir():
            mode = FileComparisonPanel.TYPE_FOLDER
        else:
            from tkinter import messagebox
            messagebox.showwarning("类型不一致", "请选择两个文件，或选择两个文件夹；不能混合选择。", parent=self)
            return
        panel = self.file_comparison_panel
        panel._external_compare_mode = True
        panel.mode_var.set(mode)
        panel.left_var.set(str(left))
        panel.right_var.set(str(right))
        panel._mode_changed()
        self.withdraw()
        panel.open_detached_window()
        detached = panel._detached_panel
        if detached is not None:
            detached.refresh_comparison()


def run(compare_paths=None):
    app = GpsToolsApp()
    app._external_compare_mode = False
    if compare_paths:
        app.after_idle(lambda: app.open_external_comparison(compare_paths))
    app.mainloop()

