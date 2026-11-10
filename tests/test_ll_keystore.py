"""Phase 3: API keys live in one locked file and nowhere in clear text."""
import base64
import json
import os
import sys
import types
from pathlib import Path

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from localizelarge import paths  # noqa: E402
from localizelarge.security import keystore  # noqa: E402
from modules import llm_clients  # noqa: E402

CLAUDE = "sk-ant-api03-PROJ001-claude-KEY-0123456789abcdef"
OPENAI = "sk-proj-PROJ001-openai-KEY-fedcba9876543210"
GEMINI = "AIzaSyPROJ001-gemini-KEY-0a1b2c3d4e5f"
OLLAMA = "http://localhost:11434"


class FakeAccountLock(keystore._Backend):
    """Stands in for DPAPI on any system: locks with a per-"account" secret so
    the key never appears in the file, and another account cannot unlock it."""

    name = "fake account lock"
    persistent = True

    def __init__(self, account="alice"):
        self.account = account.encode()

    def _xor(self, data: bytes) -> bytes:
        return bytes(b ^ self.account[i % len(self.account)] ^ 0x5A for i, b in enumerate(data))

    def lock(self, plain):
        return base64.b64encode(b"LOCK" + self._xor(plain.encode("utf-8"))).decode("ascii")

    def unlock(self, locked):
        raw = base64.b64decode(locked)
        plain = self._xor(raw[4:])
        try:
            text = plain.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError("cannot unlock") from error
        if not raw.startswith(b"LOCK") or not text.isprintable():
            raise ValueError("cannot unlock")
        return text


def _backend():
    """Real DPAPI on Windows, the stand-in elsewhere."""
    return keystore.DpapiBackend() if sys.platform == "win32" else FakeAccountLock()


@pytest.fixture
def profile(tmp_path, monkeypatch):
    """A throwaway profile with its own key store as the app's default."""
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "Roaming"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "Local"))
    paths.ensure_roots()
    store = keystore.KeyStore(backend=_backend())
    keystore.set_default_store(store)
    yield types.SimpleNamespace(root=tmp_path, store=store, settings=paths.settings_file())
    keystore.set_default_store(None)


def _every_file(root: Path):
    return [p for p in root.rglob("*") if p.is_file()]


def _files_containing(root: Path, secret: str):
    needles = [secret.encode("utf-8"), secret.encode("utf-16-le"),
               base64.b64encode(secret.encode("utf-8"))]
    return [str(p.relative_to(root)) for p in _every_file(root)
            if any(n in p.read_bytes() for n in needles)]


# ── The store ────────────────────────────────────────────────────────────

def test_the_store_file_is_the_one_in_appdata(profile):
    assert profile.store.path == paths.settings_root() / "api-keys.locked.json"
    assert profile.store.uses_file and profile.store.persistent


def test_a_key_round_trips_and_is_not_in_the_file_in_clear_text(profile):
    profile.store.set("claude", CLAUDE)
    assert profile.store.get("claude") == CLAUDE
    assert profile.store.status("claude") == keystore.PRESENT
    data = json.loads(profile.store.path.read_text(encoding="utf-8"))
    assert data["format"] == "localizelarge-api-keys" and data["formatVersion"] == 1
    assert list(data["keys"]) == ["claude"]
    assert _files_containing(profile.root, CLAUDE) == []


def test_names_and_aliases(profile):
    profile.store.set("anthropic", CLAUDE)
    profile.store.set("google", GEMINI)
    assert profile.store.all() == {"claude": CLAUDE, "gemini": GEMINI}
    assert keystore.canonical("Claude") == "claude"
    assert keystore.canonical("ollama") is None
    assert keystore.canonical("mistral") is None


@pytest.mark.parametrize("name", ["mistral", "deepl", "ollama", "openrouter", ""])
def test_a_provider_without_a_key_here_is_refused(profile, name):
    with pytest.raises(keystore.KeyStoreError):
        profile.store.set(name, "some-key-value-0123456789")
    assert profile.store.get(name) is None


def test_an_empty_value_removes_the_key(profile):
    profile.store.set("openai", OPENAI)
    profile.store.set("openai", "")
    assert profile.store.get("openai") is None
    assert profile.store.status("openai") == keystore.ABSENT
    assert "openai" not in json.loads(profile.store.path.read_text(encoding="utf-8"))["keys"]


