"""Double-click to open Cometa (runs without a console window)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from cometa.app import main
except ImportError as exc:
    message = (
        "Não foi possível iniciar o Cometa.\n\n"
        f"{exc}\n\n"
        "Instale a dependência com:\n    python -m pip install PySide6-Essentials"
    )
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, message, "Cometa", 0x10)
    else:
        print(message, file=sys.stderr)
    raise SystemExit(1)

raise SystemExit(main())
