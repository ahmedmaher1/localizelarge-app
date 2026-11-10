"""Phase 3: the Okapi sidecar is reachable only by the app that started it.

Needs the built sidecar JAR (okapi-sidecar/dist/okapi-sidecar.jar) and Java;
skipped otherwise.
"""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

requests = pytest.importorskip("requests")
psutil = pytest.importorskip("psutil")
docx = pytest.importorskip("docx")

from modules.okapi_sidecar import OkapiSidecar  # noqa: E402


def _http():
    session = requests.Session()
    session.trust_env = False
    return session


@pytest.fixture(scope="module")
def sidecar():
    sc = OkapiSidecar()
    if not sc.is_installed() or sc._find_java() is None:
        pytest.skip("Okapi sidecar JAR or Java not available")
    if not sc.start():
        pytest.skip("Okapi sidecar could not be started")
    try:
        if sc.get_version() != OkapiSidecar.EXPECTED_VERSION:
            pytest.skip(f"sidecar JAR is v{sc.get_version()}, client expects "
                        f"v{OkapiSidecar.EXPECTED_VERSION}: rebuild it")
        yield sc
    finally:
        sc.stop()


@pytest.fixture
def sample_docx(tmp_path):
    path = tmp_path / "sample.docx"
    document = docx.Document()
    document.add_paragraph("Hello world.")
    document.save(str(path))
    return path


def test_it_listens_on_the_loopback_address_only(sidecar):
    listening = [c for c in psutil.Process(sidecar._process.pid).net_connections(kind="inet")
                 if c.status == psutil.CONN_LISTEN]
    assert listening, "the sidecar is not listening at all"
    addresses = {c.laddr.ip for c in listening}
    # Java may show the IPv4 loopback address in its IPv6-mapped form.
    assert addresses <= {"127.0.0.1", "::ffff:127.0.0.1"}, addresses
    assert {c.laddr.port for c in listening} == {sidecar.port}


def test_the_port_is_chosen_per_session_not_fixed(sidecar):
    assert sidecar.port != 8090
    assert 1024 < sidecar.port < 65536
    assert sidecar.base_url == f"http://127.0.0.1:{sidecar.port}"


def test_health_answers_without_a_token_and_names_the_service(sidecar):
    reply = _http().get(f"{sidecar.base_url}/health", timeout=5)
    assert reply.status_code == 200
    body = reply.json()
    assert body["service"] == "localizelarge-okapi-sidecar"
    assert body["version"] == OkapiSidecar.EXPECTED_VERSION


@pytest.mark.parametrize("headers", [
    {},
    {"X-LL-Token": "wrong-token-wrong-token-wrong-token-wrong"},
    {"X-LL-Token": ""},
])
def test_every_other_endpoint_refuses_a_missing_or_wrong_token(sidecar, headers, sample_docx):
    http = _http()
    assert http.get(f"{sidecar.base_url}/filters", headers=headers, timeout=5).status_code == 401
    with open(sample_docx, "rb") as handle:
        reply = http.post(f"{sidecar.base_url}/extract", headers=headers, timeout=20,
                          files={"file": ("sample.docx", handle)},
                          data={"source_lang": "en", "target_lang": "ar"})
    assert reply.status_code == 401
    assert http.post(f"{sidecar.base_url}/shutdown", headers=headers, timeout=5).status_code == 401
    assert sidecar.is_running(), "an unauthorised /shutdown stopped the sidecar"


def test_the_right_token_is_accepted(sidecar, sample_docx):
    headers = {OkapiSidecar.TOKEN_HEADER: sidecar._token}
    assert _http().get(f"{sidecar.base_url}/filters", headers=headers, timeout=5).status_code == 200
    result = sidecar.extract(str(sample_docx), source_lang="en", target_lang="ar")
    assert [seg["source"] for seg in result["segments"]] == ["Hello world."]


