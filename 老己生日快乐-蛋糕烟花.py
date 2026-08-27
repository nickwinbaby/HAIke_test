import math
import random
import sys

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QFont,
    QKeySequence,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
    QShortcut,
)
from PySide6.QtWidgets import QApplication, QWidget


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def lerp(a, b, t):
    return a + (b - a) * clamp(t, 0.0, 1.0)


def ease_out_cubic(t):
    return 1 - pow(1 - t, 3)


def ease_out_back(t):
    c1 = 1.70158
    c3 = c1 + 1.0
    return 1 + c3 * pow(t - 1, 3) + c1 * pow(t - 1, 2)


def mix_color(a: QColor, b: QColor, t: float) -> QColor:
    t = clamp(t, 0.0, 1.0)
    return QColor(
        int(lerp(a.red(), b.red(), t)),
        int(lerp(a.green(), b.green(), t)),
        int(lerp(a.blue(), b.blue(), t)),
        int(lerp(a.alpha(), b.alpha(), t)),
    )


class Particle:
    def __init__(self, x, y, vx, vy, color, size, life, kind="dot"):
        self.x = x
        self.y = y
        self.px = x
        self.py = y
        self.vx = vx
        self.vy = vy
        self.color = QColor(color)
        self.size = size
        self.life = life
        self.max_life = life
        self.kind = kind
        self.phase = random.uniform(0, math.tau)
        self.spin = random.uniform(-7.0, 7.0)
        self.rot = random.uniform(0, math.tau)
        self.rot_speed = random.uniform(-7.0, 7.0)
        self.gravity = random.uniform(4.0, 26.0)
        self.drag = random.uniform(0.986, 0.996)

    def update(self, dt):
        self.px = self.x
        self.py = self.y
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vx *= self.drag
        self.vy = self.vy * self.drag + self.gravity * dt
        self.vx += math.sin(self.phase + self.life * 4.0) * 6 * dt
        self.rot += self.rot_speed * dt
        self.life -= dt

    def draw(self, painter: QPainter, t: float):
        if self.life <= 0:
            return
        p = clamp(self.life / self.max_life, 0.0, 1.0)
        alpha = int(255 * (p ** 0.72))
        color = QColor(self.color)
        color.setAlpha(alpha)
        glow = QColor(self.color)
        glow.setAlpha(int(alpha * 0.16))

        painter.setPen(Qt.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(QPointF(self.x, self.y), self.size * 3.4, self.size * 3.4)

        if self.kind == "spark":
            painter.setPen(QPen(color, max(1.0, self.size * 0.14)))
            painter.drawLine(QPointF(self.px, self.py), QPointF(self.x, self.y))
            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(QPointF(self.x, self.y), self.size * 0.55, self.size * 0.55)
        elif self.kind == "star":
            painter.save()
            painter.translate(self.x, self.y)
            painter.rotate(self.spin * t * 16.0)
            painter.setBrush(color)
            path = QPainterPath()
            s = self.size
            path.moveTo(0, -s * 1.8)
            path.lineTo(s * 0.42, -s * 0.42)
            path.lineTo(s * 1.8, 0)
            path.lineTo(s * 0.42, s * 0.42)
            path.lineTo(0, s * 1.8)
            path.lineTo(-s * 0.42, s * 0.42)
            path.lineTo(-s * 1.8, 0)
            path.lineTo(-s * 0.42, -s * 0.42)
            path.closeSubpath()
            painter.drawPath(path)
            painter.restore()
        elif self.kind == "ring":
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(color, max(1.0, self.size * 0.14)))
            r = self.size * (0.85 + (1 - p) * 3.1)
            painter.drawEllipse(QPointF(self.x, self.y), r, r)
        elif self.kind == "petal":
            painter.save()
            painter.translate(self.x, self.y)
            ang = math.degrees(math.atan2(self.vy, self.vx))
            painter.rotate(ang + math.degrees(self.rot))
            painter.setBrush(color)
            path = QPainterPath()
            s = self.size
            path.moveTo(0, -s * 1.6)
            path.cubicTo(s * 0.9, -s * 0.9, s * 0.8, s * 0.8, 0, s * 1.4)
            path.cubicTo(-s * 0.8, s * 0.8, -s * 0.9, -s * 0.9, 0, -s * 1.6)
            painter.drawPath(path)
            painter.restore()
        elif self.kind == "comet":
            painter.setPen(QPen(color, max(1.0, self.size * 0.12)))
            tail = self.size * (2.6 + (1 - p) * 4.2)
            ang = math.atan2(self.vy, self.vx)
            tx = self.x - math.cos(ang) * tail
            ty = self.y - math.sin(ang) * tail
            painter.drawLine(QPointF(tx, ty), QPointF(self.x, self.y))
            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(QPointF(self.x, self.y), self.size * 0.75, self.size * 0.75)
        else:
            painter.setBrush(color)
            painter.drawEllipse(QPointF(self.x, self.y), self.size, self.size)


