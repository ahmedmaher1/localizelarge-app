"""The one place API keys are stored.

On Windows the keys live in a single file,
``%APPDATA%\\LocalizeLarge\\api-keys.locked.json``. Each key is encrypted by
Windows (DPAPI) for the current Windows account before it is written, so the
file is useless on another computer or under another account. No key is ever
written in clear text: not to this file, not to ``settings.json``, not to a
log, a project file or an export.

On other systems (development and tests only; v1 ships for Windows) the keys
go to the system keyring when one is available. With no keyring they are kept
in memory for the session and are not saved at all.

File format::

    {"format": "localizelarge-api-keys", "formatVersion": 1,
     "keys": {"claude": "<base64 of the DPAPI blob>", ...}}
"""
from __future__ import annotations

import base64
import json
import logging
import os
import sys
import threading
from pathlib import Path
from typing import Dict, Iterable, Optional

from localizelarge import paths

logger = logging.getLogger(__name__)

FILE_FORMAT = "localizelarge-api-keys"
FILE_FORMAT_VERSION = 1

#: The providers that have an API key. Ollama has none.
KEY_NAMES = ("claude", "openai", "gemini")
DISPLAY_NAMES = {"claude": "Claude", "openai": "OpenAI", "gemini": "Gemini"}
_ALIASES = {"anthropic": "claude", "google": "gemini"}

#: Extra entropy mixed into DPAPI, so another program running as the same user
#: cannot unlock the file with a plain CryptUnprotectData call.
_ENTROPY = b"LocalizeLarge api keys v1"

PRESENT = "present"
ABSENT = "absent"
UNREADABLE = "unreadable"


def canonical(name: str) -> Optional[str]:
    """The store's name for a provider, or None when it has no API key here."""
    name = (name or "").strip().lower()
    name = _ALIASES.get(name, name)
    return name if name in KEY_NAMES else None


def display_name(name: str) -> str:
    return DISPLAY_NAMES.get(canonical(name) or "", (name or "").title())


def mask(key: str) -> str:
    """A key as it may be shown or logged: the last four characters only."""
    key = key or ""
    if len(key) <= 8:
        return "•" * len(key)
    return "•" * 8 + key[-4:]


class KeyStoreError(Exception):
    """A key could not be saved."""


# ── Backends ─────────────────────────────────────────────────────────────

class _Backend:
    name = "none"
    persistent = False

    def lock(self, plain: str) -> str:            # → text safe to write to disk
        raise NotImplementedError

    def unlock(self, locked: str) -> str:         # raises ValueError when it cannot
        raise NotImplementedError


