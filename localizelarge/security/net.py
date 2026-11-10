"""The only place that creates HTTP clients for AI providers and LanguageTool.

Every request the app sends goes to a host on a short list:

* the three cloud AI providers, at fixed addresses;
* the Ollama address the user configured (``http://localhost:11434`` by default);
* a LanguageTool server address, only if the user entered one.

A request to any other host is refused before it leaves the computer. Each
request is logged with its purpose and host name. Bodies, addresses beyond the
host, headers and keys are never logged.

The Okapi sidecar is not handled here: it is a loopback-only service with its
own client (``modules/okapi_sidecar.py``).
"""
from __future__ import annotations

import ipaddress
import logging
import os
import threading
from typing import Dict, Optional
from urllib.parse import urlsplit

logger = logging.getLogger("localizelarge.net")

#: Fixed addresses of the cloud providers. Not configurable.
CLOUD_HOSTS: Dict[str, str] = {
    "claude": "api.anthropic.com",
    "openai": "api.openai.com",
    "gemini": "generativelanguage.googleapis.com",
}
PROVIDER_LABELS: Dict[str, str] = {
    "claude": "Anthropic (Claude)",
    "openai": "OpenAI",
    "gemini": "Google (Gemini)",
    "ollama": "Ollama",
}
DEFAULT_OLLAMA_ENDPOINT = "http://localhost:11434"

PURPOSES = ("claude", "openai", "gemini", "ollama", "languagetool")


class HostNotAllowed(Exception):
    """A request was about to go to a host that is not configured."""

    def __init__(self, purpose: str, host: str):
        self.purpose = purpose
        self.host = host
        super().__init__(
            f"Blocked: {PROVIDER_LABELS.get(purpose, purpose)} request to {host or 'an unknown host'}, "
            "which is not a configured address.")


# ── Configuration ────────────────────────────────────────────────────────

_lock = threading.Lock()
_ollama_endpoint: Optional[str] = None
_languagetool_url: Optional[str] = None


def configure(*, ollama_endpoint: Optional[str] = None, languagetool_url: Optional[str] = None) -> None:
    """Set the user-configured addresses. ``""`` clears one; ``None`` leaves it."""
    global _ollama_endpoint, _languagetool_url
    with _lock:
        if ollama_endpoint is not None:
            _ollama_endpoint = ollama_endpoint.strip() or None
        if languagetool_url is not None:
            _languagetool_url = languagetool_url.strip() or None


def reset() -> None:
    """Forget the configured addresses (tests)."""
    global _ollama_endpoint, _languagetool_url
    with _lock:
        _ollama_endpoint = None
        _languagetool_url = None


def ollama_endpoint() -> str:
    """The Ollama address in use: the configured one, else the default."""
    with _lock:
        configured = _ollama_endpoint
    endpoint = configured or os.environ.get("OLLAMA_ENDPOINT") or DEFAULT_OLLAMA_ENDPOINT
    endpoint = endpoint.strip().rstrip("/")
    for suffix in ("/api", "/v1"):
        if endpoint.endswith(suffix):
            endpoint = endpoint[: -len(suffix)]
    if "://" not in endpoint:
        endpoint = "http://" + endpoint
    return endpoint


def languagetool_url() -> Optional[str]:
    """The LanguageTool server the user entered, or None (the default: off)."""
    with _lock:
        return _languagetool_url


# ── Hosts ────────────────────────────────────────────────────────────────

def host_of(url: str) -> str:
    """The host name of a URL, lower case, without port or brackets."""
    try:
        return (urlsplit(url if "://" in url else "//" + url).hostname or "").lower()
    except ValueError:
        return ""


def is_local_host(host: str) -> bool:
    """True for this computer: ``localhost`` and loopback addresses."""
    host = (host or "").strip().lower().strip("[]")
    if host in ("localhost", "localhost."):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def allowed_host(purpose: str) -> str:
    """The one host a purpose may contact, or ``""`` when none is configured."""
    if purpose in CLOUD_HOSTS:
        return CLOUD_HOSTS[purpose]
    if purpose == "ollama":
        return host_of(ollama_endpoint())
    if purpose == "languagetool":
        url = languagetool_url()
        return host_of(url) if url else ""
    return ""


def check(url: str, purpose: str) -> str:
    """Allow or refuse one request. Returns the host; raises HostNotAllowed.

    Logs the purpose and the host name, and nothing else about the request.
    """
    host = host_of(url)
    wanted = allowed_host(purpose)
    if not host or not wanted or host != wanted:
        logger.warning("[net] BLOCKED %s -> %s", purpose, host or "(no host)")
        raise HostNotAllowed(purpose, host)
    if purpose in CLOUD_HOSTS and not url.lower().startswith("https://"):
        logger.warning("[net] BLOCKED %s -> %s (not HTTPS)", purpose, host)
        raise HostNotAllowed(purpose, host)
    logger.info("[net] %s -> %s", purpose, host)
    return host


# ── Clients ──────────────────────────────────────────────────────────────

def session(purpose: str):
    """A ``requests`` session that can reach only the host of ``purpose``.

    Every request, and every redirect hop, is checked. Requests to this
    computer (Ollama on localhost, a local LanguageTool) never use a proxy.
    """
    import requests

    if purpose not in PURPOSES:
        raise ValueError(f"unknown purpose: {purpose}")

    class _GuardedSession(requests.Session):
        def send(self, request, **kwargs):
            check(request.url, purpose)
            return super().send(request, **kwargs)

    guarded = _GuardedSession()
    if is_local_host(allowed_host(purpose)):
        guarded.trust_env = False
    return guarded


def httpx_client(purpose: str, proxy: Optional[str] = None, timeout: Optional[float] = None):
    """An ``httpx`` client for a provider SDK that can reach only that provider.

    Passed to the OpenAI and Anthropic SDKs as ``http_client``, so the SDK
    cannot be pointed at another address by a setting or an environment
    variable.
    """
    import httpx

    if purpose not in PURPOSES:
        raise ValueError(f"unknown purpose: {purpose}")

    def _on_request(request):
        check(str(request.url), purpose)

    kwargs = {"event_hooks": {"request": [_on_request]}, "follow_redirects": False}
    if timeout is not None:
        kwargs["timeout"] = timeout
    if proxy:
        kwargs["proxy"] = proxy
    return httpx.Client(**kwargs)


def provider_base_url(purpose: str) -> str:
    """The fixed HTTPS address of a cloud provider."""
    return f"https://{CLOUD_HOSTS[purpose]}"


# ── Where text goes ──────────────────────────────────────────────────────

def text_destination(provider: Optional[str]) -> Optional[str]:
    """Who receives text when ``provider`` translates: a name, or None when the
    text stays on this computer (no provider, or Ollama on a local address)."""
    provider = (provider or "").strip().lower()
    if not provider:
        return None
    if provider == "ollama":
        host = host_of(ollama_endpoint())
        return None if is_local_host(host) else f"Ollama at {host}"
    return PROVIDER_LABELS.get(provider, provider)


def where_text_goes(provider: Optional[str]) -> str:
    """The sentence shown in the status bar, AI settings and the batch dialog."""
    destination = text_destination(provider)
    if destination is None:
        return "Text stays on this computer"
    return f"Text is sent to {destination}"
