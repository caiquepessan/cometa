"""Stopwatch model and JSON persistence.

Time is stored as wall-clock timestamps, so a running stopwatch keeps counting
while the app is closed (or the computer is off) and picks up exactly where it
should when the app opens again.
"""
from __future__ import annotations

import contextlib
import json
import math
import os
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

SCHEMA_VERSION = 1
MAX_NAME_LENGTH = 40


def now() -> float:
    return time.time()


IDLE, RUNNING, PAUSED, FINISHED = "idle", "running", "paused", "finished"


@dataclass
class Stopwatch:
    name: str = "Cronômetro"
    accent: int = 0
    accumulated: float = 0.0  # seconds banked by previous runs
    started_at: float | None = None  # epoch seconds when the current run began
    finished: bool = False  # stopped for good: the next start counts from zero
    id: str = field(default_factory=lambda: uuid.uuid4().hex)

    @property
    def running(self) -> bool:
        return self.started_at is not None

    @property
    def status(self) -> str:
        if self.started_at is not None:
            return RUNNING
        if self.finished:
            return FINISHED
        return PAUSED if self.accumulated > 0 else IDLE

    def elapsed(self, at: float | None = None) -> float:
        if self.started_at is None:
            return self.accumulated
        current = now() if at is None else at
        # A clock moved backwards must never make the stopwatch go backwards.
        return self.accumulated + max(0.0, current - self.started_at)

    def start(self) -> None:
        """Start, or resume after a pause. After a stop, a new count begins from zero."""
        if self.started_at is None:
            if self.finished:
                self.accumulated = 0.0
                self.finished = False
            self.started_at = now()

    def pause(self) -> None:
        if self.started_at is not None:
            self.accumulated = self.elapsed()
            self.started_at = None

    def stop(self) -> None:
        """Finish the count; the final time stays on display until a new start or reset."""
        self.pause()
        self.finished = True

    def reset(self) -> None:
        self.accumulated = 0.0
        self.started_at = None
        self.finished = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "accent": self.accent,
            "accumulated": round(self.accumulated, 3),
            "started_at": self.started_at,
            "finished": self.finished,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Stopwatch:
        name = str(data.get("name") or "").strip()[:MAX_NAME_LENGTH] or "Cronômetro"
        accumulated = float(data.get("accumulated") or 0.0)
        if not math.isfinite(accumulated) or accumulated < 0:
            accumulated = 0.0
        started_at = data.get("started_at")
        if started_at is not None:
            started_at = float(started_at)
            if not math.isfinite(started_at) or started_at <= 0:
                started_at = None
        return cls(
            name=name,
            accent=int(data.get("accent") or 0),
            accumulated=accumulated,
            started_at=started_at,
            finished=bool(data.get("finished")) and started_at is None,
            id=str(data.get("id") or uuid.uuid4().hex),
        )


@dataclass
class AppState:
    stopwatches: list[Stopwatch] = field(default_factory=list)
    geometry: str | None = None  # base64 of QWidget.saveGeometry()
    on_top: bool = True  # floating window stays above other windows


DATA_DIR_NAME = "Cometa"
LEGACY_DATA_DIR_NAME = "Cronometro"  # pre-1.0 builds, when the app was called Cronômetro


def _data_base() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")


def default_data_dir() -> Path:
    override = os.environ.get("COMETA_DATA_DIR")
    if override:
        return Path(override)
    return _data_base() / DATA_DIR_NAME


class Store:
    """Reads and atomically writes the app state as JSON."""

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or default_data_dir()
        self.path = self.directory / "state.json"
        # Only the default location picks up the data of the pre-1.0 builds.
        default = directory is None and not os.environ.get("COMETA_DATA_DIR")
        self._legacy = _data_base() / LEGACY_DATA_DIR_NAME / "state.json" if default else None

    def load(self) -> AppState:
        source = self.path
        if not source.exists() and self._legacy is not None and self._legacy.exists():
            source = self._legacy  # first run after the rename; the next save moves it over
        try:
            raw = json.loads(source.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("state root is not an object")
        except FileNotFoundError:
            return AppState()
        except (OSError, ValueError):
            if source == self.path:
                self._quarantine()
            return AppState()

        stopwatches = []
        for item in raw.get("stopwatches", []):
            if not isinstance(item, dict):
                continue
            with contextlib.suppress(TypeError, ValueError):
                stopwatches.append(Stopwatch.from_dict(item))
        window = raw.get("window") if isinstance(raw.get("window"), dict) else {}
        geometry = window.get("geometry")
        return AppState(stopwatches, geometry if isinstance(geometry, str) else None,
                        bool(window.get("on_top", True)))

    def save(self, state: AppState) -> None:
        payload = {
            "version": SCHEMA_VERSION,
            "saved_at": now(),
            "stopwatches": [sw.to_dict() for sw in state.stopwatches],
            "window": {"geometry": state.geometry, "on_top": state.on_top},
        }
        self.directory.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".state-", suffix=".tmp", dir=self.directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
                fh.flush()
                os.fsync(fh.fileno())
            self._replace(tmp)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise

    def _replace(self, tmp: str) -> None:
        # On Windows an antivirus or backup tool may briefly hold the target open.
        for attempt in range(5):
            try:
                os.replace(tmp, self.path)
                return
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.05 * (attempt + 1))

    def _quarantine(self) -> None:
        """Keep an unreadable state file aside instead of silently overwriting it."""
        with contextlib.suppress(OSError):
            stamp = time.strftime("%Y%m%d-%H%M%S")
            self.path.replace(self.path.with_name(f"state.corrupt-{stamp}.json"))


def split_time(seconds: float) -> tuple[int, int, int, int]:
    """Return (hours, minutes, seconds, centiseconds), truncating like a stopwatch."""
    total_cs = int(max(0.0, seconds) * 100)
    cs = total_cs % 100
    total_s = total_cs // 100
    hours, rest = divmod(total_s, 3600)
    minutes, secs = divmod(rest, 60)
    return hours, minutes, secs, cs


def format_hms(seconds: float) -> str:
    h, m, s, _ = split_time(seconds)
    return f"{h:02d}:{m:02d}:{s:02d}"
