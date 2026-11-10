"""The quality report: one set of data, written as HTML, PDF, XLSX or JSON.

Contents: project, languages, files, evaluator, date, profile or pack name and version,
score and pass/fail, counts per category and severity, and every issue with its segment,
source, target, the text it points at, comment and suggestion. AI runs are listed with
provider, model, token counts and estimated cost.

The HTML report is one file that loads nothing from anywhere.
"""
from __future__ import annotations

import html
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from localizelarge.quality.model import current_author, plain_text
from localizelarge.quality.project_store import ProjectQuality

from . import scoring, typology

FORMAT = "localizelarge-quality-report"
FORMAT_VERSION = 1
SCHEMA_FILE = Path(__file__).resolve().parent.parent / "schemas" / "issues.schema.json"
SEVERITY_LABEL = {"neutral": "Neutral", "minor": "Minor", "major": "Major", "critical": "Critical"}
# A letter mark for each severity, so that nothing depends on colour alone.
SEVERITY_MARK = {"neutral": "N", "minor": "m", "major": "M", "critical": "C"}
ORIGIN_LABEL = {"qa": "QA check", "glossary": "Glossary", "human": "Reviewer", "ai": "AI (beta)"}
STATUS_LABEL = {"open": "Open", "accepted": "Accepted", "rejected": "Rejected", "fixed": "Fixed"}


