"""Phase 4: glossary exchange. TBX-Basic in and out, XLSX and CSV in."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lxml import etree  # noqa: E402

from localizelarge.terms import store, tabular, tbx  # noqa: E402
from localizelarge.terms.model import Entry, Variant  # noqa: E402
from modules.database_manager import DatabaseManager  # noqa: E402
from modules.termbase_manager import TermbaseManager  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "terms"


@pytest.fixture
def termbases(tmp_path):
    db = DatabaseManager(db_path=str(tmp_path / "terms.db"), log_callback=lambda *_: None)
    db.connect()
    manager = TermbaseManager(db, lambda *_: None)
    yield manager
    db.close()


def as_tuples(entries):
    """Everything an entry holds, in a form that compares regardless of order."""
    return sorted(
        (e.source, e.target, bool(e.forbidden), e.part_of_speech, e.definition, e.notes, e.domain,
         tuple(sorted((v.text, v.forbidden) for v in e.source_variants)),
         tuple(sorted((v.text, v.forbidden) for v in e.target_variants)))
        for e in entries)


# ── Reading TBX ───────────────────────────────────────────────────────

def test_read_tbx_basic():
    data = tbx.read_tbx(FIXTURES / "sample.tbx", "en", "ar")
    assert data.languages == ["en", "ar", "fr"]
    assert (data.source_lang, data.target_lang, data.title) == ("en", "ar", "Pump glossary")
    assert data.skipped == 1                      # the entry with English only
    pump, gauge, brand = data.entries
    assert (pump.source, pump.target, pump.uid) == ("pump", "مضخة", "c1")
    assert pump.part_of_speech == "noun"
    assert pump.domain == "Mechanical engineering"
    assert pump.definition == "A device that moves a liquid."
    assert pump.notes == "Use in all manuals."
    assert pump.target_variants == [Variant("طلمبة", forbidden=True)]
    assert gauge.source_variants == [Variant("manometer")]
    assert gauge.target_variants == [Variant("مانومتر")]
    assert brand.source == "FlowMax & Co."
    assert brand.notes == "Brand name. First note.\nSecond note."


def test_read_tbx_picks_the_languages_asked_for():
    french = tbx.read_tbx(FIXTURES / "sample.tbx", "en", "fr")
    assert [(e.source, e.target) for e in french.entries] == [("pump", "pompe")]
    assert french.skipped == 3
    default = tbx.read_tbx(FIXTURES / "sample.tbx")
    assert (default.source_lang, default.target_lang) == ("en", "ar")
    reverse = tbx.read_tbx(FIXTURES / "sample.tbx", "ar", "en")
    assert reverse.entries[0].source == "مضخة" and reverse.entries[0].target == "pump"
    assert reverse.entries[0].source_variants == [Variant("طلمبة", forbidden=True)]


def test_read_tbx_version_3_and_region_codes():
    data = tbx.read_tbx(FIXTURES / "sample_v3.tbx", "en", "ar")
    assert (data.source_lang, data.target_lang) == ("en-US", "ar-EG")
    (entry,) = data.entries
    assert (entry.source, entry.target, entry.part_of_speech, entry.domain) == \
        ("emergency stop", "إيقاف الطوارئ", "noun", "Safety")
    assert entry.target_variants == [Variant("توقف طارئ", forbidden=True)]


def test_a_tbx_file_cannot_pull_in_other_files(tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP-SECRET", encoding="utf-8")
    evil = tmp_path / "evil.tbx"
    evil.write_text(
        f'<?xml version="1.0"?><!DOCTYPE martif [<!ENTITY x SYSTEM "file://{secret}">]>'
        '<martif type="TBX-Basic" xml:lang="en"><text><body><termEntry id="c1">'
        '<langSet xml:lang="en"><tig><term>a&x;</term></tig></langSet>'
        '<langSet xml:lang="fr"><tig><term>b</term></tig></langSet>'
        '</termEntry></body></text></martif>', encoding="utf-8")
    data = tbx.read_tbx(evil, "en", "fr")
    assert all("TOP-SECRET" not in e.source for e in data.entries)


# ── Writing TBX ───────────────────────────────────────────────────────

def test_write_tbx_is_well_formed_tbx_basic(tmp_path):
    entries = tbx.read_tbx(FIXTURES / "sample.tbx", "en", "ar").entries
    out = tmp_path / "out.tbx"
    assert tbx.write_tbx(out, entries, "en", "ar", "Pump glossary") == 3
    root = etree.parse(str(out)).getroot()
    assert root.tag == "martif" and root.get("type") == "TBX-Basic"
    assert len(root.findall(".//termEntry")) == 3
    statuses = [n.text for n in root.findall(".//termNote[@type='administrativeStatus']")]
    assert "deprecatedTerm-admn-sts" in statuses and "admittedTerm-admn-sts" in statuses
    ids = [e.get("id") for e in root.findall(".//termEntry")]
    assert len(set(ids)) == 3 and all(i[0].isalpha() or i[0] == "_" for i in ids)


def test_tbx_file_round_trip_without_loss(tmp_path):
    first = tbx.read_tbx(FIXTURES / "sample.tbx", "en", "ar")
    out = tmp_path / "out.tbx"
    tbx.write_tbx(out, first.entries, "en", "ar", first.title)
    second = tbx.read_tbx(out, "en", "ar")
    assert as_tuples(second.entries) == as_tuples(first.entries)
    assert [e.uid for e in second.entries] == [e.uid for e in first.entries]
    assert second.title == first.title


# ── TBX → termbase → TBX ──────────────────────────────────────────────

def test_tbx_to_termbase_to_tbx_without_loss(termbases, tmp_path):
    original = tbx.read_tbx(FIXTURES / "sample.tbx", "en", "ar")
    termbase_id = termbases.create_termbase("Pumps", "en", "ar")
    report = store.import_entries(termbases, termbase_id, original.entries, "en", "ar")
    assert (report.added, report.merged, report.failed) == (3, 0, 0)

    exported = store.export_entries(termbases, termbase_id)
    out = tmp_path / "exported.tbx"
    tbx.write_tbx(out, exported, "en", "ar", "Pumps")
    again = tbx.read_tbx(out, "en", "ar")
    # The termbase stores a term without a final full stop ("FlowMax & Co").
    expected = as_tuples(original.entries)
    expected = sorted(tuple("FlowMax & Co" if x == "FlowMax & Co." else x for x in row)
                      for row in expected)
    assert as_tuples(again.entries) == expected


def test_importing_the_same_file_twice_adds_nothing(termbases):
    entries = tbx.read_tbx(FIXTURES / "sample.tbx", "en", "ar").entries
    termbase_id = termbases.create_termbase("Pumps", "en", "ar")
    store.import_entries(termbases, termbase_id, entries, "en", "ar")
    report = store.import_entries(termbases, termbase_id, entries, "en", "ar")
    assert (report.added, report.merged, report.failed) == (0, 3, 0)
    assert len(termbases.get_terms(termbase_id)) == 3
    exported = store.export_entries(termbases, termbase_id)
    assert sum(len(e.target_variants) + len(e.source_variants) for e in exported) == 3


def test_a_second_import_adds_new_variants_and_fills_empty_details(termbases):
    termbase_id = termbases.create_termbase("Pumps", "en", "ar")
    store.import_entries(termbases, termbase_id, [Entry("valve", "صمام")], "en", "ar")
    richer = Entry("valve", "صمام", target_variants=[Variant("محبس", forbidden=True)],
                   part_of_speech="noun", definition="Controls flow.", domain="Mechanics")
    report = store.import_entries(termbases, termbase_id, [richer], "en", "ar")
    assert report.merged == 1
    (entry,) = store.export_entries(termbases, termbase_id)
    assert entry.target_variants == [Variant("محبس", forbidden=True)]
    assert (entry.part_of_speech, entry.definition, entry.domain) == ("noun", "Controls flow.", "Mechanics")


def test_forbidden_main_term_survives(termbases, tmp_path):
    termbase_id = termbases.create_termbase("Forbidden", "en", "fr")
    store.import_entries(termbases, termbase_id, [Entry("e-mail", "mél", forbidden=True)], "en", "fr")
    out = tmp_path / "f.tbx"
    tbx.write_tbx(out, store.export_entries(termbases, termbase_id), "en", "fr")
    assert tbx.read_tbx(out, "en", "fr").entries[0].forbidden is True


# ── XLSX and CSV ──────────────────────────────────────────────────────

HEADERS = ["English", "Arabic", "Synonyms", "Forbidden terms", "Part of speech", "Definition",
           "Comment", "Subject"]
ROWS = [
    ["pump", "مضخة", "", "طلمبة", "noun", "A device that moves a liquid.", "Use in all manuals.", "Mechanics"],
    ["pressure gauge", "مقياس الضغط", "مانومتر; عداد الضغط", "", "noun", "", "", ""],
    ["", "بدون مصدر", "", "", "", "", "", ""],
]


def _write_xlsx(path):
    import openpyxl
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.append(HEADERS)
    for row in ROWS:
        sheet.append(row)
    book.save(str(path))


def _write_csv(path, delimiter=","):
    import csv
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=delimiter)
        writer.writerow(HEADERS)
        writer.writerows(ROWS)


@pytest.mark.parametrize("kind", ["xlsx", "csv", "semicolon-csv", "tsv"])
def test_read_table_and_guess_the_columns(tmp_path, kind):
    path = tmp_path / ("terms." + ("xlsx" if kind == "xlsx" else "tsv" if kind == "tsv" else "csv"))
    if kind == "xlsx":
        _write_xlsx(path)
    else:
        _write_csv(path, {"csv": ",", "semicolon-csv": ";", "tsv": "\t"}[kind])
    headers, rows = tabular.read_table(str(path))
    assert headers == HEADERS
    assert len(rows) == 3 and rows[0][1] == "مضخة"

    mapping = tabular.guess_mapping(headers, "en", "ar")
    # "English"/"Arabic" are not language codes, so the first two free columns are used.
    assert mapping["source"] == 0 and mapping["target"] == 1
    assert mapping["target_variants"] == 2
    assert mapping["forbidden_targets"] == 3
    assert mapping["part_of_speech"] == 4
    assert mapping["definition"] == 5
    assert mapping["notes"] == 6
    assert mapping["domain"] == 7

    entries, skipped = tabular.to_entries(rows, mapping)
    assert skipped == 1
    pump, gauge = entries
    assert (pump.source, pump.target, pump.part_of_speech, pump.domain) == ("pump", "مضخة", "noun", "Mechanics")
    assert pump.target_variants == [Variant("طلمبة", forbidden=True)]
    assert pump.notes == "Use in all manuals."
    assert gauge.target_variants == [Variant("مانومتر"), Variant("عداد الضغط")]


def test_language_code_headers_are_matched_to_the_termbase_languages():
    mapping = tabular.guess_mapping(["ID", "fr-FR", "en-GB", "Note"], "en", "fr")
    assert mapping["source"] == 2 and mapping["target"] == 1 and mapping["notes"] == 3


def test_a_mapping_without_source_or_target_is_refused():
    with pytest.raises(ValueError):
        tabular.to_entries([["a", "b"]], {"source": 0})


def test_xlsx_to_termbase_to_tbx(termbases, tmp_path):
    path = tmp_path / "terms.xlsx"
    _write_xlsx(path)
    headers, rows = tabular.read_table(str(path))
    entries, _ = tabular.to_entries(rows, tabular.guess_mapping(headers, "en", "ar"))
    termbase_id = termbases.create_termbase("Sheet", "en", "ar")
    assert store.import_entries(termbases, termbase_id, entries, "en", "ar").added == 2
    out = tmp_path / "sheet.tbx"
    tbx.write_tbx(out, store.export_entries(termbases, termbase_id), "en", "ar", "Sheet")
    assert as_tuples(tbx.read_tbx(out, "en", "ar").entries) == as_tuples(entries)


# ── The dialogs ───────────────────────────────────────────────────────

def test_column_mapping_dialog_shows_the_guess_and_blocks_a_bad_choice(qtbot):
    from PyQt6.QtWidgets import QDialogButtonBox
    from localizelarge.terms.ui import ColumnMappingDialog

    dialog = ColumnMappingDialog(HEADERS, ROWS, tabular.guess_mapping(HEADERS, "en", "ar"))
    qtbot.addWidget(dialog)
    ok = dialog.buttons.button(QDialogButtonBox.StandardButton.Ok)
    assert dialog.mapping()["source"] == 0 and dialog.mapping()["forbidden_targets"] == 3
    assert ok.isEnabled() and dialog.problem.text() == ""

    # The same column for source and target is refused.
    dialog.combos["target"].setCurrentIndex(dialog.combos["source"].currentIndex())
    assert not ok.isEnabled() and "same column" in dialog.problem.text()

    # No target column at all is refused too.
    dialog.combos["target"].setCurrentIndex(0)
    assert not ok.isEnabled() and "Target term" in dialog.problem.text()

    # A user's own choice is what the dialog returns.
    dialog.combos["target"].setCurrentIndex(2)
    dialog.combos["notes"].setCurrentIndex(0)
    assert ok.isEnabled()
    chosen = dialog.mapping()
    assert chosen["target"] == 1 and "notes" not in chosen


def test_import_file_and_export_tbx_through_the_ui_functions(qtbot, termbases, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    from localizelarge.terms import ui

    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: shown.append(a[2]))
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: shown.append(a[2]))
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: shown.append(a[2]))

    termbase_id = termbases.create_termbase("Pumps", "en", "ar")
    # The file's languages match the termbase's, so no question is asked.
    report = ui.import_file(None, termbases, termbase_id, str(FIXTURES / "sample.tbx"))
    assert (report.added, report.failed) == (3, 0)
    assert "Added: 3" in shown[-1] and "Skipped" in shown[-1]

    out = tmp_path / "pumps.tbx"
    assert ui.export_tbx(None, termbases, termbase_id, str(out)) is True
    assert len(tbx.read_tbx(out, "en", "ar").entries) == 3
    assert ui.handles_import("a.TBX") and ui.handles_import("a.xlsx") and not ui.handles_import("a.tsv")

    # A file that is not XML gives a message, not a crash.
    broken = tmp_path / "broken.tbx"
    broken.write_text("not xml", encoding="utf-8")
    assert ui.import_file(None, termbases, termbase_id, str(broken)) is None
    assert "could not be read" in shown[-1]
