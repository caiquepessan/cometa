"""Custom-painted controls: animated buttons and the inline name editor."""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import (QAbstractAnimation, QEasingCurve, QEvent, QObject, QRectF, QSize,
                            Qt, QVariantAnimation, Signal)
from PySide6.QtGui import QColor, QFontMetricsF, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QAbstractButton, QLineEdit, QSizePolicy, QWidget

from . import icons, theme
from .model import MAX_NAME_LENGTH
from .theme import Accent

IconPainter = Callable[[QPainter, QRectF, QColor], None]


class Tween(QObject):
    """A float that eases toward a target and repaints (or notifies) its owner."""

    def __init__(self, owner: QWidget, value: float = 0.0, duration: int = 160,
                 curve: QEasingCurve.Type = QEasingCurve.Type.OutCubic,
                 on_change: Callable[[float], None] | None = None) -> None:
        super().__init__(owner)
        self.value = float(value)
        self._owner = owner
        self._on_change = on_change
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(duration)
        self._anim.setEasingCurve(curve)
        self._anim.valueChanged.connect(self._step)

    @property
    def finished(self):
        return self._anim.finished

    def _step(self, v) -> None:
        self.value = float(v)
        if self._on_change is not None:
            self._on_change(self.value)
        else:
            self._owner.update()

    def to(self, target: float, duration: int | None = None) -> None:
        target = float(target)
        if self._anim.state() == QAbstractAnimation.State.Running:
            if self._anim.endValue() == target:
                return
            self._anim.stop()
        elif abs(self.value - target) < 1e-6:
            return
        if duration is not None:
            self._anim.setDuration(duration)
        self._anim.setStartValue(self.value)
        self._anim.setEndValue(target)
        self._anim.start()

    def set(self, value: float) -> None:
        self._anim.stop()
        self._step(float(value))


class _Button(QAbstractButton):
    """Base for painted buttons: hover/press easing, pointer cursor, keyboard focus ring."""

    def __init__(self, parent: QWidget | None = None, hover_ms: int = 150) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # Clicking takes focus (so an open name editor commits), but the focus ring
        # only shows for keyboard navigation.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._focus_visible = False
        self.hover = Tween(self, 0.0, hover_ms)
        self.press = Tween(self, 0.0, 90)

    def focusInEvent(self, event) -> None:
        self._focus_visible = event.reason() in (Qt.FocusReason.TabFocusReason,
                                                 Qt.FocusReason.BacktabFocusReason)
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:
        self._focus_visible = False
        self.update()
        super().focusOutEvent(event)

    def enterEvent(self, event) -> None:
        self.hover.to(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.hover.to(0.0)
        self.press.to(0.0)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.press.to(1.0)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self.press.to(0.0)
        super().mouseReleaseEvent(event)

    def changeEvent(self, event) -> None:
        if event.type() == QEvent.Type.EnabledChange:
            self.setCursor(Qt.CursorShape.PointingHandCursor if self.isEnabled()
                           else Qt.CursorShape.ArrowCursor)
            if not self.isEnabled():
                self.hover.set(0.0)
                self.press.set(0.0)
            self.update()
        super().changeEvent(event)

    def _h(self) -> float:
        return self.hover.value if self.isEnabled() else 0.0

    def _focus_ring(self, p: QPainter, rect: QRectF, radius: float) -> None:
        if self.hasFocus() and self._focus_visible:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(theme.alpha(theme.WHITE, 0.55), 1.5))
            r = rect.adjusted(-2.5, -2.5, 2.5, 2.5)
            p.drawRoundedRect(r, radius + 2.5, radius + 2.5)


