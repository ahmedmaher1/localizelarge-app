"""Phase 5: the demo project in samples/ shows every kind of issue, a failing and a
passing scorecard, and all four report formats."""
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from localizelarge.mqm import report as mqm_report  # noqa: E402
from localizelarge.mqm import scoring, typology  # noqa: E402
from localizelarge.quality.model import plain_text  # noqa: E402
from localizelarge.quality.project_store import ProjectQuality  # noqa: E402

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def load(name):
    data = json.loads((SAMPLES / name).read_text(encoding="utf-8"))
    segments = [SimpleNamespace(**{"file_name": "", **s}) for s in data["segments"]]
    return data, segments, ProjectQuality.from_dict(data["quality"])


@pytest.fixture(scope="module")
def delivered():
    return load("demo-en-ar.llproj")


@pytest.fixture(scope="module")
def reviewed():
    return load("demo-en-ar-reviewed.llproj")


def test_the_demo_files_are_there_and_portable(delivered):
    data, segments, _ = delivered
    for name in ("demo-en-ar.docx", "demo-en-ar.llproj", "demo-en-ar-reviewed.llproj", "demo-glossary.tbx",
                 "README.md"):
        assert (SAMPLES / name).is_file(), name
    assert (data["format"], data["source_lang"], data["target_lang"]) == ("localizelarge-project", "en", "ar")
    assert data["original_docx_path"] == "demo-en-ar.docx"           # beside the project, not an absolute path
    text = (SAMPLES / "demo-en-ar.llproj").read_text(encoding="utf-8")
    assert "/home/" not in text and "/tmp/" not in text and "C:\\\\" not in text
    assert len(segments) == 11


def test_the_source_document_matches_the_project(delivered):
    import docx
    _, segments, _ = delivered
    paragraphs = " ".join(p.text for p in docx.Document(str(SAMPLES / "demo-en-ar.docx")).paragraphs)
    for segment in segments:
        assert segment.source in paragraphs


def test_the_delivered_project_has_every_kind_of_issue(delivered):
    _, segments, quality = delivered
    issues = quality.issues.all()
    origins = {i.origin for i in issues}
    assert origins == {"qa", "glossary", "human", "ai"}
    rules = {i.rule_id for i in issues}
    assert {"qa.empty", "qa.numbers", "qa.end_punctuation", "qa.repeated_word", "qa.urls_emails",
            "glossary.required", "glossary.forbidden", "mqm"} <= rules
    by_id = {s.id: s for s in segments}
    for issue in issues:
        assert typology.get(issue.category) is not None, issue.category
        segment = by_id[issue.segment_id]
        side_text = segment.source if issue.side == "source" else segment.target
        assert not issue.is_stale(side_text), issue.message          # every span still fits its text
        if issue.start is not None and issue.end > issue.start:      # a position alone marks "missing here"
            assert issue.quoted(side_text)
    omission = next(i for i in issues if i.category == "accuracy/omission")
    assert omission.quoted(by_id[omission.segment_id].source) == "and safety goggles"
    forbidden = next(i for i in issues if i.rule_id == "glossary.forbidden")
    assert forbidden.quoted(by_id[forbidden.segment_id].target) == "الطلمبة"
    for ai_issue in (i for i in issues if i.origin == "ai"):
        assert ai_issue.status == "open" and "written by hand" in ai_issue.author


def test_the_delivered_project_fails_and_the_reviewed_one_passes(delivered, reviewed):
    _, segments, quality = delivered
    failing = scoring.calculate(quality.issues.all(), scoring.word_count(segments), quality.profile.scoring)
    assert failing.passed is False and failing.evaluation_word_count == 71
    # Counted: everything except the two open AI proposals.
    assert failing.issue_count == len(quality.issues) - 2
    assert failing.by_severity["critical"] == 1

    _, segments2, quality2 = reviewed
    passing = scoring.calculate(quality2.issues.all(), scoring.word_count(segments2), quality2.profile.scoring)
    assert passing.passed is True and passing.score == 100.0 and passing.issue_count == 0
    assert {i.status for i in quality2.issues} == {"fixed", "rejected"}
    assert all(s.target.strip() for s in segments2)


def test_the_reviewed_text_has_no_qa_findings_and_uses_the_glossary(reviewed):
    from localizelarge.quality import engine, glossary_check
    from localizelarge.quality.checks import Context
    from localizelarge.quality.glossary_check import Glossary, GlossaryEntry
    from localizelarge.terms import tbx
    _, segments, _ = reviewed
    assert engine.run_project(segments, Context("en", "ar", segments)) == []
    entries = [GlossaryEntry(e.source, targets=[e.target] + [v.text for v in e.target_variants if not v.forbidden],
                             forbidden=[v.text for v in e.target_variants if v.forbidden])
               for e in tbx.read_tbx(str(SAMPLES / "demo-glossary.tbx"), "en", "ar").entries]
    found = glossary_check.run(segments, Glossary(entries, "en", "ar"))
    assert found == []


@pytest.mark.parametrize("name", ["demo-en-ar.llproj", "demo-en-ar-reviewed.llproj"])
def test_all_four_report_formats_open(name, tmp_path, qtbot):
    data, segments, quality = load(name)
    report = mqm_report.build(project_name=data["name"], source_lang="en", target_lang="ar", segments=segments,
                              quality=quality, evaluator="Reviewer", date="2026-11-10T12:00:00Z",
                              app_version="1.0.0")
    mqm_report.validate(report)
    for extension in (".html", ".pdf", ".xlsx", ".json"):
        mqm_report.write(report, str(tmp_path / ("report" + extension)))

    from lxml import etree
    page = (tmp_path / "report.html").read_text(encoding="utf-8")
    assert etree.HTML(page) is not None
    assert ("FAIL" if name == "demo-en-ar.llproj" else "PASS") in page and 'class="rtl"' in page
    assert (tmp_path / "report.pdf").read_bytes().startswith(b"%PDF-")
    import openpyxl
    book = openpyxl.load_workbook(str(tmp_path / "report.xlsx"))
    assert book["Issues"].max_row == len(report["issues"]) + 1
    assert json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))["project"]["name"] == data["name"]
    if name == "demo-en-ar.llproj":
        assert "<mark>and safety goggles</mark>" in page
        assert plain_text(segments[5].target) in page
