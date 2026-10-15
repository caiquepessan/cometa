"""OS integration: Windows title bar styling, taskbar identity and single instance."""
from __future__ import annotations

import contextlib
import hashlib
import sys
from typing import Callable

from PySide6.QtCore import QObject
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QWidget

IS_WINDOWS = sys.platform == "win32"

_GWL_STYLE = -16
_WS_MINIMIZEBOX = 0x00020000
_WS_SYSMENU = 0x00080000


def allow_minimize(window: QWidget) -> None:
    """Frameless windows lack the styles that let the taskbar button (and Win+D)
    minimize and restore them; add those styles back without bringing a frame."""
    if not IS_WINDOWS:
        return
    with contextlib.suppress(Exception):
        import ctypes

        user32 = ctypes.windll.user32
        get_style = user32.GetWindowLongPtrW
        get_style.restype = ctypes.c_ssize_t
        get_style.argtypes = [ctypes.c_void_p, ctypes.c_int]
        set_style = user32.SetWindowLongPtrW
        set_style.restype = ctypes.c_ssize_t
        set_style.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
        hwnd = ctypes.c_void_p(int(window.winId()))
        style = get_style(hwnd, _GWL_STYLE)
        wanted = style | _WS_MINIMIZEBOX | _WS_SYSMENU
        if wanted != style:
            set_style(hwnd, _GWL_STYLE, wanted)


def set_app_id(app_id: str) -> None:
    """Own taskbar identity, so Windows shows our icon instead of Python's."""
    if IS_WINDOWS:
        with contextlib.suppress(Exception):
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)


def _allow_foreground_handoff() -> None:
    if IS_WINDOWS:
        with contextlib.suppress(Exception):
            import ctypes

            ctypes.windll.user32.AllowSetForegroundWindow(-1)  # ASFW_ANY


class SingleInstance(QObject):
    """Keeps one window per data folder; a second launch just focuses the first."""

    def __init__(self, scope: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        digest = hashlib.sha1(scope.encode("utf-8")).hexdigest()[:16]
        self.key = f"cometa-{digest}"
        self._server: QLocalServer | None = None

    def forward_to_running(self) -> bool:
        socket = QLocalSocket()
        socket.connectToServer(self.key)
        if not socket.waitForConnected(300):
            return False
        _allow_foreground_handoff()
        socket.write(b"activate\n")
        socket.flush()
        socket.waitForBytesWritten(300)
        socket.disconnectFromServer()
        return True

    def listen(self, on_activate: Callable[[], None]) -> None:
        self._server = QLocalServer(self)
        if not self._server.listen(self.key):
            QLocalServer.removeServer(self.key)
            self._server.listen(self.key)

        def accept() -> None:
            while self._server.hasPendingConnections():
                conn = self._server.nextPendingConnection()
                conn.disconnected.connect(conn.deleteLater)
                on_activate()

        self._server.newConnection.connect(accept)
