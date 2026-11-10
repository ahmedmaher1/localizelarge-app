"""Every folder and file Localize Large reads or writes on its own account.

This module is the only place that builds these paths. Nothing else joins
``APPDATA``, ``LOCALAPPDATA`` or a home folder by hand.

Two roots, both named ``LocalizeLarge``:

* the **settings root** – settings, the locked API-key file, prompts, quality
  packs. Windows: ``%APPDATA%\\LocalizeLarge``.
* the **local root** – databases, logs, caches. Windows:
  ``%LOCALAPPDATA%\\LocalizeLarge``.

On other systems (development and tests only; v1 ships for Windows) the roots
follow XDG: ``$XDG_CONFIG_HOME/LocalizeLarge`` and
``$XDG_DATA_HOME/LocalizeLarge``.

The app never reads or writes a Supervertaler folder. There is no fallback to
one and no migration from one.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR_NAME = "LocalizeLarge"

PROJECT_EXTENSION = ".llproj"
LEGACY_PROJECT_EXTENSION = ".svproj"
PACK_EXTENSION = ".llqp"

DATABASE_FILE_NAME = "localizelarge.db"
API_KEYS_FILE_NAME = "api-keys.locked.json"


def _env_dir(name: str) -> Path | None:
    value = os.environ.get(name)
    return Path(value) if value else None


def settings_root() -> Path:
    """Settings root. Windows: ``%APPDATA%\\LocalizeLarge``."""
    if sys.platform == "win32":
        base = _env_dir("APPDATA") or Path.home() / "AppData" / "Roaming"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = _env_dir("XDG_CONFIG_HOME") or Path.home() / ".config"
    return base / APP_DIR_NAME


def local_root() -> Path:
    """Local root. Windows: ``%LOCALAPPDATA%\\LocalizeLarge``."""
    if sys.platform == "win32":
        base = _env_dir("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = _env_dir("XDG_DATA_HOME") or Path.home() / ".local" / "share"
    return base / APP_DIR_NAME


def _made(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


# ── Settings root ────────────────────────────────────────────────────────

def settings_dir() -> Path:
    """Folder of ``settings.json`` and the other settings files."""
    return settings_root() / "workbench" / "settings"


def settings_file() -> Path:
    return settings_dir() / "settings.json"


def api_keys_file() -> Path:
    """The one API-key store: a file locked to this Windows account."""
    return settings_root() / API_KEYS_FILE_NAME


def prompt_library_dir() -> Path:
    return settings_root() / "prompt_library"


def packs_dir() -> Path:
    """Installed quality packs: ``packs/<id>/<version>/``."""
    return settings_root() / "packs"


def pricing_override_file() -> Path:
    return settings_root() / "pricing.json"


# ── Local root ───────────────────────────────────────────────────────────

def database_dir() -> Path:
    return local_root() / "resources"


def database_file() -> Path:
    """The translation-memory and glossary database."""
    return database_dir() / DATABASE_FILE_NAME


def logs_dir() -> Path:
    return local_root() / "logs"


def crash_log_file() -> Path:
    return logs_dir() / "crash.log"


def cache_dir() -> Path:
    return local_root() / "cache"


def ensure_roots() -> None:
    """Create both roots and their standard folders."""
    for folder in (settings_root(), settings_dir(), database_dir(), logs_dir(), cache_dir()):
        _made(folder)


def is_project_file(path: str | os.PathLike[str]) -> bool:
    """True for ``.llproj`` and for the older ``.svproj``, which is opened read-compatible."""
    suffix = Path(path).suffix.lower()
    return suffix in (PROJECT_EXTENSION, LEGACY_PROJECT_EXTENSION)
