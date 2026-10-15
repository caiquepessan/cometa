"""The dial: a seconds ring with a sweeping comet, tick marks and the time readout.

It repaints ~30 times a second while running, so everything that does not change from
frame to frame is pre-rendered once: the full-length comet is a sprite that only gets
rotated into place, and every digit group / label is a cached pixmap.
"""
from __future__ import annotations

import math
import time
from datetime import date, datetime
from functools import lru_cache

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QFont, QFontMetricsF, QPainter,
                           QPainterPath, QPen, QPixmap, QRadialGradient)
from PySide6.QtWidgets import QWidget

from . import theme
from .model import Stopwatch, split_time
from .theme import Accent
from .widgets import Tween

COMET_DEG = 110.0  # length of the glowing trail behind the moving head
COMET_PASSES = ((18.0, 0.06), (9.0, 0.15), (3.2, 1.0))  # (pen width, opacity) glow layers
READOUT_HALF_PX = 88  # readout size in half pixels (44 px)
TRANSPARENT = QColor(0, 0, 0, 0)


class _Type:
    """Readout typography at one size: fonts and metrics."""

    def __init__(self, size: float) -> None:
        self.main = theme.font(size, 300, display=True, tabular=True)
        self.frac = theme.font(size * 0.45, 400, display=True, tabular=True)
        fm, ff = QFontMetricsF(self.main), QFontMetricsF(self.frac)
        self.digit = max(fm.horizontalAdvance(d) for d in "0123456789")
        self.colon = fm.horizontalAdvance(":")
        self.frac_width = ff.horizontalAdvance(".00")
        self.cap = fm.capHeight()

    def advance(self, text: str) -> float:
        return sum(self.colon if ch == ":" else self.digit for ch in text)


@lru_cache(maxsize=16)
def _type(half_px: int) -> _Type:
    return _Type(half_px / 2)


@lru_cache(maxsize=1)
def _status_font() -> tuple[QFont, QFontMetricsF]:
    f = theme.font(10.5, 650, spacing=1.8, smooth=True)
    return f, QFontMetricsF(f)


@lru_cache(maxsize=1)
def _hint_font() -> tuple[QFont, QFontMetricsF]:
    f = theme.font(11.5, 450, smooth=True)
    return f, QFontMetricsF(f)


