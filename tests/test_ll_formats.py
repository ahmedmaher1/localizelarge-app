"""Phase 4: the file-format table (formats.json) as the app sees it."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from localizelarge import formats  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TABLE = ROOT / "okapi-sidecar" / "src" / "main" / "resources" / "formats.json"

V1_EXTENSIONS = {
    ".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp", ".html", ".htm", ".xlf", ".xliff",
    ".xlf2", ".po", ".idml", ".md", ".json", ".yaml", ".yml", ".properties", ".csv", ".txt",
    ".xml", ".vtt", ".srt",
}


def test_the_app_reads_the_same_table_as_the_sidecar():
    rows = json.loads(TABLE.read_text(encoding="utf-8"))["formats"]
    assert [f.config_id for f in formats.all_formats()] == [r["configId"] for r in rows]


def test_every_v1_format_can_be_imported():
    assert V1_EXTENSIONS <= formats.import_extensions()


def test_tmx_is_in_the_table_but_not_an_import_format():
    assert formats.format_for("memory.tmx").config_id == "okf_tmx"
    assert ".tmx" not in formats.import_extensions()


def test_lookup_ignores_case_and_unknown_files_give_none():
    assert formats.format_for("Report.DOCX").config_id == "okf_openxml"
    assert formats.format_for("notes.odt").config_id == "okf_openoffice"
    assert formats.format_for("picture.png") is None


def test_no_extension_is_listed_twice():
    seen = [ext for f in formats.all_formats() for ext in f.extensions]
    assert len(seen) == len(set(seen))


def test_dialog_filters_cover_every_import_format():
    filters = formats.dialog_filters()
    patterns = " ".join(pattern for _, pattern in filters)
    for ext in V1_EXTENSIONS:
        assert f"*{ext}" in patterns.split(), ext
    assert all(name for name, _ in filters)


def test_every_format_has_a_sample_file():
    fixtures = ROOT / "tests" / "fixtures" / "formats"
    for fmt in formats.import_formats():
        assert (fixtures / f"sample{fmt.extensions[0]}").is_file(), fmt.extensions[0]


def test_the_table_is_read_from_the_jar_when_there_is_no_source_tree(tmp_path, monkeypatch):
    import zipfile
    jar = tmp_path / "okapi-sidecar.jar"
    with zipfile.ZipFile(jar, "w") as archive:
        archive.write(TABLE, "formats.json")
    monkeypatch.setattr(formats, "_source_table", lambda: tmp_path / "missing.json")
    monkeypatch.setattr(formats, "_jar_candidates", lambda: [jar])
    formats.all_formats.cache_clear()
    try:
        assert ".docx" in formats.import_extensions()
    finally:
        formats.all_formats.cache_clear()
