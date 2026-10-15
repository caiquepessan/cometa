"""Confirmation shown inside the card it concerns: the card blurs and asks."""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFontMetricsF, QPainter, QPixmap
from PySide6.QtWidgets import (QGraphicsOpacityEffect, QHBoxLayout, QLabel, QSizePolicy,
                               QVBoxLayout, QWidget)

from . import icons, theme
from .glass import blurred
from .theme import Accent
from .widgets import IconPainter, PillButton, Tween

SIDE_MARGIN = 22


class _TimeChip(QWidget):
    """Pill showing the live time at stake."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._text = "00:00:00"
        self._accent: Accent | None = None
        self.setFixedHeight(32)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def set_content(self, text: str, accent: Accent) -> None:
        changed = text != self._text or accent is not self._accent
        self._text, self._accent = text, accent
        if changed:
            self.updateGeometry()
            self.update()

    def sizeHint(self) -> QSize:
        fm = QFontMetricsF(theme.font(14, 500, tabular=True))
        return QSize(int(fm.horizontalAdvance(self._text) + 54), 32)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(theme.rim_pen(r, theme.alpha(theme.WHITE, 0.26), theme.alpha(theme.WHITE, 0.05)))
        p.setBrush(theme.alpha(theme.WHITE, 0.07))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        color = self._accent.start if self._accent else theme.MUTED
        icons.stopwatch(p, QRectF(r.left() + 11, r.center().y() - 8, 16, 16), color)
        p.setFont(theme.font(14, 500, tabular=True))
        p.setPen(theme.TEXT)
        p.drawText(r.adjusted(34, 0, -12, 0),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._text)


class _Badge(QWidget):
    """Tinted circle with the icon of the action being confirmed."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._icon: IconPainter = icons.stop
        self._tint = theme.AMBER
        self.setFixedSize(46, 46)

    def set_look(self, icon: IconPainter, tint: QColor) -> None:
        self._icon, self._tint = icon, tint
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(theme.rim_pen(r, theme.alpha(self._tint, 0.55), theme.alpha(self._tint, 0.15)))
        p.setBrush(theme.alpha(self._tint, 0.14))
        p.drawEllipse(r)
        self._icon(p, r.adjusted(12, 12, -12, -12), theme.mix(self._tint, theme.WHITE, 0.15))


