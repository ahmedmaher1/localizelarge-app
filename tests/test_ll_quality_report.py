"""Phase 5c: the quality report in its four formats: HTML, PDF, XLSX, JSON."""
import json
import os
import re
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from localizelarge.mqm import report as mqm_report  # noqa: E402
from localizelarge.quality.model import IssueList, make_issue  # noqa: E402
from localizelarge.quality.profile import QualityProfile  # noqa: E402
from localizelarge.quality.project_store import ProjectQuality  # noqa: E402


def seg(id, source, target, file_name="manual.docx"):
    return SimpleNamespace(id=id, source=source, target=target, file_name=file_name)


SEGMENTS = [
    seg(1, "Check the <b>pump</b> every week.", "افحص <b>الطلمبة</b> كل أسبوع."),
    seg(2, "The pressure is 6 bar.", "الضغط 8 بار."),
    seg(3, "Wear gloves & goggles.", "ارتدِ القفازات."),
    seg(4, "Close the valve.", "أغلق الصمام.", "notes.txt"),
]


def make_quality():
    issues = IssueList()
    issues.add(make_issue(SEGMENTS[0], origin="glossary", rule_id="glossary.forbidden",
                          category="terminology/inconsistent-with-terminology-resource", severity="major",
                          message="“طلمبة” must not be used for “pump”.", start=7, end=12,
                          suggestion="مضخة", author="Glossary"))
    issues.add(make_issue(SEGMENTS[1], origin="qa", rule_id="qa.numbers", category="accuracy/mistranslation",
                          severity="major", message="The number 6 of the source is not in the target.",
                          author="QA"))
    issues.add(make_issue(SEGMENTS[2], origin="human", rule_id="mqm", category="accuracy/omission",
                          severity="critical", message="“& goggles” is not translated.", side="source",
                          start=12, end=21, comment="Safety text <must> be complete.", status="accepted",
                          author="Reviewer"))
    issues.add(make_issue(SEGMENTS[3], origin="ai", rule_id="mqm", category="style/awkward-style",
                          severity="minor", message="Could be smoother.", author="AI: ollama/llama3"))
    rejected = issues.add(make_issue(SEGMENTS[3], origin="qa", rule_id="qa.length", category="style/awkward-style",
                                     severity="minor", message="Short.", status="rejected", author="QA"))
    stale = issues.add(make_issue(SEGMENTS[3], origin="human", rule_id="mqm", category="linguistic-conventions/grammar",
                                  severity="minor", message="Agreement", start=0, end=4, author="Reviewer"))
    stale.text_hash = "0" * 40
    assert rejected.status == "rejected"
    return ProjectQuality(issues, QualityProfile(name="Client X", version="2"))


AI_RUNS = [{"provider": "ollama", "model": "llama3", "date": "2026-11-10T10:00:00Z", "segments": 4,
            "issuesKept": 1, "issuesDropped": 2, "inputTokens": 900, "outputTokens": 120,
            "estimatedCostUsd": 0.0}]


@pytest.fixture
def report():
    return mqm_report.build(project_name="Pump manual", source_lang="en", target_lang="ar",
                            segments=SEGMENTS, quality=make_quality(), evaluator="Reviewer",
                            date="2026-11-10T12:00:00Z", ai_runs=AI_RUNS, app_version="1.0.0")


def test_report_data(report):
    assert report["project"] == {"name": "Pump manual", "sourceLang": "en", "targetLang": "ar",
                                 "files": ["manual.docx", "notes.txt"], "evaluator": "Reviewer",
                                 "date": "2026-11-10T12:00:00Z", "segmentCount": 4}
    assert report["profile"]["name"] == "Client X" and report["profile"]["version"] == "2"
    score = report["score"]
    # Counted: forbidden term (major 5), number (major 5), omission (critical 25), stale grammar
    # (minor 1). Not counted: the open AI proposal and the rejected finding.
    assert score["issueCount"] == 4 and score["absolutePenaltyTotal"] == 36
    assert score["evaluationWordCount"] == 16
    assert score["passed"] is False and score["model"] == "calibrated"
    assert report["counts"]["bySeverity"] == {"neutral": 0, "minor": 1, "major": 2, "critical": 1}
    assert report["counts"]["byOrigin"] == {"glossary": 1, "qa": 2, "human": 2, "ai": 1}
    assert report["counts"]["byStatus"] == {"open": 4, "accepted": 1, "rejected": 1}
    rows = report["issues"]
    assert [r["segmentNumber"] for r in rows] == [1, 2, 3, 4, 4, 4]
    assert rows[0]["quote"] == "افحص الطلمبة كل أسبوع."[7:12]           # counted in the text without tags
    assert rows[2]["quote"] == "& goggles" and rows[2]["side"] == "source"
    assert rows[2]["categoryLabel"] == "Accuracy › Omission"
    assert [r["counted"] for r in rows].count(False) == 2
    assert [r["needsCheck"] for r in rows].count(True) == 1