class DpapiBackend(_Backend):
    """Windows Data Protection API, current-user scope."""

    name = "Windows DPAPI (this Windows account)"
    persistent = True

    def __init__(self):
        import ctypes
        from ctypes import wintypes

        class _Blob(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

        self._ctypes = ctypes
        self._Blob = _Blob
        self._crypt32 = ctypes.windll.crypt32
        self._kernel32 = ctypes.windll.kernel32

    def _blob(self, data: bytes):
        buffer = self._ctypes.create_string_buffer(data, len(data))
        return self._Blob(len(data), self._ctypes.cast(buffer, self._ctypes.POINTER(self._ctypes.c_char))), buffer

    def _call(self, function, data: bytes) -> bytes:
        ctypes = self._ctypes
        source, _keep_source = self._blob(data)
        entropy, _keep_entropy = self._blob(_ENTROPY)
        result = self._Blob()
        CRYPTPROTECT_UI_FORBIDDEN = 0x1
        ok = function(ctypes.byref(source), None, ctypes.byref(entropy), None, None,
                      CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(result))
        if not ok:
            raise ValueError(f"Windows could not process the key (error {ctypes.GetLastError()})")
        try:
            return ctypes.string_at(result.pbData, result.cbData)
        finally:
            self._kernel32.LocalFree(result.pbData)

    def lock(self, plain: str) -> str:
        blob = self._call(self._crypt32.CryptProtectData, plain.encode("utf-8"))
        return base64.b64encode(blob).decode("ascii")

    def unlock(self, locked: str) -> str:
        try:
            blob = base64.b64decode(locked.encode("ascii"), validate=True)
        except Exception as error:
            raise ValueError("The stored key is damaged") from error
        return self._call(self._crypt32.CryptUnprotectData, blob).decode("utf-8")


class KeyringBackend(_Backend):
    """The system keyring (macOS Keychain, Secret Service). Development only."""

    name = "system keyring"
    persistent = True
    SERVICE = "LocalizeLarge"

    def __init__(self):
        import keyring
        from keyring.backends import fail

        backend = keyring.get_keyring()
        if isinstance(backend, fail.Keyring):
            raise RuntimeError("no usable keyring")
        self._keyring = keyring

    def get(self, name: str) -> Optional[str]:
        return self._keyring.get_password(self.SERVICE, name)

    def set(self, name: str, value: Optional[str]) -> None:
        if value:
            self._keyring.set_password(self.SERVICE, name, value)
        else:
            try:
                self._keyring.delete_password(self.SERVICE, name)
            except Exception:
                pass


class MemoryBackend(_Backend):
    """Keys held for this session only. Nothing is written anywhere."""

    name = "memory only (keys are not saved)"
    persistent = False


def _pick_backend() -> _Backend:
    if sys.platform == "win32":
        return DpapiBackend()
    try:
        return KeyringBackend()
    except Exception as error:
        logger.info("No system keyring for API keys (%s): keys are kept for this session only",
                    type(error).__name__)
        return MemoryBackend()


# ── The store ────────────────────────────────────────────────────────────

class KeyStore:
    """API keys by provider name.

    ``path`` is the locked file (used by the DPAPI backend, and by any backend
    that implements ``lock``/``unlock``). ``backend`` can be given for tests.
    """

    def __init__(self, path: Optional[Path] = None, backend: Optional[_Backend] = None):
        self.path = Path(path) if path is not None else paths.api_keys_file()
        self.backend = backend if backend is not None else _pick_backend()
        self._memory: Dict[str, str] = {}
        self._lock = threading.RLock()

    # -- which storage is in use ------------------------------------------

    @property
    def persistent(self) -> bool:
        return self.backend.persistent

    @property
    def uses_file(self) -> bool:
        return not isinstance(self.backend, (KeyringBackend, MemoryBackend))

    def describe(self) -> str:
        if self.uses_file:
            return f"{self.backend.name}; file {self.path}"
        return self.backend.name

    # -- file -------------------------------------------------------------

    def _read_file(self) -> Dict[str, str]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as error:
            logger.warning("The API key file could not be read (%s)", type(error).__name__)
            return {}
        keys = data.get("keys") if isinstance(data, dict) else None
        if not isinstance(keys, dict):
            return {}
        return {k: v for k, v in keys.items() if k in KEY_NAMES and isinstance(v, str) and v}

    def _write_file(self, locked: Dict[str, str]) -> None:
        payload = {"format": FILE_FORMAT, "formatVersion": FILE_FORMAT_VERSION,
                   "keys": {name: locked[name] for name in KEY_NAMES if name in locked}}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".tmp")
        try:
            temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            os.replace(temporary, self.path)
        except OSError as error:
            try:
                temporary.unlink()
            except OSError:
                pass
            raise KeyStoreError(f"The API key file could not be written: {error}") from error

    # -- reading ----------------------------------------------------------

    def status(self, name: str) -> str:
        """PRESENT, ABSENT, or UNREADABLE (stored, but cannot be unlocked here)."""
        key_name = canonical(name)
        if key_name is None:
            return ABSENT
        with self._lock:
            if isinstance(self.backend, MemoryBackend):
                return PRESENT if self._memory.get(key_name) else ABSENT
            if isinstance(self.backend, KeyringBackend):
                try:
                    return PRESENT if self.backend.get(key_name) else ABSENT
                except Exception:
                    return UNREADABLE
            locked = self._read_file().get(key_name)
            if not locked:
                return ABSENT
            try:
                return PRESENT if self.backend.unlock(locked) else ABSENT
            except Exception:
                return UNREADABLE

    def get(self, name: str) -> Optional[str]:
        """The key, or None when there is none or it cannot be unlocked here."""
        key_name = canonical(name)
        if key_name is None:
            return None
        with self._lock:
            if isinstance(self.backend, MemoryBackend):
                return self._memory.get(key_name) or None
            if isinstance(self.backend, KeyringBackend):
                try:
                    return self.backend.get(key_name) or None
                except Exception:
                    return None
            locked = self._read_file().get(key_name)
            if not locked:
                return None
            try:
                return self.backend.unlock(locked) or None
            except Exception:
                return None

    def all(self, names: Iterable[str] = KEY_NAMES) -> Dict[str, str]:
        """Every key that is present and readable."""
        found = {}
        for name in names:
            value = self.get(name)
            if value:
                found[canonical(name)] = value
        return found

    def unreadable(self) -> list:
        return [name for name in KEY_NAMES if self.status(name) == UNREADABLE]

    # -- writing ----------------------------------------------------------

    def set(self, name: str, value: Optional[str]) -> None:
        """Save a key. An empty value removes it. Raises KeyStoreError on failure."""
        key_name = canonical(name)
        if key_name is None:
            raise KeyStoreError(f"{name!r} is not a provider with an API key")
        value = (value or "").strip()
        with self._lock:
            if isinstance(self.backend, MemoryBackend):
                if value:
                    self._memory[key_name] = value
                else:
                    self._memory.pop(key_name, None)
                return
            if isinstance(self.backend, KeyringBackend):
                try:
                    self.backend.set(key_name, value or None)
                except Exception as error:
                    raise KeyStoreError(f"The keyring refused the key: {type(error).__name__}") from error
                return
            locked = self._read_file()
            if value:
                try:
                    locked[key_name] = self.backend.lock(value)
                except Exception as error:
                    raise KeyStoreError(f"The key could not be locked: {error}") from error
            else:
                locked.pop(key_name, None)
            self._write_file(locked)