class FireworkShell:
    def __init__(self, sx, sy, tx, ty, color):
        self.x = sx
        self.y = sy
        self.tx = tx
        self.ty = ty
        self.color = QColor(color)
        self.trail = []
        dx = tx - sx
        dy = ty - sy
        dist = max(1.0, math.hypot(dx, dy))
        speed = random.uniform(260, 420)
        self.vx = dx / dist * speed
        self.vy = dy / dist * speed
        self.life = random.uniform(0.8, 1.3)

    def update(self, dt):
        self.trail.append((self.x, self.y))
        if len(self.trail) > 18:
            self.trail.pop(0)
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vy += 68 * dt
        self.life -= dt
        return self.life <= 0 or (self.vy > 0 and self.y <= self.ty)

    def draw(self, painter: QPainter):
        for i, (tx, ty) in enumerate(self.trail):
            a = int(160 * (i + 1) / max(1, len(self.trail)))
            c = QColor(self.color)
            c.setAlpha(a)
            painter.setPen(Qt.NoPen)
            painter.setBrush(c)
            painter.drawEllipse(QPointF(tx, ty), 1.3 + i * 0.12, 1.3 + i * 0.12)
        painter.setBrush(QColor(245, 245, 245, 235))
        painter.drawEllipse(QPointF(self.x, self.y), 3.0, 3.0)


class PulseRing:
    def __init__(self, x, y, color):
        self.x = x
        self.y = y
        self.color = QColor(color)
        self.life = 1.0
        self.max_life = 1.0

    def update(self, dt):
        self.life -= dt

    def draw(self, painter: QPainter):
        if self.life <= 0:
            return
        p = clamp(self.life / self.max_life, 0.0, 1.0)
        c = QColor(self.color)
        c.setAlpha(int(180 * p))
        painter.setPen(QPen(c, 2.0))
        painter.setBrush(Qt.NoBrush)
        r = (1 - p) * 180 + 18
        painter.drawEllipse(QPointF(self.x, self.y), r, r)