def test_a_key_locked_under_another_account_is_unreadable_not_absent(profile):
    if sys.platform == "win32":
        # Stand in for "another account": a blob DPAPI cannot unlock.
        profile.store.set("claude", CLAUDE)
        data = json.loads(profile.store.path.read_text(encoding="utf-8"))
        data["keys"]["claude"] = base64.b64encode(b"not a DPAPI blob at all").decode("ascii")
        profile.store.path.write_text(json.dumps(data), encoding="utf-8")
        other = profile.store
    else:
        profile.store.set("claude", CLAUDE)
        other = keystore.KeyStore(path=profile.store.path, backend=FakeAccountLock("mallory-other"))
    assert other.status("claude") == keystore.UNREADABLE
    assert other.get("claude") is None
    assert other.unreadable() == ["claude"]


def test_a_damaged_file_reads_as_empty_and_can_be_written_again(profile):
    profile.store.path.write_text("{ this is not json", encoding="utf-8")
    assert profile.store.all() == {}
    profile.store.set("gemini", GEMINI)
    assert profile.store.get("gemini") == GEMINI


def test_memory_only_store_writes_nothing(tmp_path):
    store = keystore.KeyStore(path=tmp_path / "api-keys.locked.json", backend=keystore.MemoryBackend())
    store.set("claude", CLAUDE)
    assert store.get("claude") == CLAUDE
    assert not store.persistent
    assert _every_file(tmp_path) == []


def test_mask_shows_only_the_last_four_characters():
    assert keystore.mask(CLAUDE) == "••••••••" + CLAUDE[-4:]
    assert CLAUDE[:20] not in keystore.mask(CLAUDE)
    assert keystore.mask("short") == "•••••"
    assert keystore.mask("") == ""


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is Windows only")
def test_dpapi_blob_differs_each_time_and_needs_the_entropy(profile):
    backend = keystore.DpapiBackend()
    first, second = backend.lock(CLAUDE), backend.lock(CLAUDE)
    assert first != second
    assert backend.unlock(first) == CLAUDE == backend.unlock(second)
    assert CLAUDE.encode() not in base64.b64decode(first)


# ── The app's reader and writer ──────────────────────────────────────────

def test_the_reader_returns_stored_keys_and_the_ollama_address(profile):
    profile.settings.write_text(json.dumps({"api_keys": {"ollama_endpoint": OLLAMA}}), encoding="utf-8")
    assert llm_clients.save_api_key("claude", CLAUDE) is True
    assert llm_clients.save_api_key("ollama_endpoint", OLLAMA) is True      # not a key: nothing stored
    keys = llm_clients.load_api_keys(str(profile.settings))
    assert keys == {"claude": CLAUDE, "ollama_endpoint": OLLAMA}
    assert profile.store.all() == {"claude": CLAUDE}


def test_a_key_in_settings_json_is_never_read_as_a_key(profile):
    profile.settings.write_text(json.dumps({"api_keys": {"openai": OPENAI}}), encoding="utf-8")
    assert "openai" not in llm_clients.load_api_keys(str(profile.settings))


def test_missing_and_unreadable_keys_are_explained(profile):
    assert llm_clients.api_key_problem("claude") == "No API key set for Claude. Add one in Settings → AI Settings."
    assert llm_clients.api_key_problem("ollama") is None
    llm_clients.save_api_key("claude", CLAUDE)
    assert llm_clients.api_key_problem("claude") is None
    assert llm_clients.unreadable_key_notes() == {}


def test_start_up_moves_clear_text_keys_out_of_settings_json(profile):
    profile.settings.write_text(json.dumps({
        "api_keys": {"claude": CLAUDE, "google": GEMINI, "deepl": "deepl-KEY-PROJ001-zzzz",
                     "mistral": "mistral-KEY-PROJ001-yyyy", "ollama_endpoint": OLLAMA},
        "ui": {"llm_settings": {"provider": "claude", "custom_openai_profiles": [
            {"name": "proxy", "endpoint": "https://example.invalid/v1", "api_key": "custom-KEY-PROJ001-xxxx"}]}},
    }), encoding="utf-8")
    prepared = llm_clients.prepare_api_keys(str(profile.settings), join=True)
    assert prepared.notices == ["2 API key(s) were moved out of the settings file into the locked key store."]
    assert prepared.keychain_missing is None
    assert profile.store.all() == {"claude": CLAUDE, "gemini": GEMINI}
    after = json.loads(profile.settings.read_text(encoding="utf-8"))
    assert after["api_keys"] == {"ollama_endpoint": OLLAMA}
    assert after["ui"]["llm_settings"]["custom_openai_profiles"] == []
    for secret in (CLAUDE, GEMINI, "deepl-KEY-PROJ001-zzzz", "mistral-KEY-PROJ001-yyyy", "custom-KEY-PROJ001-xxxx"):
        assert _files_containing(profile.root, secret) == [], secret
    # A second start has nothing to do.
    assert llm_clients.prepare_api_keys(str(profile.settings), join=False).notices == []


