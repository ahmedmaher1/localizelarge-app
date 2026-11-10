"""Start the real app on an empty profile, close it, and look at what it left behind.

Checks the Phase 1 and Phase 2 promises that can be seen from outside:

* it starts and exits with code 0, without a crash;
* it creates its own two folders and nothing named after Supervertaler;
* it leaves no Java (sidecar) process running;
* it never imports a package that was removed from v1.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

REMOVED_PACKAGES = (
    "PyQt6.QtWebEngineWidgets", "PyQt6.QtWebEngineCore", "fitz", "vosk", "sounddevice",
    "boto3", "deepl", "pynput", "ahk",
)


@pytest.fixture(scope="module")
def launch(tmp_path_factory):
    profile = tmp_path_factory.mktemp("profile")
    env = dict(os.environ)
    env.update({
        "HOME": str(profile / "home"),
        "USERPROFILE": str(profile / "home"),
        "APPDATA": str(profile / "Roaming"),
        "LOCALAPPDATA": str(profile / "Local"),
        "XDG_CONFIG_HOME": str(profile / "Roaming"),
        "XDG_DATA_HOME": str(profile / "Local"),
        "XDG_CACHE_HOME": str(profile / "Cache"),
        "QT_QPA_PLATFORM": "offscreen",
        "LOCALIZELARGE_SMOKE_EXIT_MS": "3000",
        "PYTHONIOENCODING": "utf-8",
    })
    for name in ("home", "Roaming", "Local", "Cache"):
        (profile / name).mkdir()
    # Report, at exit, which removed packages ended up imported.
    probe = (
        "import atexit, runpy, sys\n"
        f"removed = {REMOVED_PACKAGES!r}\n"
        "atexit.register(lambda: print('IMPORTED_REMOVED=' + ','.join(m for m in removed if m in sys.modules)))\n"
        f"sys.argv = [{str(ROOT / 'Supervertaler.py')!r}]\n"
        f"runpy.run_path({str(ROOT / 'Supervertaler.py')!r}, run_name='__main__')\n"
    )
    result = subprocess.run(
        [sys.executable, "-X", "faulthandler", "-c", probe],
        cwd=str(ROOT), env=env, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=180,
    )
    return profile, result


def _names_under(folder: Path):
    return sorted(p.name for p in folder.iterdir())


def test_the_app_starts_and_exits_cleanly(launch):
    _, result = launch
    tail = (result.stdout + result.stderr)[-2000:]
    assert result.returncode == 0, tail
    assert "Fatal Python error" not in result.stderr, tail
    assert "Traceback (most recent call last)" not in result.stderr, tail


def test_it_creates_only_its_own_two_folders(launch):
    profile, _ = launch
    assert _names_under(profile / "Roaming") == ["LocalizeLarge"]
    assert _names_under(profile / "Local") == ["LocalizeLarge"]
    assert _names_under(profile / "home") == []


def test_nothing_it_wrote_is_named_after_supervertaler(launch):
    profile, _ = launch
    offenders = [str(p.relative_to(profile)) for p in profile.rglob("*") if "supervertaler" in p.name.lower()]
    assert offenders == []


def test_settings_and_data_land_in_the_right_root(launch):
    profile, _ = launch
    settings_root = profile / "Roaming" / "LocalizeLarge"
    local_root = profile / "Local" / "LocalizeLarge"
    assert (local_root / "resources" / "localizelarge.db").is_file()
    assert (local_root / "logs").is_dir()
    assert not list(settings_root.rglob("*.db"))
    assert not list(settings_root.rglob("*.log"))


def test_no_removed_package_is_imported(launch):
    _, result = launch
    lines = [line for line in result.stdout.splitlines() if line.startswith("IMPORTED_REMOVED=")]
    assert lines, result.stdout[-1000:]
    assert lines[-1] == "IMPORTED_REMOVED="


def test_no_java_process_is_left_running(launch):
    psutil = pytest.importorskip("psutil")
    profile, _ = launch
    left = []
    for proc in psutil.process_iter(["name", "cmdline"]):
        try:
            cmdline = " ".join(proc.info.get("cmdline") or [])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if "okapi-sidecar" in cmdline and "java" in (proc.info.get("name") or "").lower():
            left.append(cmdline[:120])
    assert left == []