class IconButton(_Button):
    """Round icon button. `ghost` has a resting outline, `bead` adds a dark glass base so
    it reads over any background, `plain` only shows on hover."""

    def __init__(self, icon: IconPainter, *, size: int = 40, icon_size: int = 18,
                 variant: str = "ghost", danger: bool = False, tooltip: str = "",
                 checked_icon: IconPainter | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._icon = icon
        self._checked_icon = checked_icon
        self._icon_size = icon_size
        self._variant = variant
        self._danger = danger
        self.reveal = 1.0  # extra opacity factor, used for hover-revealed buttons
        self.setFixedSize(size, size)
        if tooltip:
            self.setToolTip(tooltip)
            self.setAccessibleName(tooltip)

    def set_reveal(self, value: float) -> None:
        self.reveal = value
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, value < 0.05)
        self.update()

    def paintEvent(self, event) -> None:
        if self.reveal <= 0.001:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setOpacity(self.reveal)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        h, pr = self._h(), self.press.value
        radius = r.height() / 2
        on = self.isCheckable() and self.isChecked()
        if self._variant == "bead":
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(14, 14, 20, 175))
            p.drawRoundedRect(r, radius, radius)
        if self._variant in ("ghost", "bead"):
            lit = 0.55 if self.isEnabled() else 0.3
            p.setPen(theme.rim_pen(r, theme.alpha(theme.WHITE, (0.30 + 0.12 * h) * lit * 1.6),
                                   theme.alpha(theme.WHITE, 0.05)))
            p.setBrush(theme.alpha(theme.WHITE, 0.05 + 0.05 * h - 0.025 * pr + (0.08 if on else 0.0)))
            p.drawRoundedRect(r, radius, radius)
        elif h > 0.001 or pr > 0.001:
            tint = theme.ROSE if self._danger else theme.WHITE
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.alpha(tint, (0.10 if self._danger else 0.07) * h + 0.04 * pr))
            p.drawRoundedRect(r, radius, radius)

        if not self.isEnabled():
            color = theme.alpha(theme.FAINT, 0.7)
        elif on:
            color = theme.TEXT
        elif self._danger:
            color = theme.mix(theme.MUTED, theme.ROSE_TEXT, h)
        else:
            color = theme.mix(theme.MUTED, theme.TEXT, h)
        s = self._icon_size
        icon_rect = QRectF(r.center().x() - s / 2, r.center().y() - s / 2, s, s)
        (self._checked_icon if on and self._checked_icon else self._icon)(p, icon_rect, color)
        self._focus_ring(p, r, radius)


class PrimaryButton(_Button):
    """The big pill: Iniciar / Pausar / Retomar, morphing icon and crossfading label."""

    START, PAUSE, RESUME = "start", "pause", "resume"
    LABELS = {START: "Iniciar", PAUSE: "Pausar", RESUME: "Retomar"}

    def __init__(self, accent: Accent, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._accent = accent
        self._mode = self.START
        self._label = self.LABELS[self.START]
        self._prev_label = ""
        self._morph = Tween(self, 0.0, 300, QEasingCurve.Type.OutBack)
        self._tone = Tween(self, 0.0, 260)
        self._swap = Tween(self, 1.0, 260, QEasingCurve.Type.InOutCubic)
        self.setFixedHeight(52)
        self.setMinimumWidth(120)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAccessibleName(self._label)

    @property
    def mode(self) -> str:
        return self._mode

    def set_accent(self, accent: Accent) -> None:
        self._accent = accent
        self.update()

    def set_mode(self, mode: str, animate: bool = True) -> None:
        if mode == self._mode:
            return
        label = self.LABELS[mode]
        if label != self._label:
            self._prev_label, self._label = self._label, label
            if animate:
                self._swap.set(0.0)
                self._swap.to(1.0)
            else:
                self._swap.set(1.0)
        self._mode = mode
        target = 1.0 if mode == self.PAUSE else 0.0
        if animate:
            self._morph.to(target)
            self._tone.to(target)
        else:
            self._morph.set(target)
            self._tone.set(target)
        self.setAccessibleName(label)

    def sizeHint(self) -> QSize:
        return QSize(200, 52)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        radius = r.height() / 2
        t = self._tone.value
        h, pr = self._h(), self.press.value
        a = self._accent

        if t < 0.999:  # "go" style: accent gradient
            p.setOpacity(1.0 - t)
            grad = QLinearGradient(r.topLeft(), r.topRight())
            grad.setColorAt(0.0, a.start)
            grad.setColorAt(1.0, a.end)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(grad)
            p.drawRoundedRect(r, radius, radius)
            sheen = QLinearGradient(r.topLeft(), r.bottomLeft())
            sheen.setColorAt(0.0, theme.alpha(theme.WHITE, 0.22 + 0.10 * h))
            sheen.setColorAt(0.55, theme.alpha(theme.WHITE, 0.0))
            p.setBrush(sheen)
            p.drawRoundedRect(r, radius, radius)
            if h > 0.001 or pr > 0.001:
                p.setBrush(theme.alpha(theme.WHITE, 0.10 * h) if pr < 0.01
                           else theme.alpha(QColor("#000000"), 0.14 * pr))
                p.drawRoundedRect(r, radius, radius)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(theme.rim_pen(r.adjusted(0.5, 0.5, -0.5, -0.5), theme.alpha(theme.WHITE, 0.6),
                                   theme.alpha(theme.WHITE, 0.08)))
            p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), radius - 0.5, radius - 0.5)
        if t > 0.001:  # "pause" style: frosted glass; the icon carries the accent
            p.setOpacity(t)
            p.setPen(theme.rim_pen(r, theme.alpha(theme.WHITE, 0.34 + 0.12 * h),
                                   theme.alpha(theme.WHITE, 0.06)))
            p.setBrush(theme.alpha(theme.WHITE, 0.07 + 0.05 * h))
            p.drawRoundedRect(r, radius, radius)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.glass_sheen(r, 0.9))
            p.drawRoundedRect(r, radius, radius)
            if pr > 0.001:
                p.setBrush(theme.alpha(QColor("#000000"), 0.16 * pr))
                p.drawRoundedRect(r, radius, radius)
        p.setOpacity(1.0)

        fg = theme.mix(theme.ON_ACCENT, theme.TEXT, t)
        icon_color = theme.mix(theme.ON_ACCENT, theme.mix(a.start, theme.WHITE, 0.15), t)
        f = theme.font(15, 600)
        fm = QFontMetricsF(f)
        s = self._swap.value
        w_now = fm.horizontalAdvance(self._label)
        w_prev = fm.horizontalAdvance(self._prev_label) if self._prev_label else w_now
        text_w = w_prev + (w_now - w_prev) * s
        icon_px, gap = 16.0, 9.0
        x0 = r.center().x() - (icon_px + gap + text_w) / 2
        icons.play_pause(p, QRectF(x0, r.center().y() - icon_px / 2, icon_px, icon_px),
                         icon_color, self._morph.value)

        p.setFont(f)
        p.setPen(fg)
        tx = x0 + icon_px + gap
        if self._prev_label and s < 0.5:
            p.setOpacity(1.0 - s * 2)
            p.drawText(QRectF(tx, r.y() - 7 * s, w_prev + 4, r.height()),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._prev_label)
        if s >= 0.5 or not self._prev_label:
            p.setOpacity(1.0 if not self._prev_label else (s - 0.5) * 2)
            p.drawText(QRectF(tx, r.y() + 7 * (1 - s), w_now + 4, r.height()),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._label)
        p.setOpacity(1.0)
        self._focus_ring(p, r, radius)


