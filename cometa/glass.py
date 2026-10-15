"""Frosted-glass backdrop.

The desktop wallpaper is blurred, tinted and drawn aligned with the window's position
on screen, so the app reads as a pane of glass over the desktop (the idea behind Mica).
Unlike DWM acrylic/mica, this also works when Windows "transparency effects" are off,
where the system materials collapse to a flat color.
"""
from __future__ import annotations

import os
import random
import sys
import time
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QRect, QRectF, QSize, Qt
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPixmap, QScreen
from PySide6.QtWidgets import QGraphicsBlurEffect, QGraphicsPixmapItem, QGraphicsScene

from . import theme

RECHECK_SECONDS = 4.0


def blurred(pixmap: QPixmap, radius: float) -> QPixmap:
    """Gaussian-blur a pixmap (rendered at half resolution: faster and softer)."""
    dpr = pixmap.devicePixelRatio()
    src = QPixmap(pixmap)
    src.setDevicePixelRatio(1.0)
    small = src.scaled(max(1, src.width() // 2), max(1, src.height() // 2),
                       Qt.AspectRatioMode.IgnoreAspectRatio,
                       Qt.TransformationMode.SmoothTransformation)
    out = _blur_image(small.toImage(), radius * dpr / 2, theme.BG)
    result = QPixmap.fromImage(out).scaled(src.size(), Qt.AspectRatioMode.IgnoreAspectRatio,
                                           Qt.TransformationMode.SmoothTransformation)
    result.setDevicePixelRatio(dpr)
    return result


def _blur_image(image: QImage, radius: float, base: QColor) -> QImage:
    scene = QGraphicsScene()
    item = QGraphicsPixmapItem(QPixmap.fromImage(image))
    effect = QGraphicsBlurEffect()
    effect.setBlurRadius(radius)
    effect.setBlurHints(QGraphicsBlurEffect.BlurHint.QualityHint)
    item.setGraphicsEffect(effect)
    scene.addItem(item)
    out = QImage(image.size(), QImage.Format.Format_ARGB32_Premultiplied)
    out.fill(base)
    p = QPainter(out)
    scene.render(p, QRectF(out.rect()), QRectF(image.rect()))
    p.end()
    return out


def wallpaper_path() -> Path | None:
    if sys.platform != "win32":
        return None
    try:
        import ctypes

        buf = ctypes.create_unicode_buffer(1024)
        if ctypes.windll.user32.SystemParametersInfoW(0x0073, len(buf), buf, 0):  # SPI_GETDESKWALLPAPER
            path = Path(buf.value)
            if buf.value and path.is_file():
                return path
    except (OSError, AttributeError, ValueError):
        pass
    cached = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Themes" / "TranscodedWallpaper"
    return cached if cached.is_file() else None


def wallpaper_style() -> str:
    """'fill' (default), 'fit', 'stretch' — what Windows uses to place the image."""
    if sys.platform != "win32":
        return "fill"
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop") as key:
            style = str(winreg.QueryValueEx(key, "WallpaperStyle")[0]).strip()
    except OSError:
        return "fill"
    return {"2": "stretch", "6": "fit"}.get(style, "fill")


def _place(image: QImage, size: QSize, style: str) -> QImage:
    if style == "stretch":
        return image.scaled(size, Qt.AspectRatioMode.IgnoreAspectRatio,
                            Qt.TransformationMode.SmoothTransformation)
    mode = (Qt.AspectRatioMode.KeepAspectRatio if style == "fit"
            else Qt.AspectRatioMode.KeepAspectRatioByExpanding)
    scaled = image.scaled(size, mode, Qt.TransformationMode.SmoothTransformation)
    out = QImage(size, QImage.Format.Format_ARGB32_Premultiplied)
    out.fill(QColor("#000000"))
    p = QPainter(out)
    p.drawImage((size.width() - scaled.width()) // 2, (size.height() - scaled.height()) // 2, scaled)
    p.end()
    return out


def _luminance(image: QImage) -> float:
    c = QColor(image.scaled(1, 1, Qt.AspectRatioMode.IgnoreAspectRatio,
                            Qt.TransformationMode.SmoothTransformation).pixel(0, 0))
    return 0.2126 * c.redF() + 0.7152 * c.greenF() + 0.0722 * c.blueF()


@lru_cache(maxsize=1)
def noise_tile(size: int = 128, strength: int = 9) -> QPixmap:
    """Fine grain that makes flat translucent surfaces read as frosted glass."""
    rng = random.Random(7)
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    for y in range(size):
        for x in range(size):
            a = rng.randint(0, strength)
            v = 255 if rng.random() < 0.5 else 0
            img.setPixelColor(x, y, QColor(v, v, v, a))
    return QPixmap.fromImage(img)


class WallpaperGlass:
    """Builds and caches the blurred wallpaper for each screen."""

    def __init__(self) -> None:
        self._cache: dict[tuple, QPixmap] = {}
        self.version = 0  # bumps whenever the wallpaper changes
        self._source: tuple[str, float, str] | None = None
        self._checked_at = 0.0

    def refresh(self) -> bool:
        """Re-read the wallpaper now; True when it changed."""
        before = self._source
        self._checked_at = 0.0
        return self._current_source() != before

    def _current_source(self) -> tuple[str, float, str] | None:
        now = time.monotonic()
        if now - self._checked_at < RECHECK_SECONDS:
            return self._source
        self._checked_at = now
        path = wallpaper_path()
        try:
            source = (str(path), path.stat().st_mtime, wallpaper_style()) if path else None
        except OSError:
            source = None
        if source != self._source:
            self._source = source
            self._cache.clear()
            self.version += 1
        return self._source

    def pixmap_for(self, screen: QScreen | None) -> tuple[QPixmap, QRect] | None:
        if screen is None:
            return None
        source = self._current_source()
        if source is None:
            return None
        geo = screen.geometry()
        key = (geo.width(), geo.height())
        if key not in self._cache:
            pm = self._build(source, geo.size())
            if pm is None:
                return None
            self._cache[key] = pm
        return self._cache[key], geo

    @staticmethod
    def _build(source: tuple[str, float, str], size: QSize) -> QPixmap | None:
        image = QImage(source[0])
        if image.isNull() or size.isEmpty():
            return None
        quarter = QSize(max(64, size.width() // 4), max(36, size.height() // 4))
        small = _place(image.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied),
                       quarter, source[2])
        # A soft-light pass over itself adds the "vibrancy" of real glass.
        p = QPainter(small)
        p.setOpacity(0.3)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SoftLight)
        p.drawImage(0, 0, small.copy())
        p.end()
        soft = _blur_image(small, 22, QColor("#000000"))
        # Adaptive tint: bright wallpapers get a darker veil, so text always stays legible.
        y = _luminance(soft)
        veil = max(0.14, min(0.78, (y - 0.20) / max(0.01, y - 0.02)))
        p = QPainter(soft)
        p.fillRect(soft.rect(), theme.alpha(theme.BG, veil))
        p.end()
        full = QPixmap.fromImage(soft.scaled(size, Qt.AspectRatioMode.IgnoreAspectRatio,
                                             Qt.TransformationMode.SmoothTransformation))
        p = QPainter(full)
        p.fillRect(full.rect(), QBrush(noise_tile()))
        p.end()
        return full

