"""Phase 1: the Localize Large identity – data paths, project format, About text."""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from localizelarge import about, paths, project_format  # noqa: E402


# ── Data paths ───────────────────────────────────────────────────────────

@pytest.fixture
def windows_profile(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    return tmp_path


def test_windows_settings_live_in_appdata(windows_profile):
    root = windows_profile / "Roaming" / "LocalizeLarge"
    assert paths.settings_root() == root
    assert paths.api_keys_file() == root / "api-keys.locked.json"
    assert paths.packs_dir() == root / "packs"
    assert paths.settings_file().is_relative_to(root)
    assert paths.prompt_library_dir().is_relative_to(root)


def test_windows_databases_logs_and_caches_live_in_localappdata(windows_profile):
    root = windows_profile / "Local" / "LocalizeLarge"
    assert paths.local_root() == root
    for path in (paths.database_file(), paths.logs_dir(), paths.crash_log_file(), paths.cache_dir()):
        assert path.is_relative_to(root)
    assert paths.database_file().name == "localizelarge.db"


def test_other_systems_follow_xdg(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    assert paths.settings_root() == tmp_path / "cfg" / "LocalizeLarge"
    assert paths.local_root() == tmp_path / "data" / "LocalizeLarge"


def test_no_path_names_a_supervertaler_folder(windows_profile):
    every_path = [
        paths.settings_root(), paths.local_root(), paths.settings_dir(), paths.settings_file(),
        paths.api_keys_file(), paths.prompt_library_dir(), paths.packs_dir(),
        paths.pricing_override_file(), paths.database_dir(), paths.database_file(),
        paths.logs_dir(), paths.crash_log_file(), paths.cache_dir(),
    ]
    for path in every_path:
        assert "supervertaler" not in str(path).lower()


def test_ensure_roots_creates_only_localizelarge_folders(windows_profile):
    paths.ensure_roots()
    assert sorted(p.name for p in (windows_profile / "Roaming").iterdir()) == ["LocalizeLarge"]
    assert sorted(p.name for p in (windows_profile / "Local").iterdir()) == ["LocalizeLarge"]
    assert paths.settings_dir().is_dir()
    assert paths.database_dir().is_dir()
    assert paths.logs_dir().is_dir()


def test_main_module_data_root_is_the_settings_root(tmp_path, monkeypatch):
    """The monolith's old path functions answer from localizelarge.paths."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "cfg"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "data"))
    source = Path(__file__).resolve().parent.parent / "Supervertaler.py"
    text = source.read_text(encoding="utf-8")
    start = text.index("from localizelarge import paths as _ll_paths")
    end = text.index("import threading\n", start)
    namespace = {"Path": Path, "Optional": __import__("typing").Optional}
    exec(text[start:end], namespace)
    assert namespace["get_user_data_path"]() == paths.settings_root()
    assert namespace["get_default_user_data_path"]() == paths.settings_root()
    assert namespace["needs_first_run_data_dialog"]() is False
    assert namespace["load_user_data_path_from_config"]() is None
    assert not (tmp_path / "cfg" / "LocalizeLarge" / "config.json").exists()


# ── Project format ───────────────────────────────────────────────────────

def test_stamp_puts_the_format_keys_first_and_keeps_the_data():
    stamped = project_format.stamp({"name": "Demo", "segments": [{"id": 1}]})
    assert list(stamped)[:2] == ["format", "formatVersion"]
    assert stamped["format"] == "localizelarge-project"
    assert stamped["formatVersion"] == 1
    assert stamped["name"] == "Demo"
    assert stamped["segments"] == [{"id": 1}]
    json.dumps(stamped)


def test_stamp_overrides_a_stale_format_value():
    stamped = project_format.stamp({"format": "something-else", "formatVersion": 99, "name": "x"})
    assert stamped["format"] == "localizelarge-project"
    assert stamped["formatVersion"] == 1


def test_an_svproj_is_saved_as_llproj_beside_it(tmp_path):
    old = tmp_path / "Job" / "Job.svproj"
    assert project_format.save_path_for(str(old)) == str(tmp_path / "Job" / "Job.llproj")
    assert project_format.is_legacy(str(old))
    assert project_format.is_legacy(str(tmp_path / "JOB.SVPROJ"))


def test_an_llproj_keeps_its_path(tmp_path):
    new = str(tmp_path / "Job.llproj")
    assert project_format.save_path_for(new) == new
    assert not project_format.is_legacy(new)


def test_both_extensions_count_as_project_files():
    assert paths.is_project_file("a.llproj")
    assert paths.is_project_file("a.svproj")
    assert not paths.is_project_file("a.docx")


def test_a_newer_project_format_is_refused():
    with pytest.raises(ValueError, match="newer version"):
        project_format.check_version({"format": "localizelarge-project", "formatVersion": 2})


def test_current_and_legacy_projects_pass_the_version_check():
    project_format.check_version({"format": "localizelarge-project", "formatVersion": 1})
    project_format.check_version({"name": "an old svproj with no format key"})


def test_open_filter_offers_both_extensions_and_save_filter_only_llproj():
    assert "*.llproj" in project_format.FILE_DIALOG_FILTER_OPEN
    assert "*.svproj" in project_format.FILE_DIALOG_FILTER_OPEN
    assert "*.llproj" in project_format.FILE_DIALOG_FILTER_SAVE
    assert "svproj" not in project_format.FILE_DIALOG_FILTER_SAVE


# ── About ────────────────────────────────────────────────────────────────

def test_about_text_carries_the_attribution_and_contacts():
    html = about.about_html("1.0.0")
    assert "Localize Large 1.0.0" in html
    assert "Based on Supervertaler Workbench 1.10.376 by Michael Beijer (MIT License)" in html
    assert "localizelarge.com" in html
    assert "contact@localizelarge.com" in html
    assert "GPL-3.0-or-later" in html


def test_the_licenses_file_exists_in_the_source_tree():
    assert about.licenses_file().name == "THIRD_PARTY_LICENSES.md"
    assert about.licenses_file().is_file()


def test_notice_keeps_the_mit_text_and_copyright():
    notice = (Path(__file__).resolve().parent.parent / "NOTICE").read_text(encoding="utf-8")
    assert "Localize Large is based on Supervertaler Workbench by Michael Beijer (MIT License)." in notice
    assert "Copyright (c) 2025 Michael Beijer" in notice
    assert "Permission is hereby granted, free of charge" in notice


def test_the_about_dialog_shows_the_text_and_a_licenses_button(qtbot, monkeypatch):
    from PyQt6.QtWidgets import QDialog, QLabel, QPushButton

    shown = {}

    def fake_exec(self):
        shown["title"] = self.windowTitle()
        shown["text"] = self.findChild(QLabel, "aboutText").text()
        shown["licenses"] = self.findChild(QPushButton, "aboutLicensesButton") is not None
        return 0

    monkeypatch.setattr(QDialog, "exec", fake_exec)
    about.show_about_dialog(None, "1.0.0")
    assert shown["title"] == "About Localize Large"
    assert "Michael Beijer" in shown["text"]
    assert shown["licenses"] is True