def build(*, project_name: str, source_lang: str, target_lang: str, segments: Sequence[Any],
          quality: ProjectQuality, evaluator: str = "", date: str = "",
          ai_runs: Optional[Iterable[Dict[str, Any]]] = None, app_version: str = "",
          files: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    """The report as data. Everything the four formats show comes from this."""
    profile = quality.profile
    issues = quality.issues.all()
    result = scoring.calculate(issues, scoring.word_count(segments), profile.scoring)
    counted_ids = {id(i) for i in scoring.counted(issues, profile.scoring)}
    by_id = {getattr(s, "id", None): (number, s) for number, s in enumerate(segments, 1)}
    files_given = list(files or [])
    files = []
    for segment in segments:
        name = getattr(segment, "file_name", "") or ""
        if name and name not in files:
            files.append(name)

    if not files:
        files = [name for name in (files_given or [])]

    rows = []
    for issue in sorted(issues, key=lambda i: (by_id.get(i.segment_id, (10 ** 9, None))[0],
                                               i.start if i.start is not None else -1)):
        number, segment = by_id.get(issue.segment_id, (None, None))
        source = getattr(segment, "source", "") or "" if segment is not None else ""
        target = getattr(segment, "target", "") or "" if segment is not None else ""
        side_text = source if issue.side == "source" else target
        row = issue.to_dict()
        row.update({
            "categoryLabel": typology.label(issue.category),
            "segmentNumber": number,
            "file": getattr(segment, "file_name", "") or "" if segment is not None else "",
            "source": source, "target": target,
            "quote": issue.quoted(side_text),
            "needsCheck": segment is None or issue.is_stale(side_text),
            "counted": id(issue) in counted_ids,
        })
        rows.append(row)

    return {
        "format": FORMAT,
        "formatVersion": FORMAT_VERSION,
        "generator": f"Localize Large {app_version}".strip(),
        "project": {
            "name": project_name or "", "sourceLang": source_lang or "", "targetLang": target_lang or "",
            "files": files, "evaluator": evaluator or current_author(),
            "date": date or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "segmentCount": len(segments),
        },
        "profile": {"name": profile.name, "version": profile.version, "source": profile.source,
                    "scoring": profile.scoring.to_dict()},
        "score": {
            "model": result.model,
            "evaluationWordCount": result.evaluation_word_count,
            "issueCount": result.issue_count,
            "absolutePenaltyTotal": result.absolute_penalty_total,
            "perWordPenaltyTotal": result.per_word_penalty_total,
            "normedPenaltyTotal": result.normed_penalty_total,
            "rawScore": result.raw_score,
            "calibratedScore": result.calibrated_score,
            "score": result.score,
            "threshold": result.threshold,
            "passed": result.passed,
        },
        "counts": {
            "byCategory": [{"category": t.category, "label": typology.label(t.category),
                            "neutral": t.counts.get("neutral", 0), "minor": t.counts.get("minor", 0),
                            "major": t.counts.get("major", 0), "critical": t.counts.get("critical", 0),
                            "weight": t.weight, "penalty": t.penalty} for t in result.by_category],
            "bySeverity": dict(result.by_severity),
            "byOrigin": dict(Counter(i.origin for i in issues)),
            "byStatus": dict(Counter(i.status for i in issues)),
        },
        "ai": list(ai_runs or []),
        "issues": rows,
    }


def validate(report: Dict[str, Any]) -> None:
    """Raise ``jsonschema.ValidationError`` when a report does not fit its schema."""
    import jsonschema
    jsonschema.validate(report, json.loads(SCHEMA_FILE.read_text(encoding="utf-8")))


# ── Words for numbers ─────────────────────────────────────────────────

def _number(value: Optional[float], digits: int = 2) -> str:
    return "–" if value is None else f"{value:.{digits}f}"


def verdict(report: Dict[str, Any]) -> str:
    passed = report["score"]["passed"]
    return "Not scored (no words evaluated)" if passed is None else ("PASS" if passed else "FAIL")


def summary_rows(report: Dict[str, Any]) -> List[List[str]]:
    """(label, value) pairs for the top of a report."""
    project, profile, score = report["project"], report["profile"], report["score"]
    model = "Linear, calibrated" if score["model"] == "calibrated" else "Linear, raw"
    return [
        ["Project", project["name"]],
        ["Languages", f'{project["sourceLang"]} → {project["targetLang"]}'],
        ["Files", ", ".join(project["files"]) or "–"],
        ["Evaluator", project["evaluator"]],
        ["Date", project["date"]],
        ["Profile", f'{profile["name"]} (version {profile["version"]}, {profile["source"]})'],
        ["Scoring model", model],
        ["Evaluated words", str(score["evaluationWordCount"])],
        ["Issues counted", str(score["issueCount"])],
        ["Penalty points", _number(score["absolutePenaltyTotal"])],
        ["Penalty points per 1000 words" if profile["scoring"].get("reference_word_count") == 1000
         else "Normed penalty total", _number(score["normedPenaltyTotal"])],
        ["Quality score", _number(score["score"])],
        ["Pass mark", _number(score["threshold"])],
        ["Result", verdict(report)],
    ]


# ── HTML ──────────────────────────────────────────────────────────────

_CSS = """
body{font-family:Segoe UI,Arial,sans-serif;font-size:13px;color:#1f2933;margin:28px;line-height:1.45}
h1{font-size:22px;margin:0 0 4px} h2{font-size:16px;margin:28px 0 8px}
.sub{color:#52606d;margin-bottom:18px}
table{border-collapse:collapse;width:100%;margin-bottom:8px}
th,td{border:1px solid #cbd2d9;padding:5px 8px;text-align:left;vertical-align:top}
th{background:#e4e7eb} td.n,th.n{text-align:right}
table.summary{width:auto} table.summary th{width:230px}
.verdict{display:inline-block;padding:4px 14px;border:2px solid;font-weight:bold;font-size:15px}
.pass{color:#0b6b3a;border-color:#0b6b3a} .fail{color:#a61b1b;border-color:#a61b1b}
.none{color:#52606d;border-color:#52606d}
.sev{display:inline-block;min-width:1.4em;text-align:center;font-weight:bold;border:1px solid #1f2933;
     border-radius:3px;margin-right:5px;padding:0 3px}
.sev-neutral{border-style:dotted} .sev-minor{border-style:dashed}
.sev-major{border-width:2px} .sev-critical{border-width:3px;border-style:double}
mark{background:#fff3bf;border-bottom:2px solid #1f2933;padding:0 1px}
.rtl{direction:rtl;text-align:right} .muted{color:#52606d} .check{font-weight:bold}
.footer{margin-top:28px;padding-top:10px;border-top:1px solid #cbd2d9;color:#52606d;font-size:12px}
"""

_RTL = {"ar", "he", "iw", "fa", "ur", "ps", "sd", "ug", "yi", "dv", "ckb"}


def _is_rtl(lang: str) -> bool:
    return (lang or "").replace("_", "-").split("-")[0].lower() in _RTL


def _marked(text: str, issue: Dict[str, Any], side: str) -> str:
    """The plain text of a segment side, with the issue's span marked."""
    plain = plain_text(text)
    if issue["side"] != side or issue["start"] is None or issue["needsCheck"]:
        return html.escape(plain)
    start, end = issue["start"], issue["end"]
    return (html.escape(plain[:start]) + "<mark>" + html.escape(plain[start:end]) + "</mark>"
            + html.escape(plain[end:]))


def to_html(report: Dict[str, Any]) -> str:
    project, score = report["project"], report["score"]
    e = html.escape
    state = "none" if score["passed"] is None else ("pass" if score["passed"] else "fail")
    source_class = ' class="rtl"' if _is_rtl(project["sourceLang"]) else ""
    target_class = ' class="rtl"' if _is_rtl(project["targetLang"]) else ""
    out = ["<!DOCTYPE html>", '<html lang="en"><head><meta charset="utf-8">',
           f"<title>Quality report – {e(project['name'])}</title>", f"<style>{_CSS}</style></head><body>",
           "<h1>Quality report</h1>",
           f'<div class="sub">{e(project["name"])} · {e(project["sourceLang"])} → {e(project["targetLang"])}</div>',
           f'<p><span class="verdict {state}">{e(verdict(report))}</span> &nbsp; '
           f'Quality score <b>{_number(score["score"])}</b>, pass mark {_number(score["threshold"])}</p>',
           "<h2>Summary</h2>", '<table class="summary">']
    for label, value in summary_rows(report):
        out.append(f"<tr><th>{e(label)}</th><td>{e(value)}</td></tr>")
    out.append("</table>")

    out.append("<h2>Penalty points per category</h2>")
    if report["counts"]["byCategory"]:
        out.append('<table><tr><th>Category</th><th class="n">Neutral</th><th class="n">Minor</th>'
                   '<th class="n">Major</th><th class="n">Critical</th><th class="n">Weight</th>'
                   '<th class="n">Penalty points</th></tr>')
        for row in report["counts"]["byCategory"]:
            out.append(f'<tr><td>{e(row["label"])}</td><td class="n">{row["neutral"]}</td>'
                       f'<td class="n">{row["minor"]}</td><td class="n">{row["major"]}</td>'
                       f'<td class="n">{row["critical"]}</td><td class="n">{_number(row["weight"])}</td>'
                       f'<td class="n">{_number(row["penalty"])}</td></tr>')
        severities = report["counts"]["bySeverity"]
        out.append(f'<tr><th>Total (counted issues)</th><th class="n">{severities.get("neutral", 0)}</th>'
                   f'<th class="n">{severities.get("minor", 0)}</th><th class="n">{severities.get("major", 0)}</th>'
                   f'<th class="n">{severities.get("critical", 0)}</th><th></th>'
                   f'<th class="n">{_number(score["absolutePenaltyTotal"])}</th></tr></table>')
    else:
        out.append('<p class="muted">No issue counts towards the score.</p>')

    if report["ai"]:
        out.append("<h2>AI pre-annotation (beta)</h2>")
        out.append('<table><tr><th>Date</th><th>Provider</th><th>Model</th><th class="n">Segments</th>'
                   '<th class="n">Issues kept</th><th class="n">Issues dropped</th><th class="n">Tokens in</th>'
                   '<th class="n">Tokens out</th><th class="n">Estimated cost (USD)</th></tr>')
        for run in report["ai"]:
            cost = run.get("estimatedCostUsd")
            out.append(f'<tr><td>{e(str(run.get("date", "")))}</td><td>{e(str(run.get("provider", "")))}</td>'
                       f'<td>{e(str(run.get("model", "")))}</td><td class="n">{run.get("segments", "")}</td>'
                       f'<td class="n">{run.get("issuesKept", "")}</td><td class="n">{run.get("issuesDropped", "")}</td>'
                       f'<td class="n">{run.get("inputTokens") if run.get("inputTokens") is not None else "–"}</td>'
                       f'<td class="n">{run.get("outputTokens") if run.get("outputTokens") is not None else "–"}</td>'
                       f'<td class="n">{"–" if cost is None else f"{cost:.4f}"}</td></tr>')
        out.append("</table>")

    out.append(f'<h2>Issues ({len(report["issues"])})</h2>')
    if report["issues"]:
        out.append("<table><tr><th>Seg.</th><th>Severity</th><th>Category</th><th>Found by</th><th>Status</th>"
                   "<th>Source</th><th>Target</th><th>Issue</th></tr>")
        for issue in report["issues"]:
            severity = issue["severity"]
            details = [e(issue["message"])] if issue["message"] else []
            if issue["comment"]:
                details.append("<b>Comment:</b> " + e(issue["comment"]))
            if issue["suggestion"]:
                details.append("<b>Suggestion:</b> " + e(issue["suggestion"]))
            if issue["needsCheck"]:
                details.append('<span class="check">Needs check: the text changed after this issue was made.</span>')
            if not issue["counted"]:
                details.append('<span class="muted">Not counted in the score.</span>')
            out.append(
                f'<tr><td class="n">{issue["segmentNumber"] if issue["segmentNumber"] is not None else "–"}</td>'
                f'<td><span class="sev sev-{severity}">{SEVERITY_MARK[severity]}</span>{SEVERITY_LABEL[severity]}</td>'
                f'<td>{e(issue["categoryLabel"])}</td><td>{e(ORIGIN_LABEL[issue["origin"]])}<br>'
                f'<span class="muted">{e(issue["author"])}</span></td><td>{STATUS_LABEL[issue["status"]]}</td>'
                f'<td{source_class}>{_marked(issue["source"], issue, "source")}</td>'
                f'<td{target_class}>{_marked(issue["target"], issue, "target")}</td>'
                f'<td>{"<br>".join(details)}</td></tr>')
        out.append("</table>")
        out.append('<p class="muted">Severity marks: N neutral, m minor, M major, C critical.</p>')
    else:
        out.append('<p class="muted">No issues.</p>')

    out.append(f'<div class="footer">{e(report.get("generator") or "Localize Large")} · localizelarge.com. '
               f'Scoring follows the MQM Council\'s linear scoring models. {e(typology.attribution())}</div>')
    out.append("</body></html>")
    return "\n".join(out)


# ── Files ─────────────────────────────────────────────────────────────

def write_html(report: Dict[str, Any], path: str) -> None:
    Path(path).write_text(to_html(report), encoding="utf-8")


def write_json(report: Dict[str, Any], path: str) -> None:
    validate(report)
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_xlsx(report: Dict[str, Any], path: str) -> None:
    """A workbook with a Summary sheet and an Issues sheet."""
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill

    bold = Font(bold=True)
    head = PatternFill("solid", fgColor="E4E7EB")
    book = openpyxl.Workbook()

    summary = book.active
    summary.title = "Summary"
    summary.append(["Quality report"])
    summary["A1"].font = Font(bold=True, size=14)
    for label, value in summary_rows(report):
        summary.append([label, value])
        summary.cell(row=summary.max_row, column=1).font = bold
    summary.append([])
    summary.append(["Category", "Neutral", "Minor", "Major", "Critical", "Weight", "Penalty points"])
    for cell in summary[summary.max_row]:
        cell.font, cell.fill = bold, head
    for row in report["counts"]["byCategory"]:
        summary.append([row["label"], row["neutral"], row["minor"], row["major"], row["critical"],
                        row["weight"], row["penalty"]])
    summary.append([])
    summary.append(["Issues by origin"] + [f"{ORIGIN_LABEL.get(k, k)}: {v}"
                                           for k, v in report["counts"]["byOrigin"].items()])
    summary.append(["Issues by status"] + [f"{STATUS_LABEL.get(k, k)}: {v}"
                                           for k, v in report["counts"]["byStatus"].items()])
    if report["ai"]:
        summary.append([])
        summary.append(["AI run", "Provider", "Model", "Segments", "Issues kept", "Issues dropped",
                        "Tokens in", "Tokens out", "Estimated cost (USD)"])
        for cell in summary[summary.max_row]:
            cell.font, cell.fill = bold, head
        for run in report["ai"]:
            summary.append([run.get("date"), run.get("provider"), run.get("model"), run.get("segments"),
                            run.get("issuesKept"), run.get("issuesDropped"), run.get("inputTokens"),
                            run.get("outputTokens"), run.get("estimatedCostUsd")])
    summary.column_dimensions["A"].width = 34
    summary.column_dimensions["B"].width = 44

    sheet = book.create_sheet("Issues")
    columns = ["Segment", "File", "Severity", "Category", "Found by", "Rule", "Status", "Counted", "Side",
               "Text", "Source", "Target", "Issue", "Comment", "Suggestion", "Needs check", "Author",
               "Created", "Start", "End", "Id"]
    sheet.append(columns)
    for cell in sheet[1]:
        cell.font, cell.fill = bold, head
    for issue in report["issues"]:
        sheet.append([
            issue["segmentNumber"], issue.get("file", ""), SEVERITY_LABEL[issue["severity"]],
            issue["categoryLabel"], ORIGIN_LABEL[issue["origin"]], issue["rule_id"],
            STATUS_LABEL[issue["status"]], "yes" if issue["counted"] else "no", issue["side"],
            issue["quote"], plain_text(issue["source"]), plain_text(issue["target"]), issue["message"],
            issue["comment"] or "", issue["suggestion"] or "", "yes" if issue["needsCheck"] else "no",
            issue["author"], issue["created_at"], issue["start"], issue["end"], issue["id"]])
    for letter, width in zip("ABCDEFGHIJKLMNO", (9, 18, 10, 30, 12, 20, 10, 9, 8, 22, 44, 44, 50, 30, 30)):
        sheet.column_dimensions[letter].width = width
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    sheet.freeze_panes = "A2"
    book.save(str(path))


def write_pdf(report: Dict[str, Any], path: str) -> None:
    """The HTML report printed to PDF with Qt (QTextDocument and QPrinter)."""
    from PyQt6.QtCore import QMarginsF, QSizeF
    from PyQt6.QtGui import QPageLayout, QPageSize, QTextDocument
    from PyQt6.QtPrintSupport import QPrinter

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(path))
    printer.setPageLayout(QPageLayout(QPageSize(QPageSize.PageSizeId.A4), QPageLayout.Orientation.Landscape,
                                      QMarginsF(12, 12, 12, 12), QPageLayout.Unit.Millimeter))
    document = QTextDocument()
    document.setHtml(to_html(report))
    document.setPageSize(QSizeF(printer.pageRect(QPrinter.Unit.Point).size()))
    document.print(printer)


WRITERS = {".html": write_html, ".pdf": write_pdf, ".xlsx": write_xlsx, ".json": write_json}


def write(report: Dict[str, Any], path: str) -> None:
    """Write a report in the format its file extension names."""
    extension = Path(path).suffix.lower()
    if extension not in WRITERS:
        raise ValueError(f"unknown report format: {extension}")
    WRITERS[extension](report, path)
