"""Per-stopwatch task list: the header toggle, the task rows and the expanding panel."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFontMetricsF, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QFrame, QLineEdit, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from . import icons, theme
from .model import MAX_TASK_LENGTH, Stopwatch, Task
from .theme import Accent
from .widgets import IconButton, Tween, _Button

ROW_HEIGHT = 34
ROW_GAP = 2
HEADER_HEIGHT = 36
ADD_HEIGHT = 38
TOP_GAP = 14
MAX_VISIBLE_ROWS = 6


def _line_edit_style(accent: Accent) -> str:
    a = accent.start
    return (
        "QLineEdit { background: transparent; color: #F2F2F5; border: none; padding: 0px;"
        f" selection-background-color: rgba({a.red()}, {a.green()}, {a.blue()}, 0.45);"
        " selection-color: #FFFFFF; }"
    )


class TasksButton(_Button):
    """Header toggle for the task list, with a done/total counter."""

    def __init__(self, accent: Accent, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._accent = accent
        self._done = self._total = 0
        self.setCheckable(True)
        self.setFixedHeight(26)
        self.setToolTip("Tarefas")
        self.setAccessibleName("Tarefas")
        self._fit()

    def set_accent(self, accent: Accent) -> None:
        self._accent = accent
        self.update()

    def set_counts(self, done: int, total: int) -> None:
        self._done, self._total = done, total
        self._fit()
        self.update()

    def _label(self) -> str:
        return f"{self._done}/{self._total}" if self._total else ""

    def _fit(self) -> None:
        label = self._label()
        width = 26 if not label else 30 + QFontMetricsF(theme.font(12, 600, tabular=True)).horizontalAdvance(label) + 8
        self.setFixedWidth(int(width))

    def sizeHint(self) -> QSize:
        return QSize(self.width(), 26)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        h, on, a = self._h(), self.isChecked(), self._accent
        if on or h > 0.001:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.alpha(a.start, 0.18) if on else theme.alpha(theme.WHITE, 0.07 * h))
            p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        all_done = self._total > 0 and self._done == self._total
        if on:
            color = theme.mix(a.start, theme.WHITE, 0.3)
        elif all_done:
            color = a.start
        else:
            color = theme.mix(theme.MUTED, theme.TEXT, h)
        icons.checklist(p, QRectF(5, r.center().y() - 8, 16, 16), color)
        label = self._label()
        if label:
            p.setFont(theme.font(12, 600, tabular=True))
            p.setPen(color)
            p.drawText(QRectF(26, 0, r.width() - 26, r.height()), Qt.AlignmentFlag.AlignVCenter, label)
        self._focus_ring(p, r, r.height() / 2)


class TaskRow(QWidget):
    """One task: the circle toggles it done, double-click edits, × removes."""

    toggled = Signal(object)
    removed = Signal(object)
    edited = Signal(object, str)

    def __init__(self, task: Task, accent: Accent, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.task = task
        self._accent = accent
        self._hover = Tween(self, 0.0, 140, on_change=self._on_hover)
        self._check = Tween(self, 1.0 if task.done else 0.0, 280)
        self.setFixedHeight(ROW_HEIGHT)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setMouseTracking(True)
        self.delete_btn = IconButton(icons.close, size=24, icon_size=10, variant="plain",
                                     danger=True, tooltip="Remover tarefa", parent=self)
        self.delete_btn.set_reveal(0.0)
        self.delete_btn.clicked.connect(lambda: self.removed.emit(self))
        self._edit = QLineEdit(self)
        self._edit.setFrame(False)
        self._edit.setMaxLength(MAX_TASK_LENGTH)
        self._edit.setFont(theme.font(13.5, 400))
        self._edit.setStyleSheet(_line_edit_style(accent))
        self._edit.hide()
        self._edit.installEventFilter(self)
        self._edit.returnPressed.connect(lambda: self._finish(True))
        self._finishing = False

    def set_accent(self, accent: Accent) -> None:
        self._accent = accent
        self._edit.setStyleSheet(_line_edit_style(accent))
        self.update()

    def set_done(self, done: bool) -> None:
        self._check.to(1.0 if done else 0.0)

    def _on_hover(self, value: float) -> None:
        self.delete_btn.set_reveal(value)
        self.update()

    def _checkbox_hit(self, x: float) -> bool:
        return x < 32

    def enterEvent(self, event) -> None:
        self._hover.to(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover.to(0.0)
        self.unsetCursor()
        super().leaveEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._checkbox_hit(event.position().x()):
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.unsetCursor()
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._checkbox_hit(event.position().x()):
            self.toggled.emit(self)
        event.accept()  # rows never start a window drag

    def mouseDoubleClickEvent(self, event) -> None:
        if not self._checkbox_hit(event.position().x()):
            self._begin_edit()
        event.accept()

    def resizeEvent(self, event) -> None:
        self.delete_btn.move(self.width() - self.delete_btn.width() - 2,
                             (self.height() - self.delete_btn.height()) // 2)
        self._edit.setGeometry(32, 4, self.width() - 32 - 30, self.height() - 8)
        super().resizeEvent(event)

    def _begin_edit(self) -> None:
        self._edit.setText(self.task.text)
        self._edit.show()
        self._edit.setFocus(Qt.FocusReason.MouseFocusReason)
        self._edit.selectAll()
        self.update()

    def _finish(self, commit: bool) -> None:
        if not self._edit.isVisible() or self._finishing:
            return
        self._finishing = True
        try:
            text = " ".join(self._edit.text().split())
            self._edit.clearFocus()
            self._edit.hide()
        finally:
            self._finishing = False
        if commit and text and text != self.task.text:
            self.edited.emit(self, text)
        self.update()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj is self._edit:
            if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
                self._finish(False)
                return True
            if event.type() == QEvent.Type.FocusOut and not self._finishing:
                self._finish(True)
        return super().eventFilter(obj, event)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        h, t, a = self._hover.value, self._check.value, self._accent
        if h > 0.001:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.alpha(theme.WHITE, 0.045 * h))
            p.drawRoundedRect(r, 9, 9)

        # The checkbox: an outlined circle that fills with the accent and draws a check.
        c = QPointF(15, r.center().y())
        radius = 8.5
        if t < 0.999:
            p.setPen(QPen(theme.alpha(theme.WHITE, 0.30 + 0.15 * h), 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(c, radius, radius)
        if t > 0.001:
            fill = QLinearGradient(c.x() - radius, c.y() - radius, c.x() + radius, c.y() + radius)
            fill.setColorAt(0.0, a.start)
            fill.setColorAt(1.0, a.end)
            p.setPen(Qt.PenStyle.NoPen)
            p.setOpacity(min(1.0, t * 1.6))
            p.setBrush(fill)
            p.drawEllipse(c, radius * (0.6 + 0.4 * min(1.0, t * 1.4)), radius * (0.6 + 0.4 * min(1.0, t * 1.4)))
            p.setOpacity(1.0)
            icons.check(p, QRectF(c.x() - 7, c.y() - 7, 14, 14), theme.ON_ACCENT,
                        max(0.0, (t - 0.25) / 0.75))

        if self._edit.isVisible():
            return
        f = theme.font(13.5, 400)
        fm = QFontMetricsF(f)
        avail = r.width() - 32 - 30
        text = fm.elidedText(self.task.text, Qt.TextElideMode.ElideRight, avail)
        p.setFont(f)
        p.setPen(theme.mix(theme.TEXT, theme.alpha(theme.MUTED, 0.85), t))
        text_rect = QRectF(32, 0, avail, r.height())
        p.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
        if t > 0.001:  # the strike-through sweeps across as the task gets done
            y = r.center().y() + 1
            p.setPen(QPen(theme.alpha(theme.MUTED, 0.9), 1.3))
            p.drawLine(QPointF(32, y), QPointF(32 + fm.horizontalAdvance(text) * t, y))


class _PanelHeader(QWidget):
    """Divider, "TAREFAS" title, done/total and a thin progress bar."""

    def __init__(self, accent: Accent, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._accent = accent
        self._done = self._total = 0
        self._progress = Tween(self, 0.0, 320)
        self.setFixedHeight(HEADER_HEIGHT)

    def set_accent(self, accent: Accent) -> None:
        self._accent = accent
        self.update()

    def set_counts(self, done: int, total: int, animate: bool = True) -> None:
        self._done, self._total = done, total
        target = done / total if total else 0.0
        if animate:
            self._progress.to(target)
        else:
            self._progress.set(target)
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        divider = QLinearGradient(0, 0, w, 0)
        divider.setColorAt(0.0, theme.alpha(theme.WHITE, 0.0))
        divider.setColorAt(0.5, theme.alpha(theme.WHITE, 0.13))
        divider.setColorAt(1.0, theme.alpha(theme.WHITE, 0.0))
        p.fillRect(QRectF(0, 0, w, 1), divider)

        f = theme.font(10.5, 650, spacing=1.6, smooth=True)
        p.setFont(f)
        p.setPen(theme.MUTED)
        p.drawText(QPointF(2, 21), "TAREFAS")
        if self._total:
            count = f"{self._done} de {self._total}"
            cf = theme.font(12, 500, tabular=True)
            p.setFont(cf)
            p.setPen(self._accent.start if self._done == self._total else theme.MUTED)
            p.drawText(QPointF(w - 2 - QFontMetricsF(cf).horizontalAdvance(count), 21), count)

        bar = QRectF(2, 29, w - 4, 3)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.alpha(theme.WHITE, 0.07))
        p.drawRoundedRect(bar, 1.5, 1.5)
        if self._progress.value > 0.001:
            fill = QLinearGradient(bar.topLeft(), bar.topRight())
            fill.setColorAt(0.0, self._accent.start)
            fill.setColorAt(1.0, self._accent.end)
            p.setBrush(fill)
            p.drawRoundedRect(QRectF(bar.x(), bar.y(), bar.width() * self._progress.value, bar.height()),
                              1.5, 1.5)


class _AddRow(QWidget):
    """"+ Adicionar tarefa" input; Enter adds and keeps the focus for the next one."""

    submitted = Signal(str)

    def __init__(self, accent: Accent, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._accent = accent
        self._hover = Tween(self, 0.0, 140)
        self.setFixedHeight(ADD_HEIGHT)
        self.edit = QLineEdit(self)
        self.edit.setFrame(False)
        self.edit.setMaxLength(MAX_TASK_LENGTH)
        self.edit.setPlaceholderText("Adicionar tarefa")
        self.edit.setFont(theme.font(13.5, 400))
        self.edit.setStyleSheet(_line_edit_style(accent))
        self.edit.returnPressed.connect(self._submit)
        self.edit.installEventFilter(self)

    def set_accent(self, accent: Accent) -> None:
        self._accent = accent
        self.edit.setStyleSheet(_line_edit_style(accent))
        self.update()

    def _submit(self) -> None:
        text = " ".join(self.edit.text().split())
        if text:
            self.submitted.emit(text)
        self.edit.clear()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj is self.edit:
            if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
                self.edit.clear()
                self.edit.clearFocus()
                return True
            if event.type() in (QEvent.Type.FocusIn, QEvent.Type.FocusOut):
                self.update()
        return super().eventFilter(obj, event)

    def enterEvent(self, event) -> None:
        self._hover.to(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover.to(0.0)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        self.edit.setFocus(Qt.FocusReason.MouseFocusReason)
        event.accept()

    def resizeEvent(self, event) -> None:
        self.edit.setGeometry(32, 6, self.width() - 40, self.height() - 12)
        super().resizeEvent(event)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 2.5, -0.5, -2.5)
        focused = self.edit.hasFocus()
        h = max(self._hover.value, 1.0 if focused else 0.0)
        p.setPen(QPen(theme.alpha(self._accent.start, 0.55), 1) if focused
                 else QPen(theme.alpha(theme.WHITE, 0.06 + 0.06 * h), 1))
        p.setBrush(theme.alpha(theme.WHITE, 0.03 + 0.03 * h))
        p.drawRoundedRect(r, 10, 10)
        color = self._accent.start if focused else theme.mix(theme.MUTED, theme.TEXT, 0.4 * h)
        icons.plus(p, QRectF(8, r.center().y() - 8, 16, 16), color, 2.0)


class TaskPanel(QWidget):
    """Expanding task list under the controls. Its height is driven by the card, which
    animates it; the content keeps its natural size and is revealed from the top."""

    changed = Signal()  # tasks were added, removed, edited or toggled
    height_wanted = Signal()  # the natural height changed

    def __init__(self, sw: Stopwatch, accent: Accent, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.sw = sw
        self._accent = accent
        self.rows: list[TaskRow] = []
        self.content = QWidget(self)
        self.header = _PanelHeader(accent)
        self.scroll = QScrollArea()
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea { background: transparent; }")
        self.scroll.viewport().setAutoFillBackground(False)
        self.list = QWidget()
        self.list_layout = QVBoxLayout(self.list)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(ROW_GAP)
        self.list_layout.addStretch(1)
        self.scroll.setWidget(self.list)
        self.list.setAutoFillBackground(False)
        self._follow_new = False
        self.scroll.verticalScrollBar().rangeChanged.connect(self._follow)
        self.add_row = _AddRow(accent)
        self.add_row.submitted.connect(self._add)

        layout = QVBoxLayout(self.content)
        layout.setContentsMargins(0, TOP_GAP, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.header)
        layout.addWidget(self.scroll)
        layout.addSpacing(4)
        layout.addWidget(self.add_row)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        for task in sw.tasks:
            self._insert_row(task)
        self._sync(animate=False)

    def natural_height(self) -> int:
        rows = min(len(self.sw.tasks), MAX_VISIBLE_ROWS)
        list_height = rows * ROW_HEIGHT + max(0, rows - 1) * ROW_GAP
        return TOP_GAP + HEADER_HEIGHT + list_height + 4 + ADD_HEIGHT

    def counts(self) -> tuple[int, int]:
        return sum(1 for task in self.sw.tasks if task.done), len(self.sw.tasks)

    def set_accent(self, accent: Accent) -> None:
        self._accent = accent
        self.header.set_accent(accent)
        self.add_row.set_accent(accent)
        for row in self.rows:
            row.set_accent(accent)

    def focus_input(self) -> None:
        self.add_row.edit.setFocus(Qt.FocusReason.OtherFocusReason)

    def _insert_row(self, task: Task) -> TaskRow:
        row = TaskRow(task, self._accent)
        row.toggled.connect(self._toggle)
        row.removed.connect(self._remove)
        row.edited.connect(self._edit)
        self.list_layout.insertWidget(self.list_layout.count() - 1, row)
        self.rows.append(row)
        return row

    def _add(self, text: str) -> None:
        task = Task(text)
        self.sw.tasks.append(task)
        self._insert_row(task)
        # Keep the newest task in view: scroll once the list has grown (see _follow).
        self._follow_new = len(self.sw.tasks) > MAX_VISIBLE_ROWS
        self._sync()
        self.changed.emit()
        self.height_wanted.emit()

    def _follow(self, _minimum: int, maximum: int) -> None:
        if self._follow_new:
            self._follow_new = False
            self.scroll.verticalScrollBar().setValue(maximum)

    def _toggle(self, row: TaskRow) -> None:
        row.task.done = not row.task.done
        row.set_done(row.task.done)
        self._sync()
        self.changed.emit()

    def _remove(self, row: TaskRow) -> None:
        if row.task in self.sw.tasks:
            self.sw.tasks.remove(row.task)
        self.rows.remove(row)
        self.list_layout.removeWidget(row)
        row.deleteLater()
        self._sync()
        self.changed.emit()
        self.height_wanted.emit()

    def _edit(self, row: TaskRow, text: str) -> None:
        row.task.text = text
        row.update()
        self.changed.emit()

    def _sync(self, animate: bool = True) -> None:
        rows = min(len(self.sw.tasks), MAX_VISIBLE_ROWS)
        self.scroll.setFixedHeight(rows * ROW_HEIGHT + max(0, rows - 1) * ROW_GAP)
        self.header.set_counts(*self.counts(), animate=animate)
        self._place_content()

    def _place_content(self) -> None:
        self.content.setGeometry(0, 0, self.width(), self.natural_height())

    def resizeEvent(self, event) -> None:
        self._place_content()
        super().resizeEvent(event)