def test_a_stored_key_is_not_replaced_by_an_old_one_from_settings(profile):
    profile.store.set("claude", CLAUDE)
    profile.settings.write_text(json.dumps({"api_keys": {"claude": "sk-ant-OLD-PROJ001-0000"}}), encoding="utf-8")
    llm_clients.prepare_api_keys(str(profile.settings), join=True)
    assert profile.store.get("claude") == CLAUDE
    assert json.loads(profile.settings.read_text(encoding="utf-8"))["api_keys"] == {}


def test_without_a_secure_store_the_user_is_told_and_nothing_is_written(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "Roaming"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    keystore.set_default_store(keystore.KeyStore(backend=keystore.MemoryBackend()))
    try:
        prepared = llm_clients.prepare_api_keys(str(tmp_path / "settings.json"), join=True)
        assert "not saved" in prepared.keychain_missing
        llm_clients.save_api_key("claude", CLAUDE)
        assert _files_containing(tmp_path, CLAUDE) == []
    finally:
        keystore.set_default_store(None)


# ── The key-leak test: save keys through the app, then search every file ──

@pytest.fixture(scope="module")
def S():
    from PyQt6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    saved = sys.stdout, sys.stderr
    import Supervertaler   # re-wraps stdout/stderr on Windows at import
    S._wrappers = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = saved
    return Supervertaler


def _window(S, logs):
    """A stand-in main window with the real settings and key methods bound to it."""
    w = types.SimpleNamespace(user_data_path=paths.settings_root(), log=logs.append)
    for name in ("_get_settings_dir", "_get_unified_settings_path", "_load_unified_settings",
                 "_save_unified_settings", "_load_settings_section", "_save_settings_section",
                 "save_api_keys", "load_api_keys", "save_llm_settings", "load_llm_settings",
                 "_save_api_keys_from_ui"):
        setattr(w, name, types.MethodType(getattr(S.SupervertalerQt, name), w))
    return w


def test_keys_saved_through_the_app_appear_in_no_file_in_clear_text(S, profile, qtbot):
    from PyQt6.QtWidgets import QLineEdit

    logs = []
    w = _window(S, logs)
    w._api_key_inputs = {}
    for name, value in (("claude", CLAUDE), ("openai", OPENAI), ("gemini", GEMINI), ("ollama_endpoint", OLLAMA)):
        box = QLineEdit()
        qtbot.addWidget(box)
        box.setText(value)
        w._api_key_inputs[name] = box

    w._save_api_keys_from_ui()                                   # the Settings page's Save
    w.save_api_keys({"claude": CLAUDE, "openai": OPENAI, "ollama_endpoint": OLLAMA})   # a careless caller
    settings = w.load_llm_settings()
    settings["custom_openai_profiles"] = [{"name": "p", "endpoint": "https://example.invalid", "api_key": OPENAI}]
    w.save_llm_settings(settings)
    (paths.logs_dir() / "localizelarge.log").write_text("\n".join(logs), encoding="utf-8")

    # The keys work…
    assert w.load_api_keys() == {"claude": CLAUDE, "openai": OPENAI, "gemini": GEMINI, "ollama_endpoint": OLLAMA}
    # …the settings file holds only the Ollama address…
    saved = json.loads(paths.settings_file().read_text(encoding="utf-8"))
    assert saved["api_keys"] == {"ollama_endpoint": OLLAMA}
    assert saved["ui"]["llm_settings"]["custom_openai_profiles"] == []
    # …and no file under either data folder contains any key.
    assert len(_every_file(profile.root)) >= 2
    for secret in (CLAUDE, OPENAI, GEMINI):
        assert _files_containing(profile.root, secret) == [], secret
    # The only file that holds keys at all is the locked one.
    assert profile.store.path.is_file()
    assert sorted(json.loads(profile.store.path.read_text(encoding="utf-8"))["keys"]) == ["claude", "gemini", "openai"]
