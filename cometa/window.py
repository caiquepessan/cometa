"""Floating window: frameless and transparent, showing only the glass cards and the "+".

There is no title bar: drag any card (or the space around it) to move the window.
Close / minimize / always-on-top appear next to the "+" on hover, and in the
right-click menu.
"""
from __future__ import annotations

import html
import sys
from functools import lru_cache
from typing import Callable

from PySide6.QtCore import (QAbstractAnimation, QByteArray, QEasingCurve, QEvent, QPoint,
                            QPropertyAnimation, QRect, QRectF, Qt, QTimer, QVariantAnimation)
from PySide6.QtGui import (QColor, QGuiApplication, QImage, QKeySequence, QPainter, QPixmap,
                           QShortcut)
from PySide6.QtWidgets import (QFrame, QGraphicsOpacityEffect, QHBoxLayout, QMainWindow, QMenu,
                               QScrollArea, QVBoxLayout, QWidget)

from . import icons, theme
from .appicon import app_icon
from .card import CARD_HEIGHT, CARD_WIDTH, RADIUS, StopwatchCard
from .glass import WallpaperGlass, _blur_image
from .model import PAUSED, RUNNING, AppState, Stopwatch, Store, format_hms
from .overlay import ConfirmOverlay
from .system import allow_minimize
from .widgets import IconButton, PlusButton, Tween

MARGIN = 30  # transparent border that holds the soft shadows
GAP = 18  # between cards, and between the last card and the rail
RAIL = 46  # column with the "+" (and the window controls, on hover)
FRAME_MS = 40  # 25 fps while something runs (half that when the window is in the background)
SHADOW_BLUR = 18


def content_width(cards: int) -> int:
    return 2 * MARGIN + cards * (CARD_WIDTH + GAP) + RAIL


@lru_cache(maxsize=8)
def _shadow(width: int, height: int, radius: float, strength: int) -> QPixmap:
    """Soft drop shadow for a rounded shape, padded by 2 x blur on every side."""
    pad = 2 * SHADOW_BLUR
    img = QImage(width + 2 * pad, height + 2 * pad, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, strength))
    p.drawRoundedRect(QRectF(pad, pad, width, height), radius, radius)
    p.end()
    return QPixmap.fromImage(_blur_image(img, SHADOW_BLUR, QColor(0, 0, 0, 0)))


def _draw_shadow(p: QPainter, rect: QRect, radius: float, strength: int) -> None:
    """Soft shadow under `rect`. Big shapes are 9-sliced from one small cached shadow,
    so any card height (the task panel animates it) costs no new blur."""
    pad = 2 * SHADOW_BLUR
    target = QRect(rect.x() - pad, rect.y() - pad + 8, rect.width() + 2 * pad, rect.height() + 2 * pad)
    c = pad + int(radius) + SHADOW_BLUR  # corner slice: blur + rounded corner + falloff
    if target.width() <= 2 * c or target.height() <= 2 * c:
        p.drawPixmap(target.topLeft(), _shadow(rect.width(), rect.height(), radius, strength))
        return
    core = 2 * (c - pad) + 1
    tile = _shadow(core, core, radius, strength)  # (2c + 1) square
    t = tile.width()
    columns = ((0, c, target.x(), c), (c, t - 2 * c, target.x() + c, target.width() - 2 * c),
               (t - c, c, target.x() + target.width() - c, c))
    rows = ((0, c, target.y(), c), (c, t - 2 * c, target.y() + c, target.height() - 2 * c),
            (t - c, c, target.y() + target.height() - c, c))
    for sx, sw, dx, dw in columns:
        for sy, sh, dy, dh in rows:
            p.drawPixmap(QRect(dx, dy, dw, dh), tile, QRect(sx, sy, sw, sh))