def test_json_report_fits_its_schema_and_round_trips(report, tmp_path):
    path = tmp_path / "report.json"
    mqm_report.write(report, str(path))
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded == report
    mqm_report.validate(loaded)
    schema = json.loads(mqm_report.SCHEMA_FILE.read_text(encoding="utf-8"))
    assert schema["properties"]["format"]["const"] == loaded["format"] == "localizelarge-quality-report"


def test_a_report_that_breaks_the_schema_is_not_written(report, tmp_path):
    import jsonschema
    report["issues"][0]["severity"] = "huge"
    with pytest.raises(jsonschema.ValidationError):
        mqm_report.write(report, str(tmp_path / "bad.json"))
    assert not (tmp_path / "bad.json").exists()


def test_html_report_is_self_contained_and_complete(report, tmp_path):
    path = tmp_path / "report.html"
    mqm_report.write(report, str(path))
    page = path.read_text(encoding="utf-8")
    from lxml import etree
    assert etree.HTML(page) is not None
    # One file, nothing loaded from anywhere.
    assert not re.search(r"<script|<link|<img|<iframe|@import|url\(|src=|href=", page, re.I)
    for needle in ("Pump manual", "en → ar", "FAIL", "Client X (version 2", "manual.docx, notes.txt",
                   "Reviewer", "Accuracy › Omission", "Terminology › Inconsistent with terminology resource",
                   "Safety text &lt;must&gt; be complete.", "مضخة", "Needs check", "Not counted in the score",
                   "AI pre-annotation (beta)", "llama3", "The MQM Council", "CC BY 4.0"):
        assert needle in page, needle
    # The span is marked in the text, in the plain text without tags.
    assert "<mark>&amp; goggles</mark>" in page
    assert "<b>pump</b>" not in page and "&lt;b&gt;" not in page
    # Arabic targets are laid out right to left; severity has a letter mark, not only a colour.
    assert 'class="rtl"' in page
    assert re.search(r'class="sev sev-critical">C</span>Critical', page)


def test_xlsx_report_has_a_summary_sheet_and_an_issues_sheet(report, tmp_path):
    import openpyxl
    path = tmp_path / "report.xlsx"
    mqm_report.write(report, str(path))
    book = openpyxl.load_workbook(str(path))
    assert book.sheetnames == ["Summary", "Issues"]
    summary = {row[0]: row[1] for row in book["Summary"].iter_rows(values_only=True) if row[0]}
    assert summary["Project"] == "Pump manual" and summary["Result"] == "FAIL"
    assert summary["Profile"].startswith("Client X (version 2")
    assert summary["Accuracy › Omission"] == 0                # the Neutral column of that category row
    rows = list(book["Issues"].iter_rows(values_only=True))
    header = rows[0]
    assert header[:4] == ("Segment", "File", "Severity", "Category") and len(rows) == 7
    omission = next(r for r in rows[1:] if r[header.index("Category")] == "Accuracy › Omission")
    assert omission[header.index("Text")] == "& goggles"
    assert omission[header.index("Comment")] == "Safety text <must> be complete."
    assert omission[header.index("Source")] == "Wear gloves & goggles."
    assert omission[header.index("Counted")] == "yes"


def test_pdf_report_is_written_with_qt(report, tmp_path, qtbot):
    path = tmp_path / "report.pdf"
    mqm_report.write(report, str(path))
    data = path.read_bytes()
    assert data.startswith(b"%PDF-") and b"%%EOF" in data[-2048:]
    assert len(data) > 5000


def test_a_passing_report_and_an_empty_one(tmp_path):
    clean = mqm_report.build(project_name="Clean", source_lang="en", target_lang="fr", segments=SEGMENTS,
                             quality=ProjectQuality(), evaluator="R", date="2026-11-10T12:00:00Z")
    assert clean["score"]["passed"] is True and clean["score"]["score"] == 100.0
    page = mqm_report.to_html(clean)
    assert "PASS" in page and "No issues." in page and 'class="rtl"' not in page
    mqm_report.validate(clean)
    empty = mqm_report.build(project_name="Empty", source_lang="en", target_lang="fr", segments=[],
                             quality=ProjectQuality(), evaluator="R", date="2026-11-10T12:00:00Z")
    assert empty["score"]["passed"] is None
    assert "Not scored" in mqm_report.to_html(empty)
    mqm_report.validate(empty)


def test_unknown_format_is_refused(report, tmp_path):
    with pytest.raises(ValueError):
        mqm_report.write(report, str(tmp_path / "report.docx"))