class SmokeWisp:
    def __init__(self, x, y, vx, vy, radius, color, life):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.radius = radius
        self.color = QColor(color)
        self.life = life
        self.max_life = life
        self.phase = random.uniform(0, math.tau)

    def update(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.radius *= 1.001
        self.vy -= 2.4 * dt
        self.life -= dt

    def draw(self, painter: QPainter, t: float):
        if self.life <= 0:
            return
        p = clamp(self.life / self.max_life, 0.0, 1.0)
        alpha = int(64 * (p ** 1.35))
        painter.setPen(Qt.NoPen)
        for i in range(4):
            rr = self.radius * (0.48 + i * 0.26)
            ox = math.sin(t * 0.55 + self.phase + i) * rr * 0.24
            oy = math.cos(t * 0.42 + self.phase + i * 1.2) * rr * 0.10
            c = QColor(self.color)
            c.setAlpha(max(0, alpha - i * 8))
            painter.setBrush(c)
            painter.drawEllipse(QPointF(self.x + ox, self.y + oy), rr, rr * 0.68)


class FlowRibbon:
    def __init__(self, y, amp, speed, phase, colors):
        self.y = y
        self.amp = amp
        self.speed = speed
        self.phase = phase
        self.colors = [QColor(c) for c in colors]

    def draw(self, painter: QPainter, t: float, w: int, h: int):
        painter.save()
        painter.setCompositionMode(QPainter.CompositionMode_Plus)
        path = QPainterPath()
        left = -80
        right = w + 80
        samples = 60
        step = (right - left) / samples
        base = self.y + math.sin(t * self.speed + self.phase) * self.amp * 0.15
        path.moveTo(left, base)
        for i in range(samples + 1):
            x = left + i * step
            wave = (
                math.sin(t * self.speed + i * 0.12 + self.phase) * self.amp
                + math.sin(t * self.speed * 0.6 + i * 0.28 + self.phase * 1.7) * self.amp * 0.45
            )
            path.lineTo(x, base + wave)

        grad = QLinearGradient(0, base - self.amp * 2.0, 0, base + self.amp * 2.0)
        grad.setColorAt(0.0, QColor(self.colors[0].red(), self.colors[0].green(), self.colors[0].blue(), 0))
        grad.setColorAt(0.45, self.colors[0])
        grad.setColorAt(0.55, self.colors[1])
        grad.setColorAt(1.0, QColor(self.colors[-1].red(), self.colors[-1].green(), self.colors[-1].blue(), 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(grad)
        painter.drawPath(path)

        painter.setPen(QPen(QColor(255, 255, 255, 14), 1.0))
        painter.drawPath(path.translated(0, -2))
        painter.drawPath(path.translated(0, 2))
        painter.restore()


class DarkCakeShow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("老己生日快乐")
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setFocusPolicy(Qt.StrongFocus)

        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)
        self.w = self.width()
        self.h = self.height()
        self.cx = self.w / 2
        self.cy = self.h / 2

        self.t = 0.0
        self.flash = 0.0
        self.flash_x = self.cx
        self.flash_y = self.h * 0.45
        self.firework_timer = 0.0

        self.stars = self._make_stars(128)
        self.bands = self._make_bands()
        self.flow_ribbons = self._make_flow_ribbons()
        self.back_motes = self._make_back_motes(260)
        self.orbs = self._make_orbs(150)
        self.wisps = self._make_wisps(20)
        self.cake_motes = self._make_cake_motes(48)
        self.shells = []
        self.particles = []
        self.rings = []

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.on_tick)
        self.timer.start(16)

        self.escape_shortcut = QShortcut(QKeySequence("Esc"), self)
        self.escape_shortcut.setContext(Qt.ApplicationShortcut)
        self.escape_shortcut.activated.connect(self.close)

        self.close_shortcut = QShortcut(QKeySequence("Ctrl+W"), self)
        self.close_shortcut.setContext(Qt.ApplicationShortcut)
        self.close_shortcut.activated.connect(self.close)

        QTimer.singleShot(0, self._claim_keyboard)

    def _claim_keyboard(self):
        try:
            self.showFullScreen()
            self.raise_()
            self.activateWindow()
            self.grabKeyboard()
            self.setFocus(Qt.ActiveWindowFocusReason)
        except Exception:
            pass

    def closeEvent(self, event):
        try:
            self.timer.stop()
            self.releaseKeyboard()
        except Exception:
            pass
        event.accept()

    def _make_stars(self, n):
        items = []
        for _ in range(n):
            items.append({
                "x": random.uniform(0, self.w),
                "y": random.uniform(0, self.h),
                "r": random.uniform(0.8, 2.4),
                "tw": random.uniform(0.7, 2.2),
                "phase": random.uniform(0, math.tau),
                "alpha": random.randint(50, 170),
            })
        return items

    def _make_bands(self):
        return [
            {"y": self.h * 0.14, "amp": 24, "speed": 0.92, "phase": 0.3, "c1": QColor(52, 48, 46, 55), "c2": QColor(52, 48, 46, 0)},
            {"y": self.h * 0.32, "amp": 20, "speed": 0.72, "phase": 1.8, "c1": QColor(72, 64, 60, 48), "c2": QColor(72, 64, 60, 0)},
            {"y": self.h * 0.56, "amp": 18, "speed": 0.58, "phase": 2.7, "c1": QColor(96, 84, 76, 38), "c2": QColor(96, 84, 76, 0)},
        ]

    def _make_flow_ribbons(self):
        return [
            FlowRibbon(self.h * 0.10, 42, 0.96, 0.2, [QColor(196, 190, 184, 66), QColor(122, 110, 104, 28), QColor(196, 190, 184, 0)]),
            FlowRibbon(self.h * 0.22, 36, 0.84, 1.0, [QColor(170, 162, 176, 62), QColor(96, 88, 112, 24), QColor(170, 162, 176, 0)]),
            FlowRibbon(self.h * 0.34, 32, 0.72, 1.8, [QColor(144, 156, 182, 56), QColor(76, 92, 120, 22), QColor(144, 156, 182, 0)]),
            FlowRibbon(self.h * 0.50, 30, 0.62, 2.6, [QColor(150, 138, 132, 52), QColor(86, 80, 78, 20), QColor(150, 138, 132, 0)]),
            FlowRibbon(self.h * 0.66, 24, 0.54, 3.2, [QColor(136, 120, 140, 44), QColor(82, 72, 92, 18), QColor(136, 120, 140, 0)]),
            FlowRibbon(self.h * 0.80, 20, 0.48, 3.9, [QColor(112, 104, 100, 38), QColor(64, 62, 64, 16), QColor(112, 104, 100, 0)]),
            FlowRibbon(self.h * 0.90, 16, 0.42, 4.5, [QColor(96, 92, 96, 32), QColor(52, 54, 60, 14), QColor(96, 92, 96, 0)]),
        ]

    def _make_orbs(self, n):
        palette = [
            QColor(230, 228, 224),
            QColor(198, 190, 184),
            QColor(170, 158, 150),
            QColor(140, 120, 108),
            QColor(108, 96, 92),
        ]
        items = []
        for _ in range(n):
            ang = random.uniform(0, math.tau)
            radius = random.uniform(56, min(self.w, self.h) * 0.42)
            x = self.cx + math.cos(ang) * radius
            y = self.h * 0.5 + math.sin(ang) * radius * 0.75
            speed = random.uniform(6, 20)
            items.append({
                "x": x,
                "y": y,
                "vx": math.cos(ang + math.pi / 2) * speed,
                "vy": math.sin(ang + math.pi / 2) * speed * 0.6,
                "size": random.uniform(1.2, 4.0),
                "life": random.uniform(2.6, 5.8),
                "max_life": 1.0,
                "phase": random.uniform(0, math.tau),
                "color": random.choice(palette),
                "kind": random.choice(["dot", "spark", "star"]),
            })
        for item in items:
            item["max_life"] = item["life"]
        return items

    def _make_wisps(self, n):
        palette = [
            QColor(56, 52, 50, 82),
            QColor(84, 76, 72, 72),
            QColor(110, 96, 86, 62),
        ]
        items = []
        for _ in range(n):
            items.append(SmokeWisp(
                random.uniform(self.w * 0.18, self.w * 0.82),
                random.uniform(self.h * 0.38, self.h * 0.88),
                random.uniform(-10, 10),
                random.uniform(-22, -8),
                random.uniform(16, 42),
                random.choice(palette),
                random.uniform(2.8, 6.8),
            ))
        return items

    def _make_back_motes(self, n):
        palette = [
            QColor(94, 86, 84, 74),
            QColor(122, 108, 104, 72),
            QColor(168, 156, 152, 58),
            QColor(80, 96, 126, 70),
            QColor(110, 84, 132, 62),
            QColor(132, 96, 84, 58),
        ]
        items = []
        for _ in range(n):
            items.append({
                "x": random.uniform(0, self.w),
                "y": random.uniform(0, self.h),
                "vx": random.uniform(-8, 8),
                "vy": random.uniform(-12, 12),
                "size": random.uniform(0.8, 2.2),
                "color": random.choice(palette),
                "phase": random.uniform(0, math.tau),
                "life": random.uniform(2.0, 5.5),
                "max_life": 1.0,
            })
        for item in items:
            item["max_life"] = item["life"]
        return items

    def _make_cake_motes(self, n):
        palette = [
            QColor(220, 216, 210),
            QColor(188, 178, 170),
            QColor(160, 146, 136),
            QColor(132, 116, 106),
        ]
        items = []
        for _ in range(n):
            items.append({
                "angle": random.uniform(0, math.tau),
                "radius": random.uniform(86, 220),
                "speed": random.uniform(0.2, 0.9),
                "phase": random.uniform(0, math.tau),
                "size": random.uniform(1.0, 3.0),
                "color": random.choice(palette),
                "kind": random.choice(["dot", "spark", "star"]),
            })
        return items

    def cake_progress(self):
        return clamp((self.t - 0.28) / 1.35, 0.0, 1.0)

    def cake_center(self):
        return self.cx, self.h * 0.62

    def on_tick(self):
        dt = 0.016
        self.t += dt
        self.flash = max(0.0, self.flash - dt * 2.0)
        self._update_orbs(dt)
        self._update_wisps(dt)
        self._update_flow_ribbons(dt)
        self._update_back_motes(dt)
        self._update_cake_motes(dt)
        self._update_shells(dt)

        if self.t > 0.45:
            self.firework_timer -= dt
            if self.firework_timer <= 0:
                self.firework_timer = random.uniform(0.08, 0.24)
                self._spawn_firework()

        self.update()

    def _update_orbs(self, dt):
        palette = [
            QColor(230, 228, 224),
            QColor(198, 190, 184),
            QColor(170, 158, 150),
            QColor(140, 120, 108),
            QColor(108, 96, 92),
        ]
        for orb in self.orbs:
            orb["x"] += orb["vx"] * dt
            orb["y"] += orb["vy"] * dt
            orb["vx"] += math.sin(self.t * 0.8 + orb["phase"]) * 2.5 * dt
            orb["vy"] += math.cos(self.t * 0.7 + orb["phase"]) * 1.8 * dt
            orb["life"] -= dt
            if orb["life"] <= 0 or orb["x"] < -80 or orb["x"] > self.w + 80 or orb["y"] < -80 or orb["y"] > self.h + 80:
                ang = random.uniform(0, math.tau)
                radius = random.uniform(56, min(self.w, self.h) * 0.42)
                orb["x"] = self.cx + math.cos(ang) * radius
                orb["y"] = self.h * 0.5 + math.sin(ang) * radius * 0.75
                speed = random.uniform(6, 20)
                orb["vx"] = math.cos(ang + math.pi / 2) * speed
                orb["vy"] = math.sin(ang + math.pi / 2) * speed * 0.6
                orb["life"] = orb["max_life"] = random.uniform(2.6, 5.8)
                orb["size"] = random.uniform(1.2, 4.0)
                orb["color"] = random.choice(palette)
                orb["kind"] = random.choice(["dot", "spark", "star"])
                orb["phase"] = random.uniform(0, math.tau)

    def _update_wisps(self, dt):
        alive = []
        for wisp in self.wisps:
            wisp.update(dt)
            if wisp.life > 0:
                alive.append(wisp)
        while len(alive) < 20:
            alive.append(SmokeWisp(
                random.uniform(self.w * 0.15, self.w * 0.85),
                self.h * 0.72 + random.uniform(-40, 30),
                random.uniform(-10, 10),
                random.uniform(-22, -8),
                random.uniform(16, 40),
                random.choice([QColor(56, 52, 50, 82), QColor(84, 76, 72, 72), QColor(110, 96, 86, 62)]),
                random.uniform(2.8, 6.8),
            ))
        self.wisps = alive

    def _update_flow_ribbons(self, dt):
        # 仅由时间驱动，这里保留接口方便后续继续加更复杂的流光逻辑
        pass

    def _update_back_motes(self, dt):
        palette = [
            QColor(94, 86, 84, 74),
            QColor(122, 108, 104, 72),
            QColor(168, 156, 152, 58),
            QColor(80, 96, 126, 70),
            QColor(110, 84, 132, 62),
            QColor(132, 96, 84, 58),
        ]
        for mote in self.back_motes:
            mote["x"] += mote["vx"] * dt
            mote["y"] += mote["vy"] * dt
            mote["life"] -= dt
            mote["vx"] += math.sin(self.t * 0.4 + mote["phase"]) * 1.2 * dt
            mote["vy"] += math.cos(self.t * 0.5 + mote["phase"]) * 0.8 * dt
            if mote["life"] <= 0 or mote["x"] < -40 or mote["x"] > self.w + 40 or mote["y"] < -40 or mote["y"] > self.h + 40:
                mote["x"] = random.uniform(0, self.w)
                mote["y"] = random.uniform(0, self.h)
                mote["vx"] = random.uniform(-8, 8)
                mote["vy"] = random.uniform(-12, 12)
                mote["size"] = random.uniform(0.8, 2.2)
                mote["color"] = random.choice(palette)
                mote["phase"] = random.uniform(0, math.tau)
                mote["life"] = mote["max_life"] = random.uniform(2.0, 5.5)

    def _update_cake_motes(self, dt):
        cx, cy = self.cake_center()
        for mote in self.cake_motes:
            mote["angle"] += mote["speed"] * dt
            mote["radius"] += math.sin(self.t * 1.5 + mote["phase"]) * 0.04
            mote["cx"] = cx
            mote["cy"] = cy - 10

    def _update_shells(self, dt):
        alive_shells = []
        for shell in self.shells:
            if shell.update(dt):
                self._burst(shell.x, shell.y, shell.color)
            else:
                alive_shells.append(shell)
        self.shells = alive_shells

        alive_particles = []
        for part in self.particles:
            part.update(dt)
            if part.life > 0:
                alive_particles.append(part)
        self.particles = alive_particles

        alive_rings = []
        for ring in self.rings:
            ring.update(dt)
            if ring.life > 0:
                alive_rings.append(ring)
        self.rings = alive_rings

    def _spawn_firework(self):
        palette = [
            QColor(226, 224, 220),
            QColor(198, 188, 180),
            QColor(162, 148, 138),
            QColor(128, 110, 100),
            QColor(92, 84, 80),
        ]
        for _ in range(1 if random.random() < 0.72 else 2):
            sx, sy = self._launch_point()
            tx, ty = self._target_point()
            self.shells.append(FireworkShell(sx, sy, tx, ty, random.choice(palette)))

    def _launch_point(self):
        side = random.choice(["bottom", "left", "right"])
        if side == "left":
            return -40, random.uniform(self.h * 0.22, self.h * 0.92)
        if side == "right":
            return self.w + 40, random.uniform(self.h * 0.22, self.h * 0.92)
        return random.uniform(self.w * 0.10, self.w * 0.90), self.h + 40

    def _target_point(self):
        return random.uniform(self.w * 0.16, self.w * 0.84), random.uniform(self.h * 0.10, self.h * 0.44)

    def _spawn_smoke(self, x, y):
        self.wisps.append(SmokeWisp(
            x + random.uniform(-18, 18),
            y + random.uniform(-10, 10),
            random.uniform(-14, 14),
            random.uniform(-30, -12),
            random.uniform(16, 34),
            random.choice([QColor(56, 52, 50, 82), QColor(84, 76, 72, 72), QColor(110, 96, 86, 62)]),
            random.uniform(2.2, 4.4),
        ))

    def _burst(self, x, y, color):
        self.flash = min(1.0, self.flash + 0.68)
        self.flash_x = x
        self.flash_y = y

        palette = [
            QColor(232, 230, 226),
            QColor(198, 188, 180),
            QColor(156, 146, 152),
            QColor(128, 150, 176),
            QColor(156, 120, 170),
            QColor(168, 140, 112),
            QColor(92, 84, 80),
        ]
        count = random.randint(84, 126)
        for i in range(count):
            angle = (math.tau * i / count) + random.uniform(-0.10, 0.10)
            speed = random.uniform(100, 320)
            kind = random.choices(["spark", "petal", "star", "ring", "dot", "comet"], weights=[4, 4, 2, 1, 1, 1])[0]
            c = mix_color(color, random.choice(palette), random.random() * 0.65)
            self.particles.append(Particle(
                x,
                y,
                math.cos(angle) * speed,
                math.sin(angle) * speed,
                c,
                random.uniform(1.1, 4.8),
                random.uniform(0.85, 1.9),
                kind=kind,
            ))
        for _ in range(22):
            angle = random.uniform(0, math.tau)
            speed = random.uniform(42, 150)
            self.particles.append(Particle(
                x,
                y,
                math.cos(angle) * speed,
                math.sin(angle) * speed,
                QColor(245, 242, 238),
                random.uniform(0.9, 2.4),
                random.uniform(0.45, 1.05),
                kind=random.choice(["spark", "star", "comet"]),
            ))
        for _ in range(18):
            angle = random.uniform(0, math.tau)
            speed = random.uniform(70, 210)
            self.particles.append(Particle(
                x,
                y,
                math.cos(angle) * speed,
                math.sin(angle) * speed,
                mix_color(color, QColor(245, 242, 238), random.random() * 0.3),
                random.uniform(1.6, 3.8),
                random.uniform(0.9, 1.8),
                kind="petal",
            ))
        for _ in range(4):
            self._spawn_smoke(x, y)

    def _draw_band(self, painter, band):
        painter.setPen(Qt.NoPen)
        path = QPainterPath()
        left = -60
        right = self.w + 60
        samples = 56
        step = (right - left) / samples
        base = band["y"] + math.sin(self.t * band["speed"] + band["phase"]) * band["amp"] * 0.2
        path.moveTo(left, base)
        for i in range(samples + 1):
            x = left + i * step
            y = base + (
                math.sin(self.t * band["speed"] + band["phase"] + i * 0.15) * band["amp"]
                + math.sin(self.t * band["speed"] * 0.62 + band["phase"] * 1.4 + i * 0.32) * band["amp"] * 0.5
            )
            path.lineTo(x, y)
        path.lineTo(right, self.h + 100)
        path.lineTo(left, self.h + 100)
        path.closeSubpath()
        grad = QLinearGradient(0, base - band["amp"] * 2.1, 0, base + band["amp"] * 2.1)
        grad.setColorAt(0.0, QColor(band["c1"].red(), band["c1"].green(), band["c1"].blue(), 0))
        mid = QColor(band["c1"])
        mid.setAlpha(band["c1"].alpha())
        grad.setColorAt(0.5, mid)
        grad.setColorAt(1.0, QColor(band["c2"].red(), band["c2"].green(), band["c2"].blue(), 0))
        painter.setBrush(grad)
        painter.drawPath(path)

    def draw_background(self, painter: QPainter):
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        painter.fillRect(self.rect(), QColor(3, 5, 10, 255))

        painter.setPen(Qt.NoPen)
        bg = QLinearGradient(0, 0, 0, self.h)
        bg.setColorAt(0.0, QColor(9, 10, 16))
        bg.setColorAt(0.56, QColor(14, 12, 18))
        bg.setColorAt(1.0, QColor(8, 8, 10))
        painter.fillRect(self.rect(), bg)

        painter.save()
        painter.setCompositionMode(QPainter.CompositionMode_Plus)

        glow1 = QRadialGradient(self.cx * 0.76, self.h * 0.22, self.w * 0.52)
        glow1.setColorAt(0.0, QColor(72, 62, 56, 42))
        glow1.setColorAt(0.4, QColor(72, 62, 56, 20))
        glow1.setColorAt(1.0, QColor(72, 62, 56, 0))
        painter.setBrush(glow1)
        painter.drawEllipse(QPointF(self.cx * 0.76, self.h * 0.22), self.w * 0.52, self.h * 0.34)

        glow2 = QRadialGradient(self.cx * 1.1, self.h * 0.44, self.w * 0.38)
        glow2.setColorAt(0.0, QColor(96, 84, 74, 28))
        glow2.setColorAt(0.45, QColor(96, 84, 74, 12))
        glow2.setColorAt(1.0, QColor(96, 84, 74, 0))
        painter.setBrush(glow2)
        painter.drawEllipse(QPointF(self.cx * 1.1, self.h * 0.44), self.w * 0.38, self.h * 0.28)

        for band in self.bands:
            self._draw_band(painter, band)

        for ribbon in self.flow_ribbons:
            ribbon.draw(painter, self.t, self.w, self.h)

        for mote in self.back_motes:
            c = QColor(mote["color"])
            c.setAlpha(int(18 + 28 * (0.5 + 0.5 * math.sin(self.t * 1.1 + mote["phase"]))))
            painter.setPen(Qt.NoPen)
            painter.setBrush(c)
            painter.drawEllipse(QPointF(mote["x"], mote["y"]), mote["size"], mote["size"])

        for star in self.stars:
            tw = 0.45 + 0.55 * (0.5 + 0.5 * math.sin(self.t * star["tw"] + star["phase"]))
            a = int(star["alpha"] * tw)
            painter.setBrush(QColor(245, 245, 245, a))
            painter.drawEllipse(QPointF(star["x"], star["y"]), star["r"], star["r"])

        for item in self.orbs:
            c = QColor(item["color"])
            c.setAlpha(int(18 + 28 * (0.5 + 0.5 * math.sin(self.t * 1.4 + item["phase"]))))
            painter.setBrush(c)
            if item["kind"] == "spark":
                painter.setPen(QPen(c, 1.0))
                painter.drawLine(QPointF(item["x"] - item["size"] * 1.6, item["y"]), QPointF(item["x"] + item["size"] * 1.6, item["y"]))
            elif item["kind"] == "star":
                painter.save()
                painter.translate(item["x"], item["y"])
                painter.rotate(math.degrees(item["phase"] + self.t * 1.8))
                s = item["size"]
                p = QPainterPath()
                p.moveTo(0, -s * 1.4)
                p.lineTo(s * 0.35, 0)
                p.lineTo(0, s * 1.4)
                p.lineTo(-s * 0.35, 0)
                p.closeSubpath()
                painter.drawPath(p)
                painter.restore()
            else:
                painter.drawEllipse(QPointF(item["x"], item["y"]), item["size"], item["size"])

        for wisp in self.wisps:
            wisp.draw(painter, self.t)

        painter.restore()

        if self.t < 0.75:
            p = ease_out_cubic(self.t / 0.75)
            painter.fillRect(self.rect(), QColor(255, 255, 255, int(150 * (1 - p))))

    def draw_fireworks(self, painter: QPainter):
        painter.save()
        painter.setCompositionMode(QPainter.CompositionMode_Plus)
        for shell in self.shells:
            shell.draw(painter)
        for part in self.particles:
            part.draw(painter, self.t)
        painter.restore()

        if self.flash > 0:
            a = int(70 * self.flash)
            grad = QRadialGradient(self.flash_x, self.flash_y, max(self.w, self.h) * 0.6)
            grad.setColorAt(0.0, QColor(255, 255, 255, a))
            grad.setColorAt(0.22, QColor(172, 156, 144, int(a * 0.34)))
            grad.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.fillRect(self.rect(), grad)

    def draw_rings(self, painter: QPainter):
        cx, cy = self.cake_center()
        painter.save()
        painter.setCompositionMode(QPainter.CompositionMode_Plus)

        for i in range(4):
            rr = 140 + i * 24 + math.sin(self.t * 1.8 + i * 0.7) * 7
            a = int(52 - i * 10)
            painter.setPen(QPen(QColor(190, 180, 174, a), 1.0))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QPointF(cx, cy - 10), rr, rr * 0.64)

        painter.setPen(QPen(QColor(118, 104, 96, 30), 1.0))
        painter.drawEllipse(QPointF(cx, cy - 10), 220 + math.sin(self.t * 3.0) * 8, 142)

        for mote in self.cake_motes:
            ang = mote["angle"]
            r = mote["radius"] + math.sin(self.t * 1.5 + mote["phase"]) * 4
            ox = mote.get("cx", cx) + math.cos(ang) * r
            oy = mote.get("cy", cy - 10) + math.sin(ang * 0.7 + self.t * 1.1 + mote["phase"]) * 18
            c = QColor(mote["color"])
            c.setAlpha(110 if mote["kind"] == "spark" else 78)
            painter.setPen(Qt.NoPen)
            painter.setBrush(c)
            if mote["kind"] == "spark":
                painter.drawEllipse(QPointF(ox, oy), mote["size"] * 0.7, mote["size"] * 0.7)
                painter.setPen(QPen(c, 1.0))
                painter.drawLine(QPointF(ox - mote["size"] * 1.6, oy), QPointF(ox + mote["size"] * 1.6, oy))
            elif mote["kind"] == "star":
                painter.save()
                painter.translate(ox, oy)
                painter.rotate(math.degrees(ang * 1.8 + self.t * 2.1))
                s = mote["size"]
                p = QPainterPath()
                p.moveTo(0, -s * 1.3)
                p.lineTo(s * 0.35, 0)
                p.lineTo(0, s * 1.3)
                p.lineTo(-s * 0.35, 0)
                p.closeSubpath()
                painter.drawPath(p)
                painter.restore()
            else:
                painter.drawEllipse(QPointF(ox, oy), mote["size"], mote["size"])

        for ring in self.rings:
            ring.draw(painter)

        painter.restore()

    def draw_cake(self, painter: QPainter):
        p = self.cake_progress()
        if p <= 0:
            return

        cx, base_y = self.cake_center()
        scale = 0.82 + 0.18 * ease_out_back(p)
        rise = (1 - ease_out_back(p)) * 118
        bob = math.sin(self.t * 2.2) * 1.4 if p > 0.85 else 0.0

        painter.save()
        painter.translate(cx, base_y + rise + bob)
        painter.scale(scale, scale)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, int(72 * p)))
        painter.drawEllipse(QPointF(0, 150), 190, 34)

        plate = QRadialGradient(0, 136, 250)
        plate.setColorAt(0.0, QColor(54, 68, 86, 238))
        plate.setColorAt(0.42, QColor(28, 38, 52, 235))
        plate.setColorAt(0.78, QColor(14, 21, 32, 232))
        plate.setColorAt(1.0, QColor(6, 10, 17, 226))
        painter.setBrush(plate)
        painter.drawEllipse(QPointF(0, 138), 228, 42)

        rim = QLinearGradient(-210, 125, 210, 151)
        rim.setColorAt(0.0, QColor(80, 104, 128, 0))
        rim.setColorAt(0.22, QColor(100, 128, 154, 100))
        rim.setColorAt(0.5, QColor(180, 198, 214, 150))
        rim.setColorAt(0.78, QColor(100, 128, 154, 100))
        rim.setColorAt(1.0, QColor(80, 104, 128, 0))
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(rim, 2.0))
        painter.drawEllipse(QPointF(0, 138), 218, 35)

        inner_rim = QRadialGradient(0, 130, 160)
        inner_rim.setColorAt(0.0, QColor(116, 142, 166, 42))
        inner_rim.setColorAt(0.65, QColor(72, 98, 124, 22))
        inner_rim.setColorAt(1.0, QColor(40, 60, 82, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(inner_rim)
        painter.drawEllipse(QPointF(0, 132), 174, 21)

        body_rect = QRectF(-150, 40, 300, 72)
        body_grad = QLinearGradient(-150, 40, 150, 112)
        body_grad.setColorAt(0.0, QColor(108, 74, 52))
        body_grad.setColorAt(0.5, QColor(70, 46, 34))
        body_grad.setColorAt(1.0, QColor(34, 24, 20))
        painter.setBrush(body_grad)
        painter.drawRoundedRect(body_rect, 28, 28)

        upper_rect = QRectF(-108, -22, 216, 58)
        upper_grad = QLinearGradient(-108, -22, 108, 36)
        upper_grad.setColorAt(0.0, QColor(96, 66, 48))
        upper_grad.setColorAt(0.5, QColor(60, 40, 32))
        upper_grad.setColorAt(1.0, QColor(30, 20, 18))
        painter.setBrush(upper_grad)
        painter.drawRoundedRect(upper_rect, 22, 22)

        separator = QLinearGradient(-142, 28, 142, 44)
        separator.setColorAt(0.0, QColor(196, 188, 180, 0))
        separator.setColorAt(0.18, QColor(196, 188, 180, 185))
        separator.setColorAt(0.5, QColor(232, 226, 218, 225))
        separator.setColorAt(0.82, QColor(196, 188, 180, 185))
        separator.setColorAt(1.0, QColor(196, 188, 180, 0))
        painter.setBrush(separator)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(QRectF(-142, 30, 284, 14), 7, 7)

        painter.setPen(QPen(QColor(232, 224, 216, 36), 1.0))
        for y in (52, 66, 80, 94):
            painter.drawLine(QPointF(-116, y), QPointF(116, y))

        painter.setPen(Qt.NoPen)
        for dx in (-120, -80, -40, 0, 40, 80, 120):
            painter.setBrush(QColor(184, 160, 146, 170))
            painter.drawEllipse(QPointF(dx, 98), 3.0, 3.0)

        top_grad = QLinearGradient(0, -34, 0, -10)
        top_grad.setColorAt(0.0, QColor(242, 236, 230))
        top_grad.setColorAt(1.0, QColor(196, 188, 180))
        painter.setBrush(top_grad)
        painter.drawRoundedRect(QRectF(-104, -34, 208, 24), 14, 14)

        painter.setBrush(QColor(236, 232, 226, 210))
        for dx, w, h in [(-76, 18, 26), (-36, 16, 30), (0, 18, 32), (36, 16, 29), (76, 15, 26)]:
            painter.drawRoundedRect(QRectF(dx - w / 2, -34, w, h), w / 2, w / 2)

        painter.setBrush(QColor(150, 126, 110, 44))
        for i in range(6):
            y = 48 + i * 10
            painter.drawRoundedRect(QRectF(-132, y, 264, 4), 2, 2)

        gloss = QLinearGradient(-140, 0, 140, 0)
        gloss.setColorAt(0.0, QColor(255, 255, 255, 0))
        gloss.setColorAt(0.5, QColor(255, 255, 255, 34))
        gloss.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setCompositionMode(QPainter.CompositionMode_Screen)
        for i in range(3):
            yy = 10 + i * 16 + math.sin(self.t * 1.6 + i) * 2
            painter.fillRect(QRectF(-136, yy, 272, 4), gloss)
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

        dot_colors = [
            QColor(214, 210, 206),
            QColor(182, 172, 166),
            QColor(148, 136, 128),
            QColor(180, 148, 118),
        ]
        dots = [(-92, 4), (-52, 0), (-12, 6), (30, 2), (82, 4), (-74, 34), (-26, 38), (18, 34), (70, 36)]
        for i, (dx, dy) in enumerate(dots):
            c = QColor(dot_colors[i % len(dot_colors)])
            c.setAlpha(190)
            painter.setBrush(c)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPointF(dx, dy), 4.8, 4.8)

        self.draw_candles(painter, p)

        painter.restore()

    def draw_candles(self, painter: QPainter, p):
        if p <= 0.34:
            return
        reveal = clamp((p - 0.34) / 0.28, 0.0, 1.0)
        flame = clamp((p - 0.54) / 0.20, 0.0, 1.0)
        positions = [-54, 0, 54]
        colors = [
            QColor(214, 208, 198),
            QColor(164, 154, 148),
            QColor(180, 132, 100),
        ]

        for i, x in enumerate(positions):
            h = 62 * reveal
            y = -30 - h
            c = QColor(colors[i])
            c.setAlpha(230)
            painter.setBrush(c)
            painter.setPen(QPen(QColor(240, 236, 232, 96), 1))
            painter.drawRoundedRect(QRectF(x - 7, y, 14, h), 5, 5)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(235, 232, 228, 120))
            painter.drawRoundedRect(QRectF(x - 3.0, y + 6, 2.4, max(6, h * 0.62)), 1.2, 1.2)
            if flame > 0:
                self.draw_flame(painter, x, y - 10, flame, i)

    def draw_flame(self, painter: QPainter, x, y, p, idx):
        beat = 0.88 + 0.12 * math.sin(self.t * 13.0 + idx)
        height = 24 * p * beat
        width = 12 * p * beat
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(182, 138, 86, int(100 * p)))
        painter.drawEllipse(QPointF(x, y - 2), 24 * p, 24 * p)

        path = QPainterPath()
        path.moveTo(x, y - height * 0.95)
        path.cubicTo(x + width, y - height * 0.66, x + width * 1.05, y - height * 0.05, x, y + height * 0.54)
        path.cubicTo(x - width * 1.05, y - height * 0.05, x - width, y - height * 0.66, x, y - height * 0.95)
        painter.setBrush(QColor(176, 128, 84, int(200 * p)))
        painter.drawPath(path)

        inner = QPainterPath()
        inner.moveTo(x, y - height * 0.68)
        inner.cubicTo(x + width * 0.50, y - height * 0.45, x + width * 0.36, y - height * 0.02, x, y + height * 0.18)
        inner.cubicTo(x - width * 0.36, y - height * 0.02, x - width * 0.50, y - height * 0.45, x, y - height * 0.68)
        painter.setBrush(QColor(244, 236, 222, int(180 * p)))
        painter.drawPath(inner)

        if p > 0.35:
            for j in range(2):
                ang = math.tau * (0.18 + 0.22 * j) + self.t * 6.2 + idx
                sx = x + math.cos(ang) * 4
                sy = y - height * 0.55 + math.sin(ang) * 4
                painter.setBrush(QColor(220, 214, 208, int(120 * p)))
                painter.drawEllipse(QPointF(sx, sy), 1.2, 1.2)

    def draw_text(self, painter: QPainter):
        p = self.cake_progress()
        if p <= 0.38:
            return
        alpha = int(255 * clamp((p - 0.38) / 0.36, 0.0, 1.0))
        _, base_y = self.cake_center()
        rect = QRectF(0, base_y + 116, self.w, 70)

        painter.save()
        halo = QRadialGradient(self.cx, base_y + 124, 260)
        halo.setColorAt(0.0, QColor(42, 58, 76, 132))
        halo.setColorAt(0.38, QColor(32, 46, 64, 78))
        halo.setColorAt(0.72, QColor(22, 34, 50, 28))
        halo.setColorAt(1.0, QColor(16, 24, 38, 0))
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        painter.setBrush(halo)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(self.cx, base_y + 124), 250, 64)

        text_bar = QLinearGradient(self.cx - 210, 0, self.cx + 210, 0)
        text_bar.setColorAt(0.0, QColor(9, 15, 25, 0))
        text_bar.setColorAt(0.18, QColor(12, 22, 36, 108))
        text_bar.setColorAt(0.5, QColor(16, 29, 46, 150))
        text_bar.setColorAt(0.82, QColor(12, 22, 36, 108))
        text_bar.setColorAt(1.0, QColor(9, 15, 25, 0))
        painter.setBrush(text_bar)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(QRectF(self.cx - 220, base_y + 108, 440, 56), 28, 28)

        painter.setPen(QPen(QColor(112, 142, 170, int(alpha * 0.34)), 1.0))
        painter.drawLine(QPointF(self.cx - 150, base_y + 166), QPointF(self.cx + 150, base_y + 166))

        painter.setFont(QFont("Microsoft YaHei", 32, QFont.Bold))
        painter.setPen(QColor(14, 14, 16, int(alpha * 0.42)))
        painter.drawText(rect.translated(2, 2), Qt.AlignCenter, "老己生日快乐")
        painter.setPen(QColor(248, 244, 238, alpha))
        painter.drawText(rect, Qt.AlignCenter, "老己生日快乐")
        painter.restore()

    def paintEvent(self, event):
        painter = QPainter(self)
        self.draw_background(painter)
        self.draw_fireworks(painter)
        self.draw_rings(painter)
        self.draw_cake(painter)
        self.draw_text(painter)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Escape, Qt.Key_Q):
            self.close()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    win = DarkCakeShow()
    win.showFullScreen()
    sys.exit(app.exec())
