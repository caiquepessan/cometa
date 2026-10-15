"""Application entry point."""
from __future__ import annotations

import sys

from PySide6.QtCore import QLibraryInfo, QLocale, Qt, QTranslator
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from . import theme
from .model import Store
from .system import SingleInstance, set_app_id
from .window import MainWindow


def _dark_palette() -> QPalette:
    pal = QPalette()
    roles = {
        QPalette.ColorRole.Window: "#0B0B10",
        QPalette.ColorRole.WindowText: "#F2F2F5",
        QPalette.ColorRole.Base: "#121218",
        QPalette.ColorRole.AlternateBase: "#17171E",
        QPalette.ColorRole.Text: "#F2F2F5",
        QPalette.ColorRole.Button: "#17171E",
        QPalette.ColorRole.ButtonText: "#F2F2F5",
        QPalette.ColorRole.Highlight: "#818CF8",
        QPalette.ColorRole.HighlightedText: "#FFFFFF",
        QPalette.ColorRole.ToolTipBase: "#1B1B23",
        QPalette.ColorRole.ToolTipText: "#E7E7EC",
        QPalette.ColorRole.PlaceholderText: "#5A5A66",
    }
    for role, color in roles.items():
        pal.setColor(role, QColor(color))
    return pal


def main(argv: list[str] | None = None) -> int:
    if not getattr(sys, "frozen", False):
        # Run from source, the process is python.exe: claim our own taskbar identity.
        # The packaged Cometa.exe already has one (and matches its shortcuts).
        set_app_id("Cometa.Desktop")
    app = QApplication(sys.argv if argv is None else argv)
    app.setApplicationName("Cometa")
    app.setOrganizationName("Cometa")

    store = Store()
    instance = SingleInstance(str(store.directory.resolve()))
    if instance.forward_to_running():
        return 0

    if hasattr(app.styleHints(), "setColorScheme"):
        app.styleHints().setColorScheme(Qt.ColorScheme.Dark)
    app.setStyle("Fusion")
    app.setPalette(_dark_palette())
    theme.init_fonts()
    app.setFont(theme.font(13))
    app.setStyleSheet(theme.STYLESHEET)

    translator = QTranslator(app)
    if translator.load(QLocale("pt_BR"), "qtbase", "_",
                       QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(translator)

    window = MainWindow(store, store.load())
    instance.listen(window.bring_to_front)
    app.aboutToQuit.connect(window._persist)
    window.show()
    return app.exec()
