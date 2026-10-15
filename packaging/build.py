"""Builds the standalone Windows app and its installer.

    python -m pip install pyinstaller
    python packaging/build.py OUTPUT_DIR

OUTPUT_DIR receives:
    Cometa/                             the installer folder:
        app/                            Cometa.exe and its runtime (PyInstaller, one folder)
        install.ps1, uninstall.ps1
        Instalar Cometa.cmd             double-click to install for the current user
    Cometa-<version>-windows-x64.zip    the same folder, zipped for a release
"""
from __future__ import annotations

import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

VERSION_INFO = """\
VSVersionInfo(
  ffi=FixedFileInfo(filevers={nums}, prodvers={nums}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('041604B0', [
      StringStruct('CompanyName', 'Cometa'),
      StringStruct('FileDescription', 'Cometa'),
      StringStruct('FileVersion', '{version}'),
      StringStruct('InternalName', 'Cometa'),
      StringStruct('LegalCopyright', 'MIT License'),
      StringStruct('OriginalFilename', 'Cometa.exe'),
      StringStruct('ProductName', 'Cometa'),
      StringStruct('ProductVersion', '{version}')])]),
    VarFileInfo([VarStruct('Translation', [1046, 1200])])
  ]
)
"""


def write_icon(path: Path) -> None:
    """Multi-size .ico (PNG-compressed entries) rendered from the in-app icon."""
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    from PySide6.QtWidgets import QApplication

    from cometa.appicon import _render

    _app = QApplication.instance() or QApplication([])
    images = []
    for size in (16, 20, 24, 32, 40, 48, 64, 128, 256):
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        _render(size).save(buffer, "PNG")
        buffer.close()
        images.append((size, bytes(data)))
    offset = 6 + 16 * len(images)
    entries, blobs = b"", b""
    for size, png in images:
        side = 0 if size >= 256 else size  # 0 means 256 in the ICO format
        entries += struct.pack("<BBBBHHII", side, side, 0, 0, 1, 32, len(png), offset + len(blobs))
        blobs += png
    path.write_bytes(struct.pack("<HHH", 0, 1, len(images)) + entries + blobs)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    out = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(ROOT))
    import cometa

    version = cometa.__version__
    work = Path(tempfile.mkdtemp(prefix="cometa-build-"))
    try:
        icon = work / "cometa.ico"
        write_icon(icon)
        version_file = work / "version.txt"
        nums = tuple(int(n) for n in (version.split(".") + ["0"] * 4)[:4])
        version_file.write_text(VERSION_INFO.format(nums=nums, version=version), encoding="utf-8")
        subprocess.run([
            sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
            "--name", "Cometa", "--icon", str(icon), "--version-file", str(version_file),
            "--distpath", str(work / "dist"), "--workpath", str(work / "build"),
            "--specpath", str(work), "--exclude-module", "tkinter",
            str(ROOT / "Cometa.pyw"),
        ], check=True)

        bundle = out / "Cometa"
        if bundle.exists():
            shutil.rmtree(bundle)
        bundle.mkdir(parents=True)
        shutil.copytree(work / "dist" / "Cometa", bundle / "app")
        # Windows PowerShell 5.1 only reads scripts as UTF-8 when they carry a BOM.
        for script in ("install.ps1", "uninstall.ps1"):
            (bundle / script).write_text((HERE / script).read_text(encoding="utf-8"),
                                         encoding="utf-8-sig")
        shutil.copy2(HERE / "Instalar.cmd", bundle / "Instalar Cometa.cmd")
        archive = shutil.make_archive(str(out / f"Cometa-{version}-windows-x64"), "zip",
                                      root_dir=out, base_dir="Cometa")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print(f"Instalador: {bundle}")
    print(f"Release:    {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
