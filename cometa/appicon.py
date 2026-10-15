"""The application icon, painted at every size the OS might ask for."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QIcon, QLinearGradient, QPainter,
                           QPainterPath, QPen, QPixmap, QRadialGradient)

from . import theme

SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)


def _render(size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = float(size)
    tile = QRectF(0, 0, s, s).adjusted(s * 0.03, s * 0.03, -s * 0.03, -s * 0.03)
    radius = s * 0.24

    bg = QLinearGradient(tile.topLeft(), tile.bottomRight())
    bg.setColorAt(0.0, QColor("#1F1F2B"))
    bg.setColorAt(1.0, QColor("#0B0B11"))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(bg)
    p.drawRoundedRect(tile, radius, radius)
    if size >= 32:
        p.setPen(QPen(theme.alpha(theme.WHITE, 0.10), max(1.0, s / 128)))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(tile.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)

    accent = theme.ACCENTS[0]
    c = tile.center()
    R = s * 0.27
    width = max(1.6, s * 0.075)
    ring = QRectF(c.x() - R, c.y() - R, 2 * R, 2 * R)

    p.setPen(QPen(theme.alpha(theme.WHITE, 0.12), width))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(ring)

    head_deg = 300.0  # clockwise from 12 o'clock
    qt_head = 90.0 - head_deg
    grad = QConicalGradient(c, qt_head)
    grad.setColorAt(0.0, theme.mix(accent.end, theme.WHITE, 0.15))
    grad.setColorAt(0.5, accent.start)
    grad.setColorAt(0.84, theme.alpha(accent.start, 0.0))
    grad.setColorAt(1.0, theme.mix(accent.end, theme.WHITE, 0.15))
    arc = QPainterPath()
    arc.arcMoveTo(ring, qt_head)
    arc.arcTo(ring, qt_head, 300)
    pen = QPen(QBrush(grad), width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.strokePath(arc, pen)

    arc.arcMoveTo(ring, qt_head)
    head = arc.currentPosition()
    if size >= 24:
        glow = QRadialGradient(head, width * 2.2)
        glow.setColorAt(0.0, theme.alpha(accent.end, 0.6))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow)
        p.drawEllipse(head, width * 2.2, width * 2.2)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#FFFFFF"))
    p.drawEllipse(head, width * 0.62, width * 0.62)

    if size >= 32:
        p.setBrush(theme.alpha(theme.WHITE, 0.85))
        p.drawEllipse(QPointF(c), s * 0.028, s * 0.028)
    p.end()
    return pm


def app_icon() -> QIcon:
    icon = QIcon()
    for size in SIZES:
        icon.addPixmap(_render(size))
    return icon
