import math
import random
import sys
import ctypes

from PySide6.QtCore import Qt, QTimer, QRectF, QPointF
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
    QBrush,
)
from PySide6.QtWidgets import QApplication, QWidget


# =========================
# 你可以改这里的文案
# =========================
MESSAGES = [
    "喜欢你",
    "想和你一起看日落",
    "你笑起来真好看",
    "你是今天最甜的风景",
    "想把偏爱都给你",
    "每天都想见到你",
    "你比星星还耀眼",
    "心动不止一点点",
    "想陪你很久很久",
    "谢谢你来到我身边",
    "你是我藏不住的喜欢",
    "世界很大，我只想奔向你",
    "希望以后的故事都有你",
    "你一出现，空气都变甜了",
    "怦然心动，是关于你",
    "今天也比昨天更喜欢你",
    "遇见你之后，万物都浪漫",
    "你是我的例外和偏爱",
    "表白一下：我喜欢你",
    "想一直一直对你好",
    "能能出品，必属精品",
]


def ease_out_back(t: float) -> float:
    """稍微有一点回弹的缓动"""
    c1 = 1.70158
    c3 = c1 + 1.0
    return 1 + c3 * pow(t - 1, 3) + c1 * pow(t - 1, 2)


class Card:
    def __init__(self, start_x, start_y, target_x, target_y, text, index):
        self.sx = start_x
        self.sy = start_y
        self.tx = target_x
        self.ty = target_y

        self.x = start_x
        self.y = start_y

        self.text = text
        self.index = index

        self.w = random.randint(110, 160)
        self.h = random.randint(58, 84)

        self.base_rotation = random.uniform(-22, 22)
        self.rotation = self.base_rotation
        self.target_rotation = random.uniform(-8, 8)

        self.scale = 0.5
        self.alpha = 0.0

        self.delay = random.uniform(0.0, 1.5)
        self.duration = random.uniform(1.6, 1.5)

        self.float_phase = random.uniform(0, math.pi * 2)
        self.float_speed = random.uniform(0.8, 1.5)
        self.float_amp = random.uniform(1.5, 4.5)

        self.settled = False
        self.shadow_alpha = random.randint(45, 90)

        # 粉白配色
        self.bg = random.choice([
            QColor(255, 240, 246, 215),
            QColor(255, 245, 248, 220),
            QColor(255, 250, 252, 210),
            QColor(255, 236, 243, 220),
            QColor(255, 242, 245, 215),
        ])

        self.border = random.choice([
            QColor(255, 182, 193, 200),
            QColor(255, 160, 180, 180),
            QColor(255, 200, 210, 170),
        ])

        self.text_color = QColor(120, 60, 85, 230)

    def update(self, global_t):
        local_t = global_t - self.delay
        if local_t <= 0:
            return

        p = min(1.0, local_t / self.duration)
        ep = ease_out_back(p)

        self.x = self.sx + (self.tx - self.sx) * ep
        self.y = self.sy + (self.ty - self.sy) * ep
        self.scale = 0.5 + 0.5 * ep
        self.alpha = ep
        self.rotation = self.base_rotation + (self.target_rotation - self.base_rotation) * ep

        if p >= 1.0:
            self.settled = True

    def draw(self, painter: QPainter, time_sec: float):
        # 最终阶段轻微漂浮
        fx = 0.0
        fy = 0.0
        if self.settled:
            fx = math.cos(time_sec * self.float_speed + self.float_phase) * self.float_amp
            fy = math.sin(time_sec * self.float_speed + self.float_phase) * self.float_amp

        x = self.x + fx
        y = self.y + fy

        painter.save()
        painter.translate(x, y)
        painter.rotate(self.rotation)
        painter.scale(self.scale, self.scale)

        rect = QRectF(-self.w / 2, -self.h / 2, self.w, self.h)

        # 阴影
        shadow_offset = QPointF(5, 7)
        shadow_rect = rect.translated(shadow_offset)
        shadow_color = QColor(80, 30, 50, int(self.shadow_alpha * self.alpha))
        painter.setPen(Qt.NoPen)
        painter.setBrush(shadow_color)
        painter.drawRoundedRect(shadow_rect, 16, 16)

        # 卡片主体
        bg = QColor(self.bg)
        bg.setAlpha(int(bg.alpha() * self.alpha))
        border = QColor(self.border)
        border.setAlpha(int(border.alpha() * self.alpha))

        painter.setPen(QPen(border, 1.6))
        painter.setBrush(QBrush(bg))
        painter.drawRoundedRect(rect, 16, 16)

        # 顶部高光
        highlight = QRectF(rect.x() + 8, rect.y() + 8, rect.width() - 16, 12)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, int(58 * self.alpha)))
        painter.drawRoundedRect(highlight, 8, 8)

        # 小爱心装饰
        self.draw_tiny_heart(painter, rect.right() - 22, rect.top() + 18, 7, self.alpha)

        # 文本
        text_color = QColor(self.text_color)
        text_color.setAlpha(int(text_color.alpha() * self.alpha))
        painter.setPen(text_color)

        font = QFont("Microsoft YaHei", 10)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(rect.adjusted(12, 16, -12, -12), Qt.AlignCenter | Qt.TextWordWrap, self.text)

        painter.restore()

    @staticmethod
    def draw_tiny_heart(painter: QPainter, cx: float, cy: float, size: float, alpha: float):
        path = QPainterPath()
        s = size

        path.moveTo(cx, cy + s * 0.3)
        path.cubicTo(cx + s, cy - s * 0.9, cx + s * 2.1, cy + s * 0.6, cx, cy + s * 2.0)
        path.cubicTo(cx - s * 2.1, cy + s * 0.6, cx - s, cy - s * 0.9, cx, cy + s * 0.3)

        color = QColor(255, 110, 150, int(190 * alpha))
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawPath(path)