class PillButton(_Button):
    """Text button used in dialogs: `ghost`, `light` or `danger`."""

    def __init__(self, text: str, variant: str = "ghost", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setText(text)
        self._variant = variant
        self.setFixedHeight(40)
        fm = QFontMetricsF(theme.font(14, 600))
        self.setMinimumWidth(int(fm.horizontalAdvance(text) + 44))

    def set_variant(self, variant: str) -> None:
        self._variant = variant
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(self.minimumWidth(), 40)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        radius = 12.0
        h, pr = self._h(), self.press.value
        if self._variant == "danger":
            p.setPen(theme.rim_pen(r, theme.alpha(theme.WHITE, 0.45), theme.alpha(theme.WHITE, 0.05)))
            p.setBrush(theme.mix(QColor("#F43F5E"), QColor("#FB7185"), 0.35 * h - 0.2 * pr))
            fg = theme.WHITE
        elif self._variant == "light":
            p.setPen(theme.rim_pen(r, theme.alpha(theme.WHITE, 0.9), theme.alpha(theme.WHITE, 0.3)))
            p.setBrush(theme.mix(QColor("#E9E9EF"), theme.WHITE, h - 0.3 * pr))
            fg = theme.ON_ACCENT
        else:
            p.setPen(theme.rim_pen(r, theme.alpha(theme.WHITE, 0.30 + 0.10 * h),
                                   theme.alpha(theme.WHITE, 0.06)))
            p.setBrush(theme.alpha(theme.WHITE, 0.06 + 0.05 * h))
            fg = theme.mix(theme.MUTED, theme.TEXT, 0.65 + 0.35 * h)
        p.drawRoundedRect(r, radius, radius)
        p.setPen(fg)
        p.setFont(theme.font(14, 600))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, self.text())
        self._focus_ring(p, r, radius)


