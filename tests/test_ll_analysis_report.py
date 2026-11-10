"""Phase 4: the analysis report (match bands) exports to XLSX and to self-contained HTML,
per file and in total, with segments, words and characters."""
import os
import re
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytest.importorskip("PyQt6")

from modules.statistics_analyzer import (  # noqa: E402
    CAT_100, CAT_85_94, CAT_NO_MATCH, CAT_REPETITION, CATEGORIES, TMResult,
)
from modules.statistics_dialog_qt import StatisticsDialog  # noqa: E402


def make_result():
    result = TMResult("tm1", "Main memory")
    rows = [
        ("manual.docx", CAT_100, 10, 55, 0),
        ("manual.docx", CAT_85_94, 8, 40, 2),
        ("manual.docx", CAT_NO_MATCH, 20, 120, 1),
        ("ui.json", CAT_NO_MATCH, 5, 30, 0),
        ("ui.json", CAT_REPETITION, 5, 30, 0),
    ]
    for file_name, band, words, chars, tags in rows:
        result.add_total(file_name, words, chars, tags)
        result.add_to(band, file_name, words, chars, tags)
    return result


@pytest.fixture
def report():
    """The dialog's export methods on a stand-in for the dialog's data."""
    stub = SimpleNamespace(_results=[make_result()], _segments=[None] * 5,
                           _project_name="Pump <manual>", _src_lang="en", _tgt_lang="ar")
    for name in ("_rows_for", "_build_html", "_write_xlsx", "_write_csv"):
        setattr(stub, name, getattr(StatisticsDialog, name).__get__(stub))
    return stub


def test_html_report_is_self_contained_and_has_totals_and_files(report):
    page = report._build_html()
    # Nothing is loaded from outside: no scripts, style sheets, images or fonts.
    assert not re.search(r"<script|<link|<img|@import|url\(|src=", page, re.I)
    assert "Pump &lt;manual&gt;" in page                 # the project name is escaped
    assert "All files" in page and "manual.docx" in page and "ui.json" in page
    for band in CATEGORIES:
        assert band in page
    for column in ("Segments", "Words", "Characters"):
        assert column in page
    # Total row: 5 segments, 48 words, 275 characters.
    total = re.search(r"<tr class='total'><td>All files</td>(.*?)</tr>", page, re.S).group(1)
    assert re.findall(r"<td>([\d,.]+)</td>", total)[:3] == ["5", "48", "275"]
    assert "Michael Beijer" in page


def test_xlsx_report_has_totals_and_one_block_per_file(report, tmp_path):
    import openpyxl
    path = tmp_path / "analysis.xlsx"
    report._write_xlsx(str(path))
    sheet = openpyxl.load_workbook(str(path)).active
    rows = [[c for c in row] for row in sheet.iter_rows(values_only=True)]
    first = [row[0] for row in rows]
    assert "Resources: Main memory" in first
    headers = next(row for row in rows if row[0] == "Type")
    assert list(headers[:4]) == ["Type", "Segments", "Words", "Characters"]
    total = next(row for row in rows if row[0] == "All files")
    assert total[1:4] == (5, 48, 275) or list(total[1:4]) == [5, 48, 275]
    blocks = [row[0] for row in rows if row[0] and str(row[0]).startswith("File: ")]
    assert blocks == ["File: manual.docx", "File: ui.json"]
    # The per-file figures: manual.docx has 3 segments, 38 words, 215 characters.
    start = next(i for i, row in enumerate(rows) if row[0] == "File: manual.docx")
    file_total = next(row for row in rows[start:] if row[0] == "All")
    assert list(file_total[1:4]) == [3, 38, 215]
    # Every band is a row, with numbers (not text) in the count columns.
    for band in CATEGORIES:
        row = next(r for r in rows if r[0] == band)
        assert all(isinstance(v, (int, float)) for v in row[1:6])


def test_csv_report_opens_and_has_the_same_total(report, tmp_path):
    import csv
    path = tmp_path / "analysis.csv"
    report._write_csv(str(path))
    with open(path, encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    total = next(row for row in rows if row and row[0] == "All files")
    assert total[1:4] == ["5", "48", "275"]
