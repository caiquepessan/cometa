"""One stopwatch card: a floating pane of frosted glass with header, dial and controls."""
from __future__ import annotations

import math

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (QBrush, QColor, QLinearGradient, QPainter, QPen, QPixmap,
                           QRadialGradient, QTransform)
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from . import icons, theme
from .dial import Dial
from .glass import WallpaperGlass
from .model import IDLE, PAUSED, RUNNING, Stopwatch
from .widgets import AccentDot, IconButton, NameField, PrimaryButton, Tween

CARD_WIDTH = 320
CARD_HEIGHT = 448
RADIUS = 26.0


class StopwatchCard(QWidget):
    toggle_requested = Signal(object)  # start / pause / resume
    stop_requested = Signal(object)
    reset_requested = Signal(object)
    remove_requested = Signal(object)
    rename_requested = Signal(object, str)
    recolor_requested = Signal(object)

    def __init__(self, sw: Stopwatch, glass: WallpaperGlass | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.sw = sw
        self._accent = theme.accent(sw.accent)
        self._glass = glass
        self._removable = True
        self._layer: QPixmap | None = None
        self._layer_key: tuple | None = None
        self.setFixedSize(CARD_WIDTH, CARD_HEIGHT)
        self._live = Tween(self, 1.0 if sw.running else 0.0, 480)
        self._hover = Tween(self, 0.0, 180, on_change=self._on_hover)

        self.dot = AccentDot(self._accent)
        self.name = NameField(sw.name, self._accent)
        self.delete_btn = IconButton(icons.trash, size=30, icon_size=16, variant="plain",
                                     danger=True, tooltip="Remover cronômetro")
        self.delete_btn.set_reveal(0.0)
        self.dial = Dial(sw, self._accent)
        self.reset_btn = IconButton(icons.reset, size=52, icon_size=20, variant="ghost",
                                    tooltip="Zerar")
        self.primary = PrimaryButton(self._accent)
        self.stop_btn = IconButton(icons.stop, size=52, icon_size=17, variant="ghost",
                                   danger=True, tooltip="Parar (finaliza a contagem)")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 20)
        layout.setSpacing(0)
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        header.addWidget(self.dot)
        header.addWidget(self.name, 1)
        header.addWidget(self.delete_btn)
        layout.addLayout(header)
        layout.addStretch(1)
        layout.addWidget(self.dial, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(1)
        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(10)
        controls.addWidget(self.reset_btn)
        controls.addWidget(self.primary, 1)
        controls.addWidget(self.stop_btn)
        layout.addLayout(controls)

        self.primary.clicked.connect(lambda: self.toggle_requested.emit(self))
        self.stop_btn.clicked.connect(lambda: self.stop_requested.emit(self))
        self.reset_btn.clicked.connect(lambda: self.reset_requested.emit(self))
        self.delete_btn.clicked.connect(lambda: self.remove_requested.emit(self))
        self.dot.clicked.connect(lambda: self.recolor_requested.emit(self))
        self.name.committed.connect(lambda text: self.rename_requested.emit(self, text))
        self.sync(animate=False)

    def sync(self, animate: bool = True) -> None:
        """Bring every control in line with the stopwatch state."""
        status = self.sw.status
        mode = {RUNNING: PrimaryButton.PAUSE, PAUSED: PrimaryButton.RESUME}.get(
            status, PrimaryButton.START)
        self.primary.set_mode(mode, animate)
        self.reset_btn.setEnabled(status != IDLE)
        self.stop_btn.setEnabled(status in (RUNNING, PAUSED))
        running = status == RUNNING
        self.dial.set_running(running, animate)
        if animate:
            self._live.to(1.0 if running else 0.0)
        else:
            self._live.set(1.0 if running else 0.0)
        self.dial.update()

    def set_accent(self, index: int) -> None:
        self._accent = theme.accent(index)
        for widget in (self.dot, self.name, self.dial, self.primary):
            widget.set_accent(self._accent)
        self.update()

    def set_removable(self, removable: bool) -> None:
        self._removable = removable
        self._on_hover(self._hover.value)

    def _on_hover(self, value: float) -> None:
        self.delete_btn.set_reveal(value if self._removable else 0.0)
        self.update()

    def enterEvent(self, event) -> None:
        self._hover.to(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover.to(0.0)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        # The window has no title bar: the card itself is the handle to move it.
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self.window().windowHandle()
            if handle is not None and handle.startSystemMove():
                event.accept()
                return
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:
        # The dial repaints many times a second on top of this card, while the glass only
        # changes on hover/running transitions or when the window moves: cache it.
        dpr = self.devicePixelRatioF()
        glass = self._glass.pixmap_for(self.screen()) if self._glass is not None else None
        origin = self.mapToGlobal(QPoint(0, 0))
        key = (self.size().toTuple(), dpr, self._accent.name, round(self._live.value * 48),
               round(self._hover.value * 24), origin.toTuple() if glass else None,
               self._glass.version if glass else None)
        if key != self._layer_key:
            self._layer = self._render_glass(dpr, glass, origin)
            self._layer_key = key
        QPainter(self).drawPixmap(0, 0, self._layer)

    def _render_glass(self, dpr: float, glass, origin: QPoint) -> QPixmap:
        pm = QPixmap(math.ceil(self.width() * dpr), math.ceil(self.height() * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        live, hover, a = self._live.value, self._hover.value, self._accent
        p.setPen(Qt.PenStyle.NoPen)

        # What the glass sees: the blurred wallpaper right behind this card on screen.
        if glass is not None:
            pixmap, screen_geo = glass
            offset = origin - screen_geo.topLeft()
            backdrop = QBrush(pixmap)
            backdrop.setTransform(QTransform.fromTranslate(-offset.x(), -offset.y()))
            p.setBrush(backdrop)
        else:
            backdrop = QLinearGradient(r.topLeft(), r.bottomRight())
            backdrop.setColorAt(0.0, QColor("#1C1C2B"))
            backdrop.setColorAt(1.0, QColor("#0B0B11"))
            p.setBrush(backdrop)
        p.drawRoundedRect(r, RADIUS, RADIUS)

        # Frosted glass: a translucent dark base keeps the digits legible over any
        # wallpaper, then the sheen and a specular bloom where the light hits.
        p.setBrush(QColor(12, 12, 18, 64))
        p.drawRoundedRect(r, RADIUS, RADIUS)
        p.setBrush(theme.glass_sheen(r, 1.35 + 0.3 * hover))
        p.drawRoundedRect(r, RADIUS, RADIUS)
        bloom = QRadialGradient(QPointF(r.left() + r.width() * 0.2, r.top()), r.width() * 0.95)
        bloom.setColorAt(0.0, theme.alpha(theme.WHITE, 0.10))
        bloom.setColorAt(1.0, theme.alpha(theme.WHITE, 0.0))
        p.setBrush(bloom)
        p.drawRoundedRect(r, RADIUS, RADIUS)

        if live > 0.001:  # the running dial tints the glass with its color
            center = QPointF(self.dial.geometry().center())
            glow = QRadialGradient(center, 240)
            glow.setColorAt(0.0, theme.alpha(a.start, 0.17 * live))
            glow.setColorAt(0.6, theme.alpha(a.end, 0.045 * live))
            glow.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.setBrush(glow)
            p.drawRoundedRect(r, RADIUS, RADIUS)

        k = 0.6 * live
        top = theme.mix(theme.alpha(theme.WHITE, 0.40 + 0.10 * hover), theme.alpha(a.start, 0.9), k)
        bottom = theme.mix(theme.alpha(theme.WHITE, 0.07), theme.alpha(a.end, 0.28), k)
        p.setPen(theme.rim_pen(r, top, bottom, diagonal=True))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r, RADIUS, RADIUS)

        edge = QLinearGradient(r.topLeft(), r.topRight())
        edge.setColorAt(0.0, theme.alpha(theme.WHITE, 0.0))
        edge.setColorAt(0.35, theme.alpha(theme.WHITE, 0.32))
        edge.setColorAt(1.0, theme.alpha(theme.WHITE, 0.0))
        p.setPen(QPen(QBrush(edge), 1))
        p.drawLine(QPointF(r.left() + RADIUS, r.top() + 1), QPointF(r.right() - RADIUS, r.top() + 1))
        p.end()
        return pm