class PlusButton(_Button):
    """The minimalist "+" that adds a stopwatch."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, hover_ms=260)
        self.setFixedSize(46, 46)
        self.setToolTip("Novo cronômetro  (Ctrl+N)")
        self.setAccessibleName("Novo cronômetro")

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        h, pr = self._h(), self.press.value
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(14, 14, 20, 175))  # dark glass base: legible over any background
        p.drawEllipse(r)
        p.setPen(theme.rim_pen(r, theme.alpha(theme.WHITE, 0.32 + 0.16 * h),
                               theme.alpha(theme.WHITE, 0.05)))
        p.setBrush(theme.alpha(theme.WHITE, 0.05 + 0.06 * h - 0.025 * pr))
        p.drawEllipse(r)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.glass_sheen(r, 0.8))
        p.drawEllipse(r)
        p.save()
        p.translate(r.center())
        p.rotate(90 * h)
        p.scale(1 - 0.08 * pr, 1 - 0.08 * pr)
        icons.plus(p, QRectF(-10, -10, 20, 20), theme.mix(theme.MUTED, theme.TEXT, h), 1.7)
        p.restore()
        self._focus_ring(p, r, r.height() / 2)


class AccentDot(_Button):
    """Small color dot in the card header; clicking it cycles the accent."""

    def __init__(self, accent: Accent, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._accent = accent
        self.setFixedSize(22, 22)
        self.setToolTip("Mudar cor")
        self.setAccessibleName("Mudar cor")

    def set_accent(self, accent: Accent) -> None:
        self._accent = accent
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QRectF(self.rect()).center()
        h = self._h()
        if h > 0.001:
            p.setPen(QPen(theme.alpha(theme.WHITE, 0.28 * h), 1.2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(c, 8.5, 8.5)
        radius = 5.0 + 0.6 * h
        grad = QLinearGradient(c.x() - radius, c.y() - radius, c.x() + radius, c.y() + radius)
        grad.setColorAt(0.0, self._accent.start)
        grad.setColorAt(1.0, self._accent.end)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(grad)
        p.drawEllipse(c, radius, radius)
        self._focus_ring(p, QRectF(self.rect()).adjusted(3, 3, -3, -3), 8)


class NameField(QWidget):
    """Stopwatch name: painted as a label, click (or F2) to edit inline."""

    committed = Signal(str)

    def __init__(self, text: str, accent: Accent, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._text = text
        self._accent = accent
        self._finishing = False
        self._hover = Tween(self, 0.0, 150)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(30)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setToolTip("Clique para renomear")
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)

        self._edit = QLineEdit(self)
        self._edit.setMaxLength(MAX_NAME_LENGTH)
        self._edit.setFrame(False)
        self._edit.setPlaceholderText("Nome do cronômetro")
        self._edit.setFont(theme.font(15, 600))
        self._edit.setTextMargins(0, 0, 0, 0)
        self._edit.hide()
        self._edit.installEventFilter(self)
        self._edit.returnPressed.connect(self._commit)
        self._apply_editor_style()

    @property
    def text(self) -> str:
        return self._text

    @property
    def editing(self) -> bool:
        return self._edit.isVisible()

    def set_accent(self, accent: Accent) -> None:
        self._accent = accent
        self._apply_editor_style()
        self.update()

    def _apply_editor_style(self) -> None:
        a = self._accent.start
        self._edit.setStyleSheet(
            "QLineEdit {"
            " background: transparent; color: #F2F2F5; padding: 0px; margin: 0px;"
            f" border: none; border-bottom: 1.5px solid rgba({a.red()}, {a.green()}, {a.blue()}, 0.85);"
            f" selection-background-color: rgba({a.red()}, {a.green()}, {a.blue()}, 0.45);"
            " selection-color: #FFFFFF; }"
        )

    def begin_edit(self) -> None:
        if self.editing:
            return
        self._edit.setText(self._text)
        self._edit.setGeometry(0, 1, self.width(), self.height() - 2)
        self._edit.show()
        self._edit.setFocus(Qt.FocusReason.MouseFocusReason)
        self._edit.selectAll()
        self.update()

    def _finish(self, commit: bool) -> None:
        if not self.editing or self._finishing:
            return
        self._finishing = True
        try:
            text = " ".join(self._edit.text().split())
            # Drop focus first: hiding a focused widget would hand focus to some button.
            self._edit.clearFocus()
            self._edit.hide()
        finally:
            self._finishing = False
        if commit and text and text != self._text:
            self._text = text
            self.committed.emit(text)
        self.update()

    def _commit(self) -> None:
        self._finish(True)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj is self._edit:
            if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
                self._finish(False)
                return True
            if event.type() == QEvent.Type.FocusOut and not self._finishing:
                self._finish(True)
        return super().eventFilter(obj, event)

    def resizeEvent(self, event) -> None:
        if self.editing:
            self._edit.setGeometry(0, 1, self.width(), self.height() - 2)
        super().resizeEvent(event)

    def enterEvent(self, event) -> None:
        self._hover.to(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover.to(0.0)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.begin_edit()
            event.accept()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_F2, Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.begin_edit()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event) -> None:
        if self.editing:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        f = theme.font(15, 600)
        fm = QFontMetricsF(f)
        h = max(self._hover.value, 1.0 if self.hasFocus() else 0.0)
        pencil_w = 22.0
        avail = max(0.0, self.width() - pencil_w)
        text = fm.elidedText(self._text, Qt.TextElideMode.ElideRight, avail)
        p.setFont(f)
        p.setPen(theme.TEXT)
        rect = QRectF(0, 0, avail + 2, self.height())
        p.drawText(rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
        if h > 0.001:
            x = fm.horizontalAdvance(text) + 8
            p.setOpacity(h)
            icons.pencil(p, QRectF(x, self.height() / 2 - 7, 14, 14), theme.MUTED)
            p.setOpacity(1.0)
