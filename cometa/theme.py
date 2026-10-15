"""Design tokens: colors, accent palettes and typography."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QRectF
from PySide6.QtGui import QBrush, QColor, QFont, QFontDatabase, QLinearGradient, QPen

BG = QColor("#08080C")
SURFACE_TOP = QColor("#15151C")
SURFACE_BOTTOM = QColor("#0F0F14")
TEXT = QColor("#F2F2F5")
MUTED = QColor("#8C8C99")
FAINT = QColor("#55555F")
ON_ACCENT = QColor("#0A0A0F")
ROSE = QColor("#FB7185")
ROSE_TEXT = QColor("#FDA4AF")
AMBER = QColor("#FBBF24")
WHITE = QColor("#FFFFFF")


@dataclass(frozen=True)
class Accent:
    name: str
    start: QColor
    end: QColor


ACCENTS = (
    Accent("Índigo", QColor("#818CF8"), QColor("#C084FC")),
    Accent("Esmeralda", QColor("#34D399"), QColor("#2DD4BF")),
    Accent("Âmbar", QColor("#FBBF24"), QColor("#FB923C")),
    Accent("Céu", QColor("#38BDF8"), QColor("#818CF8")),
    Accent("Rosa", QColor("#FB7185"), QColor("#E879F9")),
    Accent("Lima", QColor("#A3E635"), QColor("#34D399")),
)


def accent(index: int) -> Accent:
    return ACCENTS[index % len(ACCENTS)]


def alpha(color: QColor, a: float) -> QColor:
    c = QColor(color)
    c.setAlphaF(max(0.0, min(1.0, a)))
    return c


def mix(a: QColor, b: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor.fromRgbF(
        a.redF() + (b.redF() - a.redF()) * t,
        a.greenF() + (b.greenF() - a.greenF()) * t,
        a.blueF() + (b.blueF() - a.blueF()) * t,
        a.alphaF() + (b.alphaF() - a.alphaF()) * t,
    )


def rim_pen(rect: QRectF, top: QColor, bottom: QColor, *, diagonal: bool = False,
            width: float = 1.0) -> QPen:
    """Glass edge: bright where light hits (top / top-left), fading toward the bottom."""
    end = rect.bottomRight() if diagonal else rect.bottomLeft()
    grad = QLinearGradient(rect.topLeft(), end)
    grad.setColorAt(0.0, top)
    grad.setColorAt(0.45, mix(top, bottom, 0.75))
    grad.setColorAt(1.0, bottom)
    return QPen(QBrush(grad), width)


def glass_sheen(rect: QRectF, strength: float = 1.0) -> QLinearGradient:
    """Frosted fill, brighter at the top like light falling on a pane of glass."""
    grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    grad.setColorAt(0.0, alpha(WHITE, 0.085 * strength))
    grad.setColorAt(0.5, alpha(WHITE, 0.03 * strength))
    grad.setColorAt(1.0, alpha(WHITE, 0.018 * strength))
    return grad


class _Fonts:
    text = "Segoe UI"
    display = "Segoe UI"
    variable = False  # whether the families expose a variable weight axis


_fonts = _Fonts()


def init_fonts() -> None:
    """Pick the best installed families. Needs a QGuiApplication."""
    families = set(QFontDatabase.families())
    if {"Segoe UI Variable Text", "Segoe UI Variable Display"} <= families:
        _fonts.text = "Segoe UI Variable Text"
        _fonts.display = "Segoe UI Variable Display"
        _fonts.variable = hasattr(QFont, "setVariableAxis")
        return
    for family in ("Inter", "SF Pro Text", "Segoe UI", "Helvetica Neue", "Cantarell", "Arial"):
        if family in families:
            _fonts.text = _fonts.display = family
            return


def font(px: float, weight: int = 400, *, display: bool = False, tabular: bool = False,
         spacing: float = 0.0, smooth: bool = False, rich: bool = False) -> QFont:
    """Build a font. `smooth` drops hinting (even letter spacing), `rich` keeps the
    weight overridable by rich text (<b>), which a fixed variable axis would block."""
    f = QFont(_fonts.display if display else _fonts.text)
    f.setPixelSize(max(1, round(px)))
    if _fonts.variable and not rich:
        f.setVariableAxis(QFont.Tag("wght"), float(weight))
    else:
        f.setWeight(QFont.Weight(min(900, max(100, round(weight / 100) * 100))))
    if tabular and hasattr(QFont, "setFeature"):
        f.setFeature(QFont.Tag("tnum"), 1)
    if display or smooth or spacing:
        f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    if display:
        # Large thin digits look cleaner with grayscale antialiasing than ClearType.
        f.setStyleStrategy(QFont.StyleStrategy.NoSubpixelAntialias)
    if spacing:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    return f


STYLESHEET = """
QToolTip {
    color: #E7E7EC;
    background-color: #1B1B23;
    border: 1px solid #2B2B35;
    padding: 5px 8px;
}
QMenu {
    background-color: rgba(22, 22, 30, 245);
    border: 1px solid rgba(255, 255, 255, 30);
    border-radius: 12px;
    padding: 6px;
}
QMenu::item {
    color: #E7E7EC;
    padding: 6px 22px 6px 14px;
    border-radius: 6px;
}
QMenu::item:selected { background-color: rgba(255, 255, 255, 0.08); }
QMenu::item:disabled { color: #5A5A66; }
QMenu::separator { height: 1px; background: #2B2B35; margin: 5px 8px; }
QScrollBar:horizontal {
    height: 12px;
    background: transparent;
    margin: 0px 28px 4px 28px;
}
QScrollBar::handle:horizontal {
    background: rgba(255, 255, 255, 0.10);
    border-radius: 3px;
    min-width: 48px;
    margin: 3px 0px;
}
QScrollBar::handle:horizontal:hover { background: rgba(255, 255, 255, 0.20); }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }
QScrollBar:vertical {
    width: 8px;
    background: transparent;
    margin: 2px 0px 2px 0px;
}
QScrollBar::handle:vertical {
    background: rgba(255, 255, 255, 0.12);
    border-radius: 3px;
    min-height: 24px;
    margin: 0px 2px;
}
QScrollBar::handle:vertical:hover { background: rgba(255, 255, 255, 0.22); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
"""