_default: Optional[KeyStore] = None
_default_lock = threading.Lock()


def default_store() -> KeyStore:
    """The store the app uses. Created on first use."""
    global _default
    with _default_lock:
        if _default is None:
            _default = KeyStore()
        return _default


def set_default_store(store: Optional[KeyStore]) -> None:
    """Replace the app's store (tests), or reset it with None."""
    global _default
    with _default_lock:
        _default = store


# ── Keeping keys out of settings.json ────────────────────────────────────

#: Names under which a settings file from the base app may hold a key in clear text.
_CLEAR_TEXT_NAMES = {
    "openai": "openai", "claude": "claude", "anthropic": "claude",
    "gemini": "gemini", "google": "gemini",
}
#: Key-shaped entries of providers Localize Large does not use: removed, not moved.
_DISCARDED_NAMES = (
    "mistral", "deepseek", "openrouter", "custom_openai", "google_translate", "deepl",
    "microsoft_translate", "azure_translate", "modernmt", "mymemory", "amazon_translate",
    "amazon_translate_secret", "aws_translate",
)


def without_secrets(section: Dict[str, str]) -> Dict[str, str]:
    """A settings ``api_keys`` section with every key removed. What is left is
    not secret (the Ollama address, for example)."""
    return {name: value for name, value in (section or {}).items()
            if name not in _CLEAR_TEXT_NAMES and name not in _DISCARDED_NAMES}


def move_clear_text_keys(settings_path: Path, store: Optional[KeyStore] = None) -> int:
    """Move any API key found in clear text in ``settings.json`` into the store
    and rewrite the file without it. Returns how many keys were moved.

    A fresh Localize Large never writes keys there. This handles a settings
    file carried over from the base app. The key is removed from the file only
    after the store has taken it; a key the store already has is not replaced.
    """
    store = store or default_store()
    settings_path = Path(settings_path)
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return 0
    if not isinstance(data, dict):
        return 0
    moved = 0
    changed = False
    # Custom endpoint profiles of the base app carried their own keys.
    llm_settings = (data.get("ui") or {}).get("llm_settings") if isinstance(data.get("ui"), dict) else None
    if isinstance(llm_settings, dict):
        for name in ("custom_openai_profiles", "custom_mt_profiles"):
            if llm_settings.get(name):
                llm_settings[name] = []
                changed = True
    section = data.get("api_keys")
    if not isinstance(section, dict):
        section = {}
    for name in list(section):
        value = section.get(name)
        if name in _DISCARDED_NAMES:
            del section[name]
            changed = True
            continue
        target = _CLEAR_TEXT_NAMES.get(name)
        if target is None:
            continue
        if isinstance(value, str) and value.strip():
            if not store.persistent:
                continue                      # nowhere safe to put it: leave the file alone
            if store.status(target) == ABSENT:
                try:
                    store.set(target, value)
                except KeyStoreError:
                    continue
                moved += 1
        del section[name]
        changed = True
    if changed:
        temporary = settings_path.with_name(settings_path.name + ".tmp")
        temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, settings_path)
    return moved
