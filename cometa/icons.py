"""Vector icons painted on a 24x24 grid, so they stay crisp at any size."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPolygonF

GRID = 24.0


class _Grid:
    """Maps the 24-unit icon grid onto `rect` for the duration of a `with` block."""

    def __init__(self, painter: QPainter, rect: QRectF) -> None:
        self.p = painter
        self.rect = rect

    def __enter__(self) -> QPainter:
        p, r = self.p, self.rect
        p.save()
        scale = min(r.width(), r.height()) / GRID
        p.translate(r.center().x() - GRID * scale / 2, r.center().y() - GRID * scale / 2)
        p.scale(scale, scale)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        return p

    def __exit__(self, *exc) -> None:
        self.p.restore()


def _pen(color: QColor, width: float = 2.0) -> QPen:
    pen = QPen(color, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


_PLAY = ((8.2, 5.2), (19.0, 12.0), (19.0, 12.0), (8.2, 18.8))
_STOP = ((7.0, 7.0), (17.0, 7.0), (17.0, 17.0), (7.0, 17.0))


def play_stop(p: QPainter, rect: QRectF, color: QColor, t: float = 0.0) -> None:
    """Filled play triangle that morphs into a stop square as `t` goes 0 → 1.

    Slight overshoot outside [0, 1] is allowed so springy easing curves read as a bounce.
    """
    t = max(-0.15, min(1.15, t))
    pts = [QPointF(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t) for a, b in zip(_PLAY, _STOP)]
    with _Grid(p, rect) as g:
        g.setPen(_pen(color, 2.4))
        g.setBrush(color)
        g.drawPolygon(QPolygonF(pts))


# The play triangle split into two halves, each of which becomes one pause bar.
_PLAY_HALVES = (((8.2, 5.2), (13.6, 8.6), (13.6, 15.4), (8.2, 18.8)),
                ((13.6, 8.6), (19.0, 12.0), (19.0, 12.0), (13.6, 15.4)))
_PAUSE_BARS = (((6.6, 5.6), (9.2, 5.6), (9.2, 18.4), (6.6, 18.4)),
               ((14.8, 5.6), (17.4, 5.6), (17.4, 18.4), (14.8, 18.4)))


def play_pause(p: QPainter, rect: QRectF, color: QColor, t: float = 0.0) -> None:
    """Play triangle that splits into the two pause bars as `t` goes 0 → 1."""
    t = max(-0.15, min(1.15, t))
    with _Grid(p, rect) as g:
        g.setPen(_pen(color, 2.2))
        g.setBrush(color)
        for half, bar in zip(_PLAY_HALVES, _PAUSE_BARS):
            g.drawPolygon(QPolygonF([QPointF(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
                                     for a, b in zip(half, bar)]))


def play(p: QPainter, rect: QRectF, color: QColor) -> None:
    play_stop(p, rect, color, 0.0)


def minus(p: QPainter, rect: QRectF, color: QColor) -> None:
    with _Grid(p, rect) as g:
        g.setPen(_pen(color, 2.0))
        g.drawLine(QPointF(6, 12), QPointF(18, 12))


def pin(p: QPainter, rect: QRectF, color: QColor, filled: bool = False) -> None:
    """Push pin, used for "always on top"."""
    with _Grid(p, rect) as g:
        g.setPen(_pen(color, 1.8))
        g.setBrush(color if filled else Qt.BrushStyle.NoBrush)
        g.translate(12, 12)
        g.rotate(45)
        g.drawRoundedRect(QRectF(-3.6, -9.2, 7.2, 3.0), 1.2, 1.2)
        g.drawPolygon(QPolygonF([QPointF(-2.4, -6.2), QPointF(2.4, -6.2),
                                 QPointF(4.4, 1.4), QPointF(-4.4, 1.4)]))
        g.drawLine(QPointF(0, 1.4), QPointF(0, 8.6))


def pin_filled(p: QPainter, rect: QRectF, color: QColor) -> None:
    pin(p, rect, color, filled=True)


def stop(p: QPainter, rect: QRectF, color: QColor) -> None:
    play_stop(p, rect, color, 1.0)


def reset(p: QPainter, rect: QRectF, color: QColor) -> None:
    """Counter-clockwise arrow."""
    with _Grid(p, rect) as g:
        g.setPen(_pen(color, 2.0))
        g.setBrush(Qt.BrushStyle.NoBrush)
        circle = QRectF(12 - 7.5, 12.5 - 7.5, 15, 15)
        path = QPainterPath()
        path.arcMoveTo(circle, 170)
        path.arcTo(circle, 170, 290)
        g.drawPath(path)
        end = path.currentPosition()
        theta = math.radians(100)
        d = (-math.sin(theta), -math.cos(theta))  # travel direction at the arrow tip

        def back(angle: float, length: float = 3.9) -> QPointF:
            a = math.radians(angle)
            rx = d[0] * math.cos(a) - d[1] * math.sin(a)
            ry = d[0] * math.sin(a) + d[1] * math.cos(a)
            return QPointF(end.x() - rx * length, end.y() - ry * length)

        g.drawPolyline(QPolygonF([back(40), end, back(-40)]))


def checklist(p: QPainter, rect: QRectF, color: QColor) -> None:
    """Rounded box with a check mark: the task list toggle."""
    with _Grid(p, rect) as g:
        g.setPen(_pen(color, 1.9))
        g.setBrush(Qt.BrushStyle.NoBrush)
        g.drawRoundedRect(QRectF(4, 4, 16, 16), 4.6, 4.6)
        g.drawPolyline(QPolygonF([QPointF(8.3, 12.3), QPointF(11.0, 14.9), QPointF(15.9, 9.5)]))


_CHECK = ((6.4, 12.6), (10.3, 16.3), (17.8, 8.0))


def check(p: QPainter, rect: QRectF, color: QColor, progress: float = 1.0) -> None:
    """Check mark, drawn up to `progress` (0 → 1) of its length so it can animate in."""
    progress = max(0.0, min(1.0, progress))
    if progress <= 0.0:
        return
    segments = list(zip(_CHECK, _CHECK[1:]))
    lengths = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in segments]
    remaining = progress * sum(lengths)
    points = [QPointF(*_CHECK[0])]
    for (a, b), length in zip(segments, lengths):
        k = min(1.0, remaining / length)
        points.append(QPointF(a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k))
        remaining -= length
        if remaining <= 0:
            break
    with _Grid(p, rect) as g:
        g.setPen(_pen(color, 2.6))
        g.drawPolyline(QPolygonF(points))


def plus(p: QPainter, rect: QRectF, color: QColor, width: float = 1.8) -> None:
    with _Grid(p, rect) as g:
        g.setPen(_pen(color, width))
        g.drawLine(QPointF(12, 5), QPointF(12, 19))
        g.drawLine(QPointF(5, 12), QPointF(19, 12))


def close(p: QPainter, rect: QRectF, color: QColor) -> None:
    with _Grid(p, rect) as g:
        g.setPen(_pen(color, 2.0))
        g.drawLine(QPointF(6.5, 6.5), QPointF(17.5, 17.5))
        g.drawLine(QPointF(17.5, 6.5), QPointF(6.5, 17.5))


def trash(p: QPainter, rect: QRectF, color: QColor) -> None:
    with _Grid(p, rect) as g:
        g.setPen(_pen(color, 1.9))
        g.setBrush(Qt.BrushStyle.NoBrush)
        g.drawLine(QPointF(4.5, 6.5), QPointF(19.5, 6.5))
        g.drawPolyline(QPolygonF([QPointF(9.2, 6.5), QPointF(9.2, 4.3), QPointF(14.8, 4.3), QPointF(14.8, 6.5)]))
        body = QPainterPath(QPointF(6.4, 6.5))
        body.lineTo(7.3, 18.6)
        body.quadTo(7.4, 20, 8.8, 20)
        body.lineTo(15.2, 20)
        body.quadTo(16.6, 20, 16.7, 18.6)
        body.lineTo(17.6, 6.5)
        g.drawPath(body)
        g.drawLine(QPointF(10.3, 10.3), QPointF(10.3, 16.2))
        g.drawLine(QPointF(13.7, 10.3), QPointF(13.7, 16.2))


def pencil(p: QPainter, rect: QRectF, color: QColor) -> None:
    with _Grid(p, rect) as g:
        g.setPen(_pen(color, 1.8))
        g.setBrush(Qt.BrushStyle.NoBrush)
        g.translate(12.6, 11.4)
        g.rotate(-45)
        body = QPainterPath()
        body.moveTo(-4.6, -2.6)
        body.lineTo(6.4, -2.6)
        body.quadTo(8.6, -2.6, 8.6, 0)
        body.quadTo(8.6, 2.6, 6.4, 2.6)
        body.lineTo(-4.6, 2.6)
        body.lineTo(-9.4, 0)
        body.closeSubpath()
        g.drawPath(body)
        g.drawLine(QPointF(4.2, -2.6), QPointF(4.2, 2.6))


def stopwatch(p: QPainter, rect: QRectF, color: QColor) -> None:
    with _Grid(p, rect) as g:
        g.setPen(_pen(color, 1.9))
        g.setBrush(Qt.BrushStyle.NoBrush)
        g.drawEllipse(QPointF(12, 13.5), 7.5, 7.5)
        g.drawLine(QPointF(12, 13.5), QPointF(12, 9.6))
        g.drawLine(QPointF(10, 3.2), QPointF(14, 3.2))
        g.drawLine(QPointF(12, 3.2), QPointF(12, 6))
        g.drawLine(QPointF(18.2, 6.6), QPointF(19.6, 5.2))