def test_the_token_is_long_random_and_not_on_the_command_line(sidecar):
    assert len(sidecar._token) >= 32
    cmdline = " ".join(psutil.Process(sidecar._process.pid).cmdline())
    assert sidecar._token not in cmdline


def test_no_cors_headers_are_sent(sidecar):
    headers = {"Origin": "http://localhost", OkapiSidecar.TOKEN_HEADER: sidecar._token}
    reply = _http().get(f"{sidecar.base_url}/filters", headers=headers, timeout=5)
    assert reply.status_code == 200
    assert not [h for h in reply.headers if h.lower().startswith("access-control-")]
    preflight = _http().options(f"{sidecar.base_url}/extract", timeout=5, headers={
        "Origin": "http://evil.example", "Access-Control-Request-Method": "POST"})
    assert not [h for h in preflight.headers if h.lower().startswith("access-control-")]


def test_an_upload_name_with_folders_stays_in_the_temporary_folder(sidecar, sample_docx):
    marker = f"ll-traversal-{os.getpid()}-{int(time.time())}.docx"
    escaped = Path(tempfile.gettempdir()) / marker
    headers = {OkapiSidecar.TOKEN_HEADER: sidecar._token}
    with open(sample_docx, "rb") as handle:
        reply = _http().post(f"{sidecar.base_url}/extract", headers=headers, timeout=30,
                             files={"file": (f"../{marker}", handle)},
                             data={"source_lang": "en", "target_lang": "ar"})
    assert reply.status_code == 200, reply.text[:300]
    assert reply.json()["segmentCount"] == 1
    assert not escaped.exists()


def test_temporary_files_are_deleted_after_each_request(sidecar, sample_docx):
    def leftovers():
        return {p.name for p in Path(tempfile.gettempdir()).glob("okapi-*")}

    before = leftovers()
    sidecar.extract(str(sample_docx), source_lang="en", target_lang="ar")
    assert leftovers() <= before


def _spawn(env_extra, port):
    sc = OkapiSidecar()
    env = dict(os.environ)
    env.pop(OkapiSidecar.TOKEN_ENV, None)
    env.update(env_extra)
    return subprocess.Popen(
        [str(sc._find_java()), "-jar", str(sc.sidecar_dir / "okapi-sidecar.jar"), f"--port={port}"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env,
        cwd=str(sc.sidecar_dir))


@pytest.mark.parametrize("env_extra", [{}, {"LL_SIDECAR_TOKEN": "too-short"}])
def test_it_refuses_to_start_without_a_proper_token(sidecar, env_extra):
    process = _spawn(env_extra, OkapiSidecar._free_port())
    try:
        assert process.wait(timeout=30) == 2
    finally:
        if process.poll() is None:
            process.kill()


def test_it_exits_when_the_app_that_started_it_goes_away(sidecar):
    port = OkapiSidecar._free_port()
    process = _spawn({"LL_SIDECAR_TOKEN": "t" * 43}, port)
    try:
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                if _http().get(f"http://127.0.0.1:{port}/health", timeout=1).status_code == 200:
                    break
            except requests.RequestException:
                time.sleep(0.2)
        else:
            pytest.fail("the second sidecar did not come up")
        process.stdin.close()          # what happens when the app dies
        assert process.wait(timeout=15) == 0
    finally:
        if process.poll() is None:
            process.kill()


def test_stopping_leaves_no_process_and_a_restart_gets_a_new_token():
    sc = OkapiSidecar()
    if not sc.is_installed() or sc._find_java() is None:
        pytest.skip("Okapi sidecar JAR or Java not available")
    assert sc.start()
    first_token, first_pid = sc._token, sc._process.pid
    sc.stop()
    assert not psutil.pid_exists(first_pid) or psutil.Process(first_pid).status() == psutil.STATUS_ZOMBIE
    assert not sc.is_running()
    assert sc.start()
    try:
        assert sc._token != first_token
        assert sc._process.pid != first_pid
    finally:
        sc.stop()