class HeartDesktopWall(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Heart Wall Desktop")
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)

        # 无边框 + 置顶 + 工具窗口，减少任务栏干扰
        flags = Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        self.setWindowFlags(flags)

        # 全屏显示，覆盖桌面
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)

        self.w = self.width()
        self.h = self.height()
        self.cx = self.w / 2
        self.cy = self.h / 2

        self.cards = []
        self.time_sec = 0.0
        self.startup_time = 0.0

        self.total_cards = 180
        self.ambient_hearts = self.make_ambient_hearts(40)

        self.build_cards()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.on_tick)
        self.timer.start(16)  # ~60 FPS

        # Windows 下可选：鼠标点击穿透
        self.enable_click_through_windows()

    def enable_click_through_windows(self):
        """让窗口尽量有‘贴在桌面上’的感觉：鼠标可穿透。
        仅在 Windows 有效；其他系统会自动忽略。
        """
        if sys.platform != "win32":
            return

        try:
            hwnd = int(self.winId())
            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x00080000
            WS_EX_TRANSPARENT = 0x00000020

            user32 = ctypes.windll.user32
            current_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(
                hwnd,
                GWL_EXSTYLE,
                current_style | WS_EX_LAYERED | WS_EX_TRANSPARENT
            )
        except Exception:
            pass

    def make_ambient_hearts(self, n):
        items = []
        for _ in range(n):
            items.append({
                "x": random.uniform(0, self.w),
                "y": random.uniform(0, self.h),
                "size": random.uniform(6, 16),
                "speed": random.uniform(6, 20),
                "phase": random.uniform(0, math.pi * 2),
                "alpha": random.randint(20, 70),
            })
        return items

    def heart_points(self, count: int):
        """生成爱心轮廓+内部点"""
        points = []

        # 经典心形参数方程
        # x = 16 sin^3 t
        # y = 13 cos t - 5 cos 2t - 2 cos 3t - cos 4t
        # 这里混合几层缩放，形成填充效果
        layers = [1.00, 0.86, 0.72, 0.58]
        per_layer = max(1, count // len(layers))

        for scale in layers:
            for i in range(per_layer):
                t = 2 * math.pi * i / per_layer
                x = 16 * (math.sin(t) ** 3)
                y = (
                    13 * math.cos(t)
                    - 5 * math.cos(2 * t)
                    - 2 * math.cos(3 * t)
                    - math.cos(4 * t)
                )

                # 心形缩放
                sx = x * 18 * scale
                sy = -y * 18 * scale

                # 轻微随机扰动，像“卡片墙”
                jitter_x = random.uniform(-14, 14)
                jitter_y = random.uniform(-12, 12)

                px = self.cx + sx + jitter_x
                py = self.cy + sy + jitter_y

                points.append((px, py))

        # 不够的话补齐
        while len(points) < count:
            t = random.uniform(0, 2 * math.pi)
            r = random.uniform(0.45, 1.0)
            x = 16 * (math.sin(t) ** 3)
            y = (
                13 * math.cos(t)
                - 5 * math.cos(2 * t)
                - 2 * math.cos(3 * t)
                - math.cos(4 * t)
            )
            px = self.cx + x * 18 * r + random.uniform(-10, 10)
            py = self.cy - y * 18 * r + random.uniform(-10, 10)
            points.append((px, py))

        return points[:count]

    def random_spawn_point(self):
        """从屏幕四周生成飞入起点"""
        side = random.choice(["top", "bottom", "left", "right"])
        margin = 200

        if side == "top":
            return random.uniform(0, self.w), random.uniform(-margin, -40)
        if side == "bottom":
            return random.uniform(0, self.w), random.uniform(self.h + 40, self.h + margin)
        if side == "left":
            return random.uniform(-margin, -40), random.uniform(0, self.h)
        return random.uniform(self.w + 40, self.w + margin), random.uniform(0, self.h)

    def build_cards(self):
        positions = self.heart_points(self.total_cards)
        random.shuffle(positions)

        for i, (tx, ty) in enumerate(positions):
            sx, sy = self.random_spawn_point()
            text = random.choice(MESSAGES)
            card = Card(sx, sy, tx, ty, text, i)
            self.cards.append(card)

        # 按 y 排序，形成一点层叠前后感
        self.cards.sort(key=lambda c: c.ty)

    def on_tick(self):
        dt = 0.016
        self.time_sec += dt
        self.startup_time += dt

        for card in self.cards:
            card.update(self.startup_time)

        for item in self.ambient_hearts:
            item["y"] -= item["speed"] * dt
            item["x"] += math.sin(self.time_sec + item["phase"]) * 0.35
            if item["y"] < -20:
                item["y"] = self.h + random.uniform(10, 80)
                item["x"] = random.uniform(0, self.w)

        self.update()

    def draw_big_center_text(self, painter: QPainter):
        # 爱心完成后，中间淡淡出现一句话
        settled_count = sum(1 for c in self.cards if c.settled)
        if settled_count < int(self.total_cards * 0.72):
            return

        alpha = min(1.0, (settled_count / self.total_cards - 0.72) / 0.28)
        text_alpha = int(220 * alpha)

        font = QFont("Microsoft YaHei", 28)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(255, 255, 255, text_alpha))

        shadow_pen = QColor(255, 120, 160, int(90 * alpha))

        text = "I Like You"
        rect = QRectF(0, self.cy - 25, self.w, 60)

        # 阴影
        painter.setPen(shadow_pen)
        painter.drawText(rect.translated(2, 3), Qt.AlignCenter, text)

        # 主文字
        painter.setPen(QColor(255, 255, 255, text_alpha))
        painter.drawText(rect, Qt.AlignCenter, text)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        # 半透明氛围光晕，不要太实
        glow_alpha = 48
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 120, 160, glow_alpha))
        painter.drawEllipse(QPointF(self.cx, self.cy), 320, 260)

        painter.setBrush(QColor(255, 180, 210, 24))
        painter.drawEllipse(QPointF(self.cx, self.cy + 20), 440, 330)

        # 漂浮小心心
        for item in self.ambient_hearts:
            self.draw_floating_heart(
                painter,
                item["x"],
                item["y"],
                item["size"],
                item["alpha"]
            )

        # 小卡片
        for card in self.cards:
            card.draw(painter, self.time_sec)

        # 中央文案
        self.draw_big_center_text(painter)

    def draw_floating_heart(self, painter: QPainter, x, y, size, alpha):
        path = QPainterPath()
        s = size
        path.moveTo(x, y + s * 0.3)
        path.cubicTo(x + s, y - s * 0.9, x + s * 2.1, y + s * 0.6, x, y + s * 2.0)
        path.cubicTo(x - s * 2.1, y + s * 0.6, x - s, y - s * 0.9, x, y + s * 0.3)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 150, 180, alpha))
        painter.drawPath(path)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Escape, Qt.Key_Q):
            self.close()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)

    wall = HeartDesktopWall()
    wall.showFullScreen()

    sys.exit(app.exec())