class _Content(QWidget):
    def __init__(self, width: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(width)
        self.badge = _Badge()
        self.title = QLabel()
        self.title.setFont(theme.font(17, 650))
        self.title.setStyleSheet("color: #F2F2F5;")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.body = QLabel()
        self.body.setWordWrap(True)
        self.body.setTextFormat(Qt.TextFormat.RichText)
        self.body.setFont(theme.font(13, 400, rich=True))
        self.body.setStyleSheet("color: #A3A3B0;")
        self.body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.chip = _TimeChip()
        self.cancel = PillButton("Cancelar", "ghost")
        self.confirm = PillButton("Confirmar", "light")
        for button in (self.cancel, self.confirm):
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(10)
        buttons.addWidget(self.cancel)
        buttons.addWidget(self.confirm)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(14)
        layout.addWidget(self.title)
        layout.addSpacing(6)
        layout.addWidget(self.body)
        layout.addSpacing(14)
        layout.addWidget(self.chip, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(24)
        layout.addLayout(buttons)

    def configure(self, title: str, body_html: str, confirm_text: str, variant: str,
                  icon: IconPainter, tint: QColor) -> None:
        self.badge.set_look(icon, tint)
        self.title.setText(title)
        self.body.setText(f'<div style="line-height:118%">{body_html}</div>')
        self.confirm.setText(confirm_text)
        self.confirm.set_variant(variant)


class ConfirmOverlay(QWidget):
    """Covers its card, blurs it and asks for a confirmation."""

    def __init__(self, host: QWidget, radius: float) -> None:
        super().__init__(host)
        self._radius = radius
        self._backdrop: QPixmap | None = None
        self._on_confirm: Callable[[], None] | None = None
        self._chip_source: Callable[[], str] | None = None
        self._chip_accent: Accent | None = None
        self._closing = False
        self._effect: QGraphicsOpacityEffect | None = None
        self.content = _Content(host.width() - 2 * SIDE_MARGIN, self)
        self.content.cancel.clicked.connect(lambda: self.dismiss(False))
        self.content.confirm.clicked.connect(lambda: self.dismiss(True))
        self._fade = Tween(self, 0.0, 220, on_change=self._on_fade)
        self._fade.finished.connect(self._on_fade_done)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.hide()

    def is_open(self) -> bool:
        return self.isVisible() and not self._closing

    def ask(self, *, title: str, body_html: str, confirm_text: str, variant: str,
            icon: IconPainter, tint: QColor, chip: Callable[[], str], accent: Accent,
            on_confirm: Callable[[], None]) -> None:
        if self.isVisible():
            return
        host = self.parentWidget()
        self._backdrop = self._render_backdrop(host)
        self._on_confirm = on_confirm
        self._chip_source, self._chip_accent = chip, accent
        self._closing = False
        self.content.configure(title, body_html, confirm_text, variant, icon, tint)
        self.tick()
        self.content.adjustSize()
        self.setGeometry(host.rect())
        self._set_effect(0.0)
        self.show()
        self.raise_()
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        self._on_fade(0.0)
        self._fade.to(1.0, 220)

    def _render_backdrop(self, host: QWidget) -> QPixmap:
        """The card itself, blurred, dimmed and trimmed to its rounded shape."""
        snap = blurred(host.grab(), 14)
        dpr = snap.devicePixelRatio()
        r = QRectF(host.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        mask = QPixmap(snap.size())
        mask.setDevicePixelRatio(dpr)
        mask.fill(Qt.GlobalColor.transparent)
        mp = QPainter(mask)
        mp.setRenderHint(QPainter.RenderHint.Antialiasing)
        mp.setPen(Qt.PenStyle.NoPen)
        mp.setBrush(QColor(0, 0, 0, 255))
        mp.drawRoundedRect(r, self._radius, self._radius)
        mp.end()
        out = QPixmap(snap.size())
        out.setDevicePixelRatio(dpr)
        out.fill(Qt.GlobalColor.transparent)
        p = QPainter(out)
        p.drawPixmap(0, 0, snap)
        p.fillRect(r, QColor(8, 8, 12, 120))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        p.drawPixmap(0, 0, mask)
        p.end()
        return out

    def tick(self) -> None:
        if self._chip_source is not None and self._chip_accent is not None:
            self.content.chip.set_content(self._chip_source(), self._chip_accent)

    def dismiss(self, confirmed: bool) -> None:
        if not self.isVisible() or self._closing:
            return
        callback = self._on_confirm if confirmed else None
        self._on_confirm = None
        self._closing = True
        self._set_effect(self._fade.value)
        self._fade.to(0.0, 160)
        if callback is not None:
            callback()

    def _set_effect(self, opacity: float) -> None:
        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(opacity)
        self.setGraphicsEffect(self._effect)

    def _on_fade(self, value: float) -> None:
        if self._effect is not None:
            self._effect.setOpacity(value)
        self._place_content(value)

    def _on_fade_done(self) -> None:
        self.setGraphicsEffect(None)  # deletes the effect; full opacity needs none
        self._effect = None
        if self._closing:
            self._closing = False
            self._backdrop = None
            self._chip_source = None
            self.parentWidget().setFocus(Qt.FocusReason.OtherFocusReason)
            self.hide()

    def _place_content(self, progress: float = 1.0) -> None:
        x = (self.width() - self.content.width()) // 2
        y = (self.height() - self.content.height()) // 2 + round((1.0 - progress) * 12)
        self.content.move(x, y)

    def resizeEvent(self, event) -> None:
        self._place_content(self._fade.value)
        super().resizeEvent(event)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._backdrop is not None:
            p.drawPixmap(0, 0, self._backdrop)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(theme.rim_pen(r, theme.alpha(theme.WHITE, 0.40), theme.alpha(theme.WHITE, 0.07),
                               diagonal=True))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r, self._radius, self._radius)

    def mousePressEvent(self, event) -> None:
        if not self.content.geometry().contains(event.position().toPoint()):
            self.dismiss(False)
        event.accept()

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.dismiss(False)
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.dismiss(self.focusWidget() is not self.content.cancel)
        else:
            super().keyPressEvent(event)

    def focusNextPrevChild(self, forward: bool) -> bool:
        order = [self.content.cancel, self.content.confirm]
        current = self.focusWidget()
        index = order.index(current) if current in order else (-1 if forward else len(order))
        order[(index + (1 if forward else -1)) % len(order)].setFocus(Qt.FocusReason.TabFocusReason)
        return True
