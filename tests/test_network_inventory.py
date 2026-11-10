"""Phase 3: every web host named in the source is declared.

Scans the Python and Java source for ``http://`` and ``https://`` hosts. Each
one must be either a destination in ``docs/security/network-connections.json``
or on the short list below of addresses the app never fetches (XML namespaces,
links opened in the user's browser, placeholders). A new host makes this test
fail until it is declared.
"""
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
INVENTORY = ROOT / "docs" / "security" / "network-connections.json"

SOURCE_GLOBS = (
    "Supervertaler.py",
    "modules/**/*.py",
    "localizelarge/**/*.py",
    "localizelarge/**/*.json",
    "scripts/**/*.py",
    "tools/**/*.py",
    "okapi-sidecar/src/main/**/*.java",
    "okapi-sidecar/src/main/resources/**/*",
)

URL = re.compile(r"https?://([A-Za-z0-9.\-]+|\[[0-9a-fA-F:]+\])")

# Hosts the app connects to. Each must appear in the inventory.
CONNECTED = {
    "api.anthropic.com": "claude",
    "api.openai.com": "openai",
    "generativelanguage.googleapis.com": "gemini",
    "localhost": "ollama",            # also the example LanguageTool address and the sidecar
    "127.0.0.1": "okapi-sidecar",
}

# Hosts that appear in the source but are never fetched by the app.
NEVER_FETCHED = {
    # XML namespaces and schema identifiers: names, not addresses that are opened.
    "schemas.openxmlformats.org": "XML namespace (Office Open XML)",
    "www.w3.org": "XML namespace (W3C)",
    "themqm.org": "where the MQM typology and scoring models are published (credit and citation)",
    "creativecommons.org": "the address of the CC BY 4.0 licence of the MQM typology",
    "json-schema.org": "the name of the JSON Schema dialect in issues.schema.json; validated offline",
    "www.lisa.org": "XML namespace (SRX, TMX)",
    "sdl.com": "XML namespace (Trados SDLXLIFF)",
    # Links shown to the user and opened only in their own browser, on a click.
    "localizelarge.com": "the product's website, help and download page",
    "ollama.com": "where to get Ollama (opened in the browser from the Ollama setup dialog)",
    "github.com": "links to spelling dictionaries and libraries in Settings → Spellcheck",
    "hunspell.memoq.com": "link to spelling dictionaries in Settings → Spellcheck",
    "extensions.libreoffice.org": "link to spelling dictionaries in Settings → Spellcheck",
    "hunspell.github.io": "link to the Hunspell project in Settings → Spellcheck",
    # Placeholders and examples in comments, tooltips and docstrings.
    "example.com": "placeholder",
    "example.invalid": "placeholder",
    "user": "placeholder in a proxy example (http://user:pass@host)",
}


def _hosts_in_source():
    found = {}
    for pattern in SOURCE_GLOBS:
        for path in ROOT.glob(pattern):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for match in URL.finditer(text):
                host = match.group(1).lower().strip(".")
                if host:
                    found.setdefault(host, set()).add(str(path.relative_to(ROOT)))
    return found


@pytest.fixture(scope="module")
def inventory():
    return json.loads(INVENTORY.read_text(encoding="utf-8"))


def test_the_inventory_has_the_websites_fields(inventory):
    fields = {"id", "name", "destination", "when", "whatIsSent", "defaultOn", "howToTurnOff",
              "inShippedApp", "confirmed"}
    for row in inventory:
        assert set(row) == fields, row.get("id")
        assert re.fullmatch(r"[a-z0-9-]+", row["id"])
        for text_field in ("name", "destination", "when", "whatIsSent", "howToTurnOff"):
            assert isinstance(row[text_field], str) and row[text_field].strip(), (row["id"], text_field)
        assert isinstance(row["inShippedApp"], bool) and isinstance(row["confirmed"], bool)
        assert row["defaultOn"] in (True, False, None)


def test_the_inventory_lists_exactly_the_expected_connections(inventory):
    assert [row["id"] for row in inventory] == [
        "claude", "openai", "gemini", "ollama", "languagetool", "okapi-sidecar"]


def test_only_the_local_file_service_is_on_by_default(inventory):
    assert [row["id"] for row in inventory if row["defaultOn"]] == ["okapi-sidecar"]
    sidecar = next(row for row in inventory if row["id"] == "okapi-sidecar")
    assert "127.0.0.1" in sidecar["destination"]


def test_every_connected_host_is_in_the_inventory(inventory):
    by_id = {row["id"]: row for row in inventory}
    for host, row_id in CONNECTED.items():
        assert row_id in by_id, host
        assert host in by_id[row_id]["destination"], (host, by_id[row_id]["destination"])


def test_no_undeclared_host_appears_in_the_source():
    undeclared = {host: sorted(files) for host, files in _hosts_in_source().items()
                  if host not in CONNECTED and host not in NEVER_FETCHED}
    assert undeclared == {}, (
        "These hosts are in the source but not declared. Add a row to "
        "docs/security/network-connections.json (a real connection) or to NEVER_FETCHED "
        f"in this test (never fetched): {undeclared}")


def test_services_removed_from_v1_are_not_named_in_the_source():
    gone = ("api.languagetool.org", "api.github.com", "workers.dev", "openrouter.ai", "api.mistral.ai",
            "api.deepseek.com", "api.mymemory.translated.net", "api-free.deepl.com", "api.deepl.com",
            "translation.googleapis.com", "api.cognitive.microsofttranslator.com", "api.modernmt.com",
            "supervertaler.com")
    hosts = _hosts_in_source()
    present = {host: sorted(files) for host, files in hosts.items()
               if any(host == g or host.endswith("." + g) for g in gone)}
    assert present == {}


def test_the_guards_cloud_hosts_match_the_inventory(inventory):
    from localizelarge.security import net
    by_id = {row["id"]: row for row in inventory}
    for provider, host in net.CLOUD_HOSTS.items():
        assert host in by_id[provider]["destination"]
    assert set(net.CLOUD_HOSTS) == {"claude", "openai", "gemini"}