class Surface(QWidget):
    """Transparent canvas under the floating cards: soft drop shadows, plus an invisible
    (1/255) fill between the cards so the whole widget stays hoverable and draggable."""

    def __init__(self, owner: MainWindow) -> None:
        super().__init__()
        self._owner = owner

    def paintEvent(self, event) -> None:
        dirty = event.rect()
        p = QPainter(self)
        inner = self.rect().adjusted(MARGIN - 8, MARGIN - 8, 8 - MARGIN, 8 - MARGIN)
        p.fillRect(inner.intersected(dirty), QColor(0, 0, 0, 1))
        for widget, radius, strength in self._owner.floating_items():
            rect = QRect(widget.mapTo(self, QPoint(0, 0)), widget.size())
            if rect.contains(dirty):
                continue  # the repaint is inside the widget itself, the shadow is hidden
            effect = widget.graphicsEffect()
            opacity = effect.opacity() if isinstance(effect, QGraphicsOpacityEffect) else 1.0
            if opacity <= 0.01:
                continue
            p.setOpacity(opacity)
            _draw_shadow(p, rect, radius, strength)
        p.setOpacity(1.0)

    def mousePressEvent(self, event) -> None:
        handle = self.window().windowHandle()
        if event.button() == Qt.MouseButton.LeftButton and handle is not None:
            handle.startSystemMove()
            event.accept()
            return
        super().mousePressEvent(event)


