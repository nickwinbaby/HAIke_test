import os
import sys
import io
import struct
import tkinter as tk
from tkinter import filedialog, messagebox

try:
    from PIL import Image, ImageFilter
except ImportError:
    Image = None
    ImageFilter = None


ICON_SIZES = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]


def resource_path(relative_path):
    """Return the correct path when running as a PyInstaller executable."""
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


def make_square_rgba(image):
    """Pad image to a transparent square canvas without stretching it."""
    image = image.convert("RGBA")
    width, height = image.size
    side = max(width, height)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    x = (side - width) // 2
    y = (side - height) // 2
    canvas.paste(image, (x, y), image)
    return canvas


def get_lanczos_filter():
    return getattr(getattr(Image, "Resampling", Image), "LANCZOS")


def render_icon_size(image, size):
    """Render one high-quality square icon layer."""
    rendered = image.resize((size, size), get_lanczos_filter())

    # Small icon layers lose edge contrast easily after downscaling.
    # A light unsharp mask improves clarity without making 256px noisy.
    if size <= 64:
        rendered = rendered.filter(ImageFilter.UnsharpMask(radius=0.6, percent=130, threshold=3))

    return rendered


def save_png_layers_as_ico(image, ico_path):
    """
    Write an ICO file manually using PNG-compressed layers.
    This keeps each icon size crisp and avoids low-quality automatic resizing.
    """
    layers = []

    for width, height in ICON_SIZES:
        size = min(width, height)
        layer = render_icon_size(image, size)
        buffer = io.BytesIO()
        layer.save(buffer, format="PNG", optimize=True)
        layers.append((size, size, buffer.getvalue()))

    header = struct.pack("<HHH", 0, 1, len(layers))
    directory = bytearray()
    image_data = bytearray()
    offset = 6 + 16 * len(layers)

    for width, height, data in layers:
        directory.extend(struct.pack(
            "<BBBBHHII",
            0 if width >= 256 else width,
            0 if height >= 256 else height,
            0,
            0,
            1,
            32,
            len(data),
            offset
        ))
        image_data.extend(data)
        offset += len(data)

    with open(ico_path, "wb") as f:
        f.write(header)
        f.write(directory)
        f.write(image_data)


def convert_png_to_ico(png_path, ico_path):
    if Image is None:
        raise RuntimeError("缺少 Pillow 库，请先安装：pip install pillow")

    if not png_path:
        raise ValueError("请先选择 PNG 文件")

    if not ico_path:
        raise ValueError("请先选择 ICO 输出路径")

    if not os.path.isfile(png_path):
        raise FileNotFoundError(f"PNG 文件不存在：{png_path}")

    if not png_path.lower().endswith(".png"):
        raise ValueError("输入文件必须是 PNG 格式")

    if not ico_path.lower().endswith(".ico"):
        ico_path += ".ico"

    out_dir = os.path.dirname(os.path.abspath(ico_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with Image.open(png_path) as img:
        square_img = make_square_rgba(img)
        save_png_layers_as_ico(square_img, ico_path)

    return ico_path


class PngToIcoApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PNG 转 ICO 工具")
        self.geometry("720x230")
        self.resizable(False, False)

        self.png_var = tk.StringVar()
        self.ico_var = tk.StringVar()
        self.status_var = tk.StringVar(value="请选择 PNG 文件和 ICO 输出路径")

        self.build_ui()

    def build_ui(self):
        root = tk.Frame(self, padx=16, pady=16)
        root.pack(fill=tk.BOTH, expand=True)

        tk.Label(root, text="PNG 文件：", anchor="w", width=12).grid(row=0, column=0, sticky="w", pady=8)
        tk.Entry(root, textvariable=self.png_var, width=72).grid(row=0, column=1, sticky="we", pady=8)
        tk.Button(root, text="选择PNG", width=12, command=self.select_png).grid(row=0, column=2, padx=(8, 0), pady=8)

        tk.Label(root, text="ICO 输出：", anchor="w", width=12).grid(row=1, column=0, sticky="w", pady=8)
        tk.Entry(root, textvariable=self.ico_var, width=72).grid(row=1, column=1, sticky="we", pady=8)
        tk.Button(root, text="选择路径", width=12, command=self.select_ico).grid(row=1, column=2, padx=(8, 0), pady=8)

        button_row = tk.Frame(root)
        button_row.grid(row=2, column=0, columnspan=3, sticky="e", pady=(18, 8))

        tk.Button(button_row, text="转换", width=14, command=self.convert).pack(side=tk.LEFT, padx=(0, 8))
        tk.Button(button_row, text="退出", width=14, command=self.destroy).pack(side=tk.LEFT)

        status = tk.Label(root, textvariable=self.status_var, anchor="w", fg="#2368a2")
        status.grid(row=3, column=0, columnspan=3, sticky="we", pady=(12, 0))

        root.columnconfigure(1, weight=1)

    def select_png(self):
        path = filedialog.askopenfilename(
            title="选择 PNG 文件",
            filetypes=[("PNG 图片", "*.png"), ("所有文件", "*.*")]
        )
        if not path:
            return

        self.png_var.set(path)

        if not self.ico_var.get().strip():
            base = os.path.splitext(os.path.basename(path))[0]
            default_ico = os.path.join(os.path.dirname(path), base + ".ico")
            self.ico_var.set(default_ico)

        self.status_var.set("已选择 PNG 文件")

    def select_ico(self):
        initial_dir = os.path.dirname(self.png_var.get().strip()) or os.getcwd()
        initial_file = ""

        png_path = self.png_var.get().strip()
        if png_path:
            initial_file = os.path.splitext(os.path.basename(png_path))[0] + ".ico"

        path = filedialog.asksaveasfilename(
            title="选择 ICO 输出路径",
            initialdir=initial_dir,
            initialfile=initial_file,
            defaultextension=".ico",
            filetypes=[("ICO 图标", "*.ico"), ("所有文件", "*.*")]
        )
        if path:
            self.ico_var.set(path)
            self.status_var.set("已选择 ICO 输出路径")

    def convert(self):
        try:
            ico_path = convert_png_to_ico(self.png_var.get().strip(), self.ico_var.get().strip())
        except Exception as exc:
            self.status_var.set("转换失败")
            messagebox.showerror("转换失败", str(exc))
            return

        self.status_var.set(f"转换完成：{ico_path}")
        messagebox.showinfo("完成", f"ICO 已生成：\n{ico_path}")


if __name__ == "__main__":
    app = PngToIcoApp()
    app.mainloop()