@lru_cache(maxsize=2048)
def _text_sprite(kind: str, text: str, half_px: int, rgba: int,
                 dpr: float) -> tuple[QPixmap, float, float]:
    """Pre-rendered text: (pixmap, left padding, baseline offset). Digits are filled as
    outlines for smooth grayscale edges; labels use regular text rendering."""
    if kind in ("main", "frac"):
        t = _type(half_px)
        font = t.main if kind == "main" else t.frac
    else:
        font = (_status_font() if kind == "status" else _hint_font())[0]
    fm = QFontMetricsF(font)
    pad = 2.0
    width = fm.horizontalAdvance(text) + 2 * pad
    height = fm.ascent() + fm.descent() + 2 * pad
    pm = QPixmap(math.ceil(width * dpr), math.ceil(height * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = QColor.fromRgba(rgba)
    baseline = pad + fm.ascent()
    if kind in ("main", "frac"):
        path = QPainterPath()
        path.addText(pad, baseline, font, text)
        p.fillPath(path, color)
    else:
        p.setFont(font)
        p.setPen(color)
        p.drawText(QPointF(pad, baseline), text)
    p.end()
    return pm, pad, baseline


@lru_cache(maxsize=256)
def _comet_colors(accent: int, energy: int) -> tuple[tuple[QColor, QColor, QColor], ...]:
    a = theme.accent(accent)
    head = theme.mix(a.end, theme.WHITE, 0.18)
    e = energy / 40
    return tuple((theme.alpha(head, e * gain), theme.alpha(a.start, 0.55 * e * gain),
                  theme.alpha(a.start, 0.0)) for _, gain in COMET_PASSES)


def _stroke_comet(p: QPainter, c: QPointF, R: float, qt_head: float, span: float,
                  accent: int, energy: int) -> None:
    rect = QRectF(c.x() - R, c.y() - R, 2 * R, 2 * R)
    path = QPainterPath()
    path.arcMoveTo(rect, qt_head)
    path.arcTo(rect, qt_head, span)  # from the head back along the trail
    frac = span / 360.0
    for (width, _), (bright, mid, clear) in zip(COMET_PASSES, _comet_colors(accent, energy)):
        grad = QConicalGradient(c, qt_head)
        grad.setColorAt(0.0, bright)
        grad.setColorAt(frac * 0.45, mid)
        grad.setColorAt(frac, clear)
        grad.setColorAt(1.0, bright)
        pen = QPen(QBrush(grad), width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.strokePath(path, pen)


def _head_glow(p: QPainter, hp: QPointF, a: Accent, e: float) -> None:
    glow = QRadialGradient(hp, 20)
    glow.setColorAt(0.0, theme.alpha(a.end, 0.55 * e))
    glow.setColorAt(1.0, TRANSPARENT)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(glow)
    p.drawEllipse(hp, 20, 20)
    p.setBrush(theme.alpha(theme.mix(a.end, theme.WHITE, 0.7), 0.45 + 0.55 * e))
    p.drawEllipse(hp, 4.3, 4.3)


@lru_cache(maxsize=64)
def _comet_sprite(accent: int, energy: int, size: int, dpr: float) -> tuple[QPixmap, QPointF]:
    """The full-length comet with its head at 12 o clock, ready to be rotated into place.
    Returns the pixmap cropped to the trail and where its top-left sits on the dial."""
    c = QPointF(size / 2, size / 2)
    R = size / 2 - 16
    full = QPixmap(math.ceil(size * dpr), math.ceil(size * dpr))
    full.setDevicePixelRatio(dpr)
    full.fill(Qt.GlobalColor.transparent)
    p = QPainter(full)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    _stroke_comet(p, c, R, 90.0, COMET_DEG, accent, energy)
    _head_glow(p, QPointF(c.x(), c.y() - R), theme.accent(accent), energy / 40)
    p.end()
    # The trail runs counter-clockwise from the top: keep only the area it can touch.
    reach = 22.0
    tail_y = c.y() - R * math.cos(math.radians(COMET_DEG))
    crop = QRectF(QPointF(c.x() - R - reach, c.y() - R - reach),
                  QPointF(c.x() + reach, tail_y + reach)).intersected(QRectF(0, 0, size, size))
    src = QRectF(crop.x() * dpr, crop.y() * dpr, crop.width() * dpr, crop.height() * dpr)
    sprite = full.copy(src.toAlignedRect())
    sprite.setDevicePixelRatio(dpr)
    return sprite, crop.topLeft()


@lru_cache(maxsize=1024)
def _lit_tick_pen(accent: int, level: int, major: bool, energy: int) -> QPen:
    a = theme.accent(accent)
    k = level / 16
    color = theme.mix(a.start, theme.WHITE, 0.25 * k)
    pen = QPen(theme.alpha(color, (0.18 + 0.82 * k) * (energy / 40) * (1.0 if major else 0.75)),
               1.6 if major else 1.1)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    return pen


class Dial(QWidget):
    def __init__(self, sw: Stopwatch, accent: Accent, size: int = 272,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.sw = sw
        self._accent = accent
        self._live = Tween(self, 1.0 if sw.running else 0.0, 480)
        self._static: QPixmap | None = None
        self._ticks: list[tuple[QPointF, QPointF, bool]] | None = None
        self._hint_key: tuple | None = None
        self._hint = ""
        self.setFixedSize(size, size)

    def set_accent(self, accent: Accent) -> None:
        self._accent = accent
        self.update()

    def set_running(self, running: bool, animate: bool = True) -> None:
        target = 1.0 if running else 0.0
        if animate:
            self._live.to(target)
        else:
            self._live.set(target)

    def resizeEvent(self, event) -> None:
        self._static = None
        self._ticks = None
        super().resizeEvent(event)

    def _geometry(self) -> tuple[QPointF, float]:
        c = QPointF(self.width() / 2, self.height() / 2)
        return c, min(self.width(), self.height()) / 2 - 16

    @staticmethod
    def _polar(c: QPointF, radius: float, deg_cw_from_top: float) -> QPointF:
        rad = math.radians(deg_cw_from_top)
        return QPointF(c.x() + math.sin(rad) * radius, c.y() - math.cos(rad) * radius)

    def _tick_lines(self) -> list[tuple[QPointF, QPointF, bool]]:
        if self._ticks is None:
            c, R = self._geometry()
            self._ticks = [(self._polar(c, R - (18 if i % 5 == 0 else 15), i * 6),
                            self._polar(c, R - 10, i * 6), i % 5 == 0) for i in range(60)]
        return self._ticks

    def _static_layer(self) -> QPixmap:
        dpr = self.devicePixelRatioF()
        if self._static is not None and self._static.devicePixelRatio() == dpr:
            return self._static
        pm = QPixmap(math.ceil(self.width() * dpr), math.ceil(self.height() * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c, R = self._geometry()
        p.setPen(QPen(theme.alpha(theme.WHITE, 0.08), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(c, R, R)
        for inner, outer, major in self._tick_lines():
            pen = QPen(theme.alpha(theme.WHITE, 0.22 if major else 0.10), 1.6 if major else 1.0)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawLine(inner, outer)
        p.end()
        self._static = pm
        return pm

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.drawPixmap(0, 0, self._static_layer())

        c, R = self._geometry()
        elapsed = self.sw.elapsed()
        energy = round((0.40 + 0.60 * self._live.value) * 40)  # stopped dials glow dimmer
        if elapsed > 0 or self.sw.running:
            head = (elapsed % 60.0) * 6.0
            span = min(elapsed * 6.0, COMET_DEG)
            self._paint_comet(p, c, R, head, span, energy)
        else:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.alpha(self._accent.start, 0.55))
            p.drawEllipse(self._polar(c, R, 0), 3.2, 3.2)
        self._paint_readout(p, c, R, elapsed)

    def _paint_comet(self, p: QPainter, c: QPointF, R: float, head: float, span: float,
                     energy: int) -> None:
        accent = theme.ACCENTS.index(self._accent)
        if span >= COMET_DEG and self.width() == self.height():
            # Steady state: rotate the pre-rendered comet into place.
            sprite, origin = _comet_sprite(accent, energy, self.width(), self.devicePixelRatioF())
            p.save()
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            p.translate(c)
            p.rotate(head)
            p.translate(-c)
            p.drawPixmap(origin, sprite)
            p.restore()
        else:  # the trail is still growing (first seconds): stroke it live
            if span > 0.2:
                _stroke_comet(p, c, R, 90.0 - head, span, accent, energy)
            _head_glow(p, self._polar(c, R, head), self._accent, energy / 40)

        # Tick marks light up as the head passes and fade along the trail.
        if span > 0.2:
            ticks = self._tick_lines()
            for j in range(math.ceil((head - span) / 6.0), math.floor(head / 6.0) + 1):
                inner, outer, major = ticks[j % 60]
                level = round(16 * (1.0 - (head - j * 6.0) / span) ** 1.3)
                p.setPen(_lit_tick_pen(accent, level, major, energy))
                p.drawLine(inner, outer)

    def _paint_readout(self, p: QPainter, c: QPointF, R: float, elapsed: float) -> None:
        h, m, s, cs = split_time(elapsed)
        running = self.sw.running
        idle = elapsed <= 0 and not running
        groups = (f"{h:02d}", ":", f"{m:02d}", ":", f"{s:02d}")
        dim = (h == 0, False, h == 0 and m == 0, False, False)
        gap = 3.0

        half_px = READOUT_HALF_PX
        t = _type(half_px)
        total = t.advance("".join(groups)) + gap + t.frac_width
        avail = 2 * (R - 30)
        if total > avail:  # 100+ hours: shrink to fit the ring
            half_px = max(20, int(half_px * avail / total))
            t = _type(half_px)
            total = t.advance("".join(groups)) + gap + t.frac_width

        brightness = 1.0 if running else (0.55 if idle else 0.86)
        base = theme.alpha(theme.TEXT, brightness).rgba()
        faded = base if idle else theme.alpha(theme.TEXT, 0.34 * brightness).rgba()
        colon = theme.alpha(theme.TEXT, 0.42 * brightness).rgba()
        dpr = self.devicePixelRatioF()
        x = c.x() - total / 2
        baseline = c.y() + t.cap / 2 + 4
        for text, is_dim in zip(groups, dim):
            color = colon if text == ":" else (faded if is_dim else base)
            self._blit_text(p, "main", text, half_px, color, dpr, x, baseline)
            x += t.advance(text)
        self._blit_text(p, "frac", f".{cs:02d}", half_px,
                        theme.alpha(theme.MUTED, 0.6 if idle else 0.9).rgba(), dpr, x + gap, baseline)

        self._paint_status(p, c, running, idle, baseline - t.cap - 22, dpr)
        hint = self._session_hint()
        if hint:
            _, fm = _hint_font()
            level = round(0.75 * (0.4 + 0.6 * self._live.value) * 20) / 20
            self._blit_text(p, "hint", hint, 0, theme.alpha(theme.MUTED, level).rgba(), dpr,
                            c.x() - fm.horizontalAdvance(hint) / 2, baseline + 30)

    @staticmethod
    def _blit_text(p: QPainter, kind: str, text: str, half_px: int, rgba: int, dpr: float,
                   x: float, baseline: float) -> None:
        pm, pad, top = _text_sprite(kind, text, half_px, rgba, dpr)
        p.drawPixmap(QPointF(round(x - pad), round(baseline - top)), pm)

    def _session_hint(self) -> str:
        """When the current run began: handy once a stopwatch has run for days."""
        started = self.sw.started_at
        if started is None:
            return ""
        key = (started, self.sw.accumulated > 0, date.today())
        if key != self._hint_key:
            start = datetime.fromtimestamp(started)
            days = (key[2] - start.date()).days
            verb = "retomado" if key[1] else "iniciado"
            if days <= 0:
                self._hint = f"{verb} às {start:%H:%M}"
            elif days == 1:
                self._hint = f"{verb} ontem às {start:%H:%M}"
            else:
                self._hint = f"{verb} em {start:%d/%m} às {start:%H:%M}"
            self._hint_key = key
        return self._hint

    def _paint_status(self, p: QPainter, c: QPointF, running: bool, idle: bool, y: float,
                      dpr: float) -> None:
        a = self._accent
        if running:
            label, color = "RODANDO", theme.mix(a.start, theme.WHITE, 0.3)
        elif idle:
            label, color = "PRONTO", theme.alpha(theme.MUTED, 0.85)
        elif self.sw.finished:
            label, color = "FINALIZADO", theme.MUTED
        else:
            label, color = "PAUSADO", theme.MUTED
        _, fm = _status_font()
        text_w = fm.horizontalAdvance(label) - 1.8  # drop trailing letter spacing
        dot_w = 0.0 if idle else 12.0
        x = c.x() - (text_w + dot_w) / 2
        if not idle:
            dot = QPointF(x + 3, y - fm.capHeight() / 2)
            p.setPen(Qt.PenStyle.NoPen)
            if running:
                phase = (time.monotonic() % 1.6) / 1.6
                p.setBrush(theme.alpha(a.start, 0.45 * (1 - phase)))
                p.drawEllipse(dot, 3 + 5 * phase, 3 + 5 * phase)
                p.setBrush(theme.mix(a.start, theme.WHITE, 0.2))
            else:
                p.setBrush(theme.alpha(theme.MUTED, 0.8))
            p.drawEllipse(dot, 3, 3)
        self._blit_text(p, "status", label, 0, color.rgba(), dpr, x + dot_w, y)