class Rail(QWidget):
    """Column beside the cards: window controls at the top (shown on hover), "+" centered."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(RAIL)
        self.close_btn = IconButton(icons.close, size=30, icon_size=12, variant="bead",
                                    danger=True, tooltip="Fechar", parent=self)
        self.min_btn = IconButton(icons.minus, size=30, icon_size=12, variant="bead",
                                  tooltip="Minimizar", parent=self)
        self.pin_btn = IconButton(icons.pin, size=30, icon_size=15, variant="bead",
                                  tooltip="Sempre no topo", checked_icon=icons.pin_filled,
                                  parent=self)
        self.pin_btn.setCheckable(True)
        self.plus = PlusButton(self)
        self.controls = (self.close_btn, self.min_btn, self.pin_btn)

    def resizeEvent(self, event) -> None:
        x = (self.width() - 30) // 2
        for i, button in enumerate(self.controls):
            button.move(x, 6 + i * 38)
        self.plus.move((self.width() - self.plus.width()) // 2,
                       (self.height() - self.plus.height()) // 2)
        super().resizeEvent(event)


class HScrollArea(QScrollArea):
    """Transparent horizontal scroller (only needed when the cards outgrow the screen)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setWidgetResizable(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setStyleSheet("QScrollArea { background: transparent; }")
        self.viewport().setAutoFillBackground(False)
        self._anim = QPropertyAnimation(self.horizontalScrollBar(), b"value", self)
        self._anim.setDuration(280)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def scroll_to(self, value: int) -> None:
        bar = self.horizontalScrollBar()
        value = max(bar.minimum(), min(bar.maximum(), int(value)))
        self._anim.stop()
        self._anim.setStartValue(bar.value())
        self._anim.setEndValue(value)
        self._anim.start()

    def wheelEvent(self, event) -> None:
        bar = self.horizontalScrollBar()
        if bar.maximum() <= 0:
            event.ignore()
            return
        delta = event.angleDelta()
        step = delta.y() if abs(delta.y()) >= abs(delta.x()) else delta.x()
        if not step:
            pixels = event.pixelDelta()
            step = pixels.y() or pixels.x()
        running = self._anim.state() == QAbstractAnimation.State.Running
        base = self._anim.endValue() if running else bar.value()
        self.scroll_to(int(base) - step)
        event.accept()


class MainWindow(QMainWindow):
    def __init__(self, store: Store, state: AppState) -> None:
        super().__init__()
        self.store = store
        self.state = state
        if not state.stopwatches:
            state.stopwatches.append(Stopwatch(name="Cronômetro 1", accent=0))
        self.cards: list[StopwatchCard] = []
        self._overlays: dict[StopwatchCard, ConfirmOverlay] = {}
        self._animations: list[QAbstractAnimation] = []
        self._title = ""
        self._native_ready = False
        self.glass = WallpaperGlass()

        flags = Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint
        if state.on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("Cometa")
        self.setWindowIcon(app_icon())

        self.surface = Surface(self)
        self.setCentralWidget(self.surface)
        self.scroll = HScrollArea(self.surface)
        root = QVBoxLayout(self.surface)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.scroll)

        self.row = QWidget()
        self.row_layout = QHBoxLayout(self.row)
        self.row_layout.setContentsMargins(MARGIN, MARGIN, MARGIN, MARGIN)
        self.row_layout.setSpacing(0)
        # card slots get inserted at index len(cards), before the rail
        self.rail = Rail()
        self.rail.setFixedHeight(CARD_HEIGHT)
        self.row_layout.addWidget(self.rail, 0, Qt.AlignmentFlag.AlignTop)
        self.row_layout.addStretch(1)
        self.scroll.setWidget(self.row)
        self.row.setAutoFillBackground(False)  # setWidget() turns it on

        self.plus = self.rail.plus
        self.plus.clicked.connect(self.add_stopwatch)
        self.rail.close_btn.clicked.connect(self.close)
        self.rail.min_btn.clicked.connect(self.showMinimized)
        self.rail.pin_btn.setChecked(state.on_top)
        self.rail.pin_btn.toggled.connect(self.set_on_top)
        self._chrome = Tween(self, 0.0, 180, on_change=self._on_chrome)
        self._chrome_hide = QTimer(self)
        self._chrome_hide.setSingleShot(True)
        self._chrome_hide.setInterval(700)
        self._chrome_hide.timeout.connect(lambda: self._chrome.to(0.0))
        self._on_chrome(0.0)

        for sw in state.stopwatches:
            self._insert_slot(self._make_card(sw))
        self._sync_removable()

        self.ticker = QTimer(self)
        self.ticker.setTimerType(Qt.TimerType.PreciseTimer)
        self.ticker.timeout.connect(self._tick)
        for keys in (QKeySequence("Ctrl+N"), QKeySequence("Ctrl+T")):
            QShortcut(keys, self).activated.connect(self.add_stopwatch)
        wallpaper_watch = QTimer(self)
        wallpaper_watch.timeout.connect(self._refresh_wallpaper)
        wallpaper_watch.start(5000)

        self.setMinimumWidth(content_width(1))
        self.setFixedHeight(self._content_height())
        self._place()
        self._refresh_ticker()
        self._update_title()

    # ----- floating chrome ---------------------------------------------------------------

    def floating_items(self) -> list[tuple[QWidget, float, int]]:
        """Widgets that cast a shadow: (widget, corner radius, shadow strength)."""
        items: list[tuple[QWidget, float, int]] = [(card, RADIUS, 150) for card in self.cards]
        items.append((self.plus, self.plus.width() / 2, 120))
        return items

    def _on_chrome(self, value: float) -> None:
        for button in self.rail.controls:
            button.set_reveal(value)

    def enterEvent(self, event) -> None:
        self._chrome_hide.stop()
        self._chrome.to(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._chrome_hide.start()
        super().leaveEvent(event)

    def set_on_top(self, on: bool) -> None:
        self.state.on_top = on
        if self.rail.pin_btn.isChecked() != on:
            self.rail.pin_btn.setChecked(on)
        handle = self.windowHandle()
        if handle is not None:
            handle.setFlag(Qt.WindowType.WindowStaysOnTopHint, on)  # live, without re-creating
        allow_minimize(self)
        # On Windows the flag change can reset the translucent (layered) window surface, so
        # only the parts that keep repainting (the dial) would come back: repaint everything.
        self.update()
        QTimer.singleShot(60, self.update)
        self._persist()

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)
        menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        menu.setWindowFlags(menu.windowFlags() | Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.NoDropShadowWindowHint)
        new = menu.addAction("Novo cronômetro")
        new.setShortcut(QKeySequence("Ctrl+N"))
        new.triggered.connect(self.add_stopwatch)
        top = menu.addAction("Sempre no topo")
        top.setCheckable(True)
        top.setChecked(self.state.on_top)
        top.toggled.connect(self.set_on_top)
        menu.addSeparator()
        menu.addAction("Minimizar").triggered.connect(self.showMinimized)
        menu.addAction("Fechar").triggered.connect(self.close)
        menu.exec(event.globalPos())

    # ----- cards -------------------------------------------------------------------------

    def _make_card(self, sw: Stopwatch) -> StopwatchCard:
        card = StopwatchCard(sw, self.glass)
        card.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        card.toggle_requested.connect(self._on_toggle)
        card.stop_requested.connect(self._on_stop)
        card.reset_requested.connect(self._on_reset)
        card.remove_requested.connect(self._on_remove)
        card.rename_requested.connect(self._on_rename)
        card.tasks_changed.connect(lambda _card: self._persist())
        card.height_changed.connect(self._fit_height)
        card.recolor_requested.connect(self._on_recolor)
        return card

    def _insert_slot(self, card: StopwatchCard, width: int | None = None) -> QWidget:
        slot = QWidget()
        layout = QHBoxLayout(slot)
        layout.setContentsMargins(0, 0, GAP, 0)
        layout.setSpacing(0)
        layout.addWidget(card, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        slot.setFixedWidth(CARD_WIDTH + GAP if width is None else width)
        self.row_layout.insertWidget(len(self.cards), slot, 0, Qt.AlignmentFlag.AlignTop)
        self.cards.append(card)
        return slot

    def _sync_removable(self) -> None:
        for card in self.cards:
            card.set_removable(len(self.cards) > 1)

    def _next_name(self) -> str:
        names = {sw.name for sw in self.state.stopwatches}
        k = len(self.state.stopwatches) + 1
        while f"Cronômetro {k}" in names:
            k += 1
        return f"Cronômetro {k}"

    def _next_accent(self) -> int:
        count = len(theme.ACCENTS)
        used = [sw.accent % count for sw in self.state.stopwatches]
        start = (used[-1] + 1) % count if used else 0
        return min(range(count), key=lambda i: (used.count(i), (i - start) % count))

    def _overlay(self, card: StopwatchCard) -> ConfirmOverlay:
        if card not in self._overlays:
            self._overlays[card] = ConfirmOverlay(card, RADIUS)
        return self._overlays[card]

    def _dialog_open(self) -> bool:
        return any(o.isVisible() for o in self._overlays.values())

    def add_stopwatch(self) -> None:
        if self._dialog_open():
            return
        self._settle()
        sw = Stopwatch(name=self._next_name(), accent=self._next_accent())
        self.state.stopwatches.append(sw)
        self._persist()
        card = self._make_card(sw)
        effect = QGraphicsOpacityEffect(card)
        effect.setOpacity(0.0)
        card.setGraphicsEffect(effect)
        slot = self._insert_slot(card, width=0)
        self._sync_removable()
        n = len(self.cards)
        self._animate_slot(slot, 0, CARD_WIDTH + GAP, self._resize_plan(content_width(n)),
                           lambda: self._reveal(card))

    def _reveal(self, card: StopwatchCard) -> None:
        effect = card.graphicsEffect()
        if isinstance(effect, QGraphicsOpacityEffect):
            fade = QPropertyAnimation(effect, b"opacity", self)
            fade.setDuration(260)
            fade.setStartValue(0.0)
            fade.setEndValue(1.0)
            fade.setEasingCurve(QEasingCurve.Type.OutCubic)
            fade.valueChanged.connect(lambda _: self.surface.update())
            fade.finished.connect(lambda: card.setGraphicsEffect(None))
            self._run(fade)
        bar = self.scroll.horizontalScrollBar()
        QTimer.singleShot(0, lambda: self.scroll.scroll_to(bar.maximum()))

    def _remove(self, card: StopwatchCard) -> None:
        if card not in self.cards:
            return
        self._settle()
        self.cards.remove(card)
        self._overlays.pop(card, None)
        self.state.stopwatches.remove(card.sw)
        self._persist()
        self._sync_removable()
        self._refresh_ticker()
        self._update_title()
        slot = card.parentWidget()
        slot.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        effect = QGraphicsOpacityEffect(card)
        card.setGraphicsEffect(effect)
        fade = QPropertyAnimation(effect, b"opacity", self)
        fade.setDuration(170)
        fade.setStartValue(1.0)
        fade.setEndValue(0.0)
        fade.setEasingCurve(QEasingCurve.Type.InCubic)

        def collapse() -> None:
            def drop() -> None:
                self.row_layout.removeWidget(slot)
                slot.deleteLater()
                self._fit_height()  # the removed card may have been the tallest
                self.surface.update()

            self._animate_slot(slot, slot.width(), 0,
                               self._resize_plan(content_width(len(self.cards))), drop)

        fade.finished.connect(collapse)
        self._run(fade)

    # ----- layout animation ----------------------------------------------------------------

    def _run(self, anim: QAbstractAnimation) -> None:
        self._animations.append(anim)
        anim.finished.connect(lambda: self._animations.remove(anim) if anim in self._animations else None)
        anim.start()

    def _settle(self) -> None:
        """Jump any add/remove animation to its end state (they chain, hence the loop)."""
        while self._animations:
            anim = self._animations[0]
            if anim.state() == QAbstractAnimation.State.Running:
                anim.setCurrentTime(anim.totalDuration())
            if self._animations and self._animations[0] is anim:
                self._animations.pop(0)

    def _resize_plan(self, needed: int) -> tuple[QRect, QRect] | None:
        """Window geometry to animate between so it keeps hugging its cards."""
        if not self.isVisible():
            return None
        geo = self.geometry()
        screen = (self.screen() or QGuiApplication.primaryScreen()).availableGeometry()
        width = min(max(needed, self.minimumWidth()), screen.width())
        x = geo.x()
        if x + width > screen.right() + 1:
            x = max(screen.left(), screen.right() + 1 - width)
        target = QRect(x, geo.y(), width, geo.height())
        return (geo, target) if target != geo else None

    def _animate_slot(self, slot: QWidget, start: int, end: int,
                      plan: tuple[QRect, QRect] | None, on_done: Callable[[], None]) -> None:
        anim = QVariantAnimation(self)
        anim.setDuration(320)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)

        def step(t: float) -> None:
            slot.setFixedWidth(round(start + (end - start) * t))
            if plan is not None:
                a, b = plan
                self.setGeometry(round(a.x() + (b.x() - a.x()) * t), a.y(),
                                 round(a.width() + (b.width() - a.width()) * t), a.height())
            self.surface.update()

        anim.valueChanged.connect(step)
        anim.finished.connect(lambda: (step(1.0), on_done()))
        self._run(anim)

    # ----- actions -----------------------------------------------------------------------

    def _on_toggle(self, card: StopwatchCard) -> None:
        """Start, pause or resume: instant, no confirmation."""
        if card.sw.running:
            card.sw.pause()
        else:
            card.sw.start()
        self._changed(card)

    def _on_stop(self, card: StopwatchCard) -> None:
        sw = card.sw
        if sw.status not in (RUNNING, PAUSED):
            return
        self._confirm(
            card,
            title="Parar cronômetro?",
            body=f"A contagem de {self._name_html(sw.name)} será finalizada. O tempo fica "
                 "na tela e, ao iniciar de novo, começa do zero.",
            confirm="Parar", variant="light", icon=icons.stop, tint=theme.AMBER,
            action=lambda: self._apply(card, sw.stop),
        )

    def _on_reset(self, card: StopwatchCard) -> None:
        sw = card.sw
        if not sw.running and sw.elapsed() <= 0 and not sw.finished:
            return
        also = " O cronômetro também será parado." if sw.running else ""
        self._confirm(
            card,
            title="Zerar cronômetro?",
            body=f"{self._name_html(sw.name)} volta para 00:00:00 e o tempo registrado "
                 f"será perdido.{also}",
            confirm="Zerar", variant="danger", icon=icons.reset, tint=theme.ROSE,
            action=lambda: self._apply(card, sw.reset),
        )

    def _on_remove(self, card: StopwatchCard) -> None:
        if len(self.cards) <= 1:
            return
        sw = card.sw
        if not sw.running and sw.elapsed() <= 0:
            self._remove(card)
            return
        self._confirm(
            card,
            title="Remover cronômetro?",
            body=f"{self._name_html(sw.name)} e todo o tempo registrado serão apagados. "
                 "Essa ação não pode ser desfeita.",
            confirm="Remover", variant="danger", icon=icons.trash, tint=theme.ROSE,
            action=lambda: self._remove(card),
        )

    def _on_rename(self, card: StopwatchCard, name: str) -> None:
        card.sw.name = name
        self._persist()
        self._update_title()

    def _on_recolor(self, card: StopwatchCard) -> None:
        card.sw.accent = (card.sw.accent + 1) % len(theme.ACCENTS)
        card.set_accent(card.sw.accent)
        self._persist()

    def _confirm(self, card: StopwatchCard, *, title: str, body: str, confirm: str,
                 variant: str, icon, tint: QColor, action: Callable[[], None]) -> None:
        self._settle()
        sw = card.sw
        self._overlay(card).ask(title=title, body_html=body, confirm_text=confirm,
                                variant=variant, icon=icon, tint=tint,
                                chip=lambda: format_hms(sw.elapsed()),
                                accent=theme.accent(sw.accent), on_confirm=action)

    def _apply(self, card: StopwatchCard, change: Callable[[], None]) -> None:
        if card in self.cards:
            change()
            self._changed(card)

    def _changed(self, card: StopwatchCard) -> None:
        self._persist()
        card.sync()
        self._refresh_ticker()
        self._update_title()

    @staticmethod
    def _name_html(text: str) -> str:
        """The stopwatch name, escaped and emphasized for the dialog text."""
        return (f'<span style="color:#F2F2F5; font-weight:600;">'
                f"{html.escape(text, quote=False)}</span>")

    # ----- ticking, title, persistence ---------------------------------------------------

    def _refresh_ticker(self) -> None:
        if not any(sw.running for sw in self.state.stopwatches):
            self.ticker.stop()
            return
        if self.isMinimized():
            interval = 1000  # only the taskbar title needs updating
        else:
            interval = FRAME_MS if self.isActiveWindow() else 2 * FRAME_MS
        if self.ticker.interval() != interval:
            self.ticker.setInterval(interval)
        if not self.ticker.isActive():
            self.ticker.start()

    def _tick(self) -> None:
        if not self.isMinimized():
            for card in self.cards:
                overlay = self._overlays.get(card)
                if overlay is not None and overlay.is_open():
                    overlay.tick()
                elif card.sw.running:
                    card.dial.update()
        self._update_title()

    def _update_title(self) -> None:
        running = [sw for sw in self.state.stopwatches if sw.running]
        if len(running) == 1:
            title = f"{format_hms(running[0].elapsed())} · {running[0].name}"
        elif running:
            title = f"{len(running)} cronômetros rodando"
        else:
            title = "Cometa"
        if title != self._title:
            self._title = title
            self.setWindowTitle(title)

    def _refresh_wallpaper(self) -> None:
        if self.glass.refresh():
            for card in self.cards:
                card.update()

    def _persist(self) -> None:
        try:
            self.store.save(self.state)
        except OSError as exc:
            print(f"[cometa] não foi possível salvar: {exc}", file=sys.stderr)

    def _place(self) -> None:
        """Restore the last position (the size always follows the cards) or center it."""
        width, height = content_width(len(self.cards)), self._content_height()
        if self.state.geometry:
            try:
                self.restoreGeometry(QByteArray.fromBase64(self.state.geometry.encode("ascii")))
            except (ValueError, UnicodeError):
                pass
            self.setWindowState(Qt.WindowState.WindowNoState)  # a widget is never maximized
        screen = (QGuiApplication.screenAt(self.geometry().center())
                  or QGuiApplication.primaryScreen()).availableGeometry()
        width = min(width, screen.width())
        if not self.state.geometry:
            self.setGeometry(screen.center().x() - width // 2, screen.center().y() - height // 2,
                             width, height)
            return
        # Keep the restored position, but make sure the widget is fully on screen.
        x = max(screen.left(), min(self.x(), screen.right() + 1 - width))
        y = max(screen.top(), min(self.y(), screen.bottom() + 1 - height))
        self.setGeometry(x, y, width, height)

    def _content_height(self) -> int:
        return 2 * MARGIN + max((card.height() for card in self.cards), default=CARD_HEIGHT)

    def _fit_height(self, *_) -> None:
        """Follow the tallest card (task panels grow and shrink), growing downwards."""
        needed = self._content_height()
        if self.height() == needed and self.minimumHeight() == needed:
            return
        self.setFixedHeight(needed)
        if self.isVisible():
            screen = (self.screen() or QGuiApplication.primaryScreen()).availableGeometry()
            if self.y() + needed > screen.bottom() + 1:
                self.move(self.x(), max(screen.top(), screen.bottom() + 1 - needed))
        self.surface.update()

    def bring_to_front(self) -> None:
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()

    # ----- Qt events ---------------------------------------------------------------------

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._native_ready:
            self._native_ready = True
            allow_minimize(self)

    def moveEvent(self, event) -> None:
        for card in self.cards:
            card.update()  # the glass shows the wallpaper right behind each card
        super().moveEvent(event)

    def changeEvent(self, event) -> None:
        if event.type() in (QEvent.Type.WindowStateChange, QEvent.Type.ActivationChange):
            self._refresh_ticker()
        super().changeEvent(event)

    def closeEvent(self, event) -> None:
        self._settle()
        self.state.geometry = bytes(self.saveGeometry().toBase64().data()).decode("ascii")
        self._persist()
        super().closeEvent(event)
