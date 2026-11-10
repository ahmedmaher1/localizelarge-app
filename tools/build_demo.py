"""Build the demo project in samples/.

    QT_QPA_PLATFORM=offscreen python tools/build_demo.py

Writes:

    samples/demo-en-ar.docx             a short English document
    samples/demo-en-ar.llproj           its Arabic translation with planted errors and their
                                        issues: QA findings, glossary findings, issues added
                                        by a reviewer, and two AI proposals. The scorecard FAILS.
    samples/demo-en-ar-reviewed.llproj  the same after the errors were corrected and the
                                        issues marked as fixed or rejected. The scorecard PASSES.

The glossary is samples/demo-glossary.tbx (written by hand).

The script starts the real app on a throwaway profile (needs the built sidecar and Java),
imports the document, and uses the same code as the app for every step. The two AI
proposals are written by hand for this sample and say so in their author field; no AI
was called.
"""
import json
import os
import runpy
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"
DOCX = SAMPLES / "demo-en-ar.docx"

PARAGRAPHS = [
    ("heading", "Pump maintenance guide"),
    ("text", "Switch off the power supply before you open the pump housing."),
    ("text", "Check the pressure gauge every week."),
    ("text", "The maximum operating pressure is 6 bar."),
    ("text", "Replace the oil filter after 500 operating hours."),
    ("text", "Wear protective gloves and safety goggles."),
    ("text", "If the pump makes an unusual noise, stop it immediately."),
    ("text", "Do you need help? Write to support@example.com."),
    ("text", "Record the result in the logbook."),
    ("text", "Thank you for using FlowMax."),
]

# Each sentence of the document: (source, the translation as delivered with errors planted
# for the demo, the translation after review).
SENTENCES = [
    ("Pump maintenance guide", "دليل صيانة المضخة", "دليل صيانة المضخة"),
    ("Switch off the power supply before you open the pump housing.",
     "افصل مصدر الطاقة قبل فتح غطاء الطلمبة.",                    # forbidden term
     "افصل مصدر الطاقة قبل فتح هيكل مضخة الماء."),
    ("Check the pressure gauge every week.",
     "افحص مقياس الضغط كل أسبوع",                                # no full stop
     "افحص مقياس الضغط كل أسبوع."),
    ("The maximum operating pressure is 6 bar.",
     "أقصى ضغط تشغيل هو 8 بار.",                                 # wrong number
     "أقصى ضغط تشغيل هو 6 بار."),
    ("Replace the oil filter after 500 operating hours.",
     "استبدل فلتر الزيت بعد 500 ساعة تشغيل.",                     # not the glossary term
     "استبدل مرشح الزيت بعد 500 ساعة تشغيل."),
    ("Wear protective gloves and safety goggles.",
     "ارتدِ القفازات الواقية.",                                   # "and safety goggles" left out
     "ارتدِ القفازات الواقية و نظارات السلامة."),
    ("If the pump makes an unusual noise, stop it immediately.",
     "إذا أصدرت المضخة صوتًا غير عادي، أوقفها أوقفها فورًا.",       # a word twice
     "إذا أصدرت مضخة الماء صوتًا غير عادي، أوقفها فورًا."),
    ("Do you need help?", "هل تحتاج إلى مساعدة؟", "هل تحتاج إلى مساعدة؟"),
    ("Write to support@example.com.",
     "اكتب إلى support@example.org.",                            # wrong e-mail address
     "اكتب إلى support@example.com."),
    ("Record the result in the logbook.", "", "سجّل النتيجة في السجل."),   # not translated
    ("Thank you for using FlowMax.", "شكرًا لاستخدامك FlowMax.", "شكرًا لاستخدامك FlowMax."),
]


def write_docx():
    import docx
    document = docx.Document()
    for kind, text in PARAGRAPHS:
        if kind == "heading":
            document.add_heading(text, level=1)
        else:
            document.add_paragraph(text)
    SAMPLES.mkdir(exist_ok=True)
    document.save(str(DOCX))


def portable(data: dict) -> dict:
    """A project file without anything from the computer it was made on."""
    data = dict(data)
    data["original_docx_path"] = DOCX.name          # beside the project file
    for key in ("bundled_sources", "concordance_geometry", "ui_settings", "tm_settings",
                "termbase_settings", "nt_settings", "prompt_settings", "spellcheck_settings"):
        data.pop(key, None)
    data["created"] = data["modified"] = "2026-11-10T12:00:00"
    data["id"] = 20261110
    for segment in data.get("segments", []):
        segment["created_at"] = segment["modified_at"] = "2026-11-10T12:00:00"
    for issue in data.get("quality", {}).get("issues", []):
        issue["created_at"] = "2026-11-10T12:00:00Z"
        if issue["origin"] in ("qa", "glossary"):
            issue["author"] = "Localize Large"
        elif issue["origin"] == "human":
            issue["author"] = "Reviewer"
    return data


def steps(window, app, work: str):
    from localizelarge.mqm.ai_annotate import RunSummary
    from localizelarge.quality import glossary_check
    from localizelarge.quality.glossary_check import Glossary, GlossaryEntry
    from localizelarge.quality.model import make_issue, plain_text
    from localizelarge.quality.ui import window_hooks as hooks
    from localizelarge.terms import tbx

    def pump(n=200):
        for _ in range(n):
            app.processEvents()

    window.import_docx_from_path(str(DOCX))
    pump(400)
    project = window.current_project
    segments = project.segments
    assert [s.source for s in segments] == [source for source, _, _ in SENTENCES], [s.source for s in segments]
    by_source = {s.source: s for s in segments}
    project.name = "Demo: pump maintenance guide (EN → AR)"
    project.source_lang, project.target_lang = "en", "ar"
    for segment, (_, delivered_text, _) in zip(segments, SENTENCES):
        segment.target = delivered_text
        segment.status = "translated" if delivered_text else "not_started"

    controller = hooks.controller_of(window)
    # The demo glossary, without putting it into the throwaway database.
    entries = []
    for entry in tbx.read_tbx(str(SAMPLES / "demo-glossary.tbx"), "en", "ar").entries:
        entries.append(GlossaryEntry(
            source=entry.source, targets=[entry.target] + [v.text for v in entry.target_variants if not v.forbidden],
            forbidden=[v.text for v in entry.target_variants if v.forbidden], glossary="Demo glossary (pumps)"))
    controller._glossary = Glossary(entries, "en", "ar")
    controller.glossary = lambda: controller._glossary
    controller.run_project()

    def span(segment, side, text):
        plain = plain_text(segment.source if side == "source" else segment.target)
        start = plain.index(text)
        return start, start + len(text)

    # Issues a reviewer added by hand.
    goggles = by_source["Wear protective gloves and safety goggles."]
    start, end = span(goggles, "source", "and safety goggles")
    controller.add_issue(goggles, side="source", start=start, end=end, category="accuracy/omission",
                         severity="critical", comment="The safety goggles are left out. This is a safety instruction.",
                         suggestion="ارتدِ القفازات الواقية و نظارات السلامة.")
    housing = by_source["Switch off the power supply before you open the pump housing."]
    start, end = span(housing, "target", "غطاء")
    controller.add_issue(housing, side="target", start=start, end=end, category="accuracy/mistranslation",
                         severity="minor", comment="“housing” is the casing of the pump, not a lid.",
                         suggestion="هيكل")
    # Two AI proposals, written by hand for this sample (no AI was called).
    proposals = []
    noise = by_source["If the pump makes an unusual noise, stop it immediately."]
    start, end = span(noise, "target", "صوتًا غير عادي")
    proposals.append(make_issue(noise, origin="ai", rule_id="mqm", category="style/unidiomatic-style",
                                severity="minor", side="target", start=start, end=end,
                                message="“صوتًا غير مألوف” reads more naturally here.",
                                suggestion="صوتًا غير مألوف", author="AI: sample/written by hand for this demo"))
    thanks = by_source["Thank you for using FlowMax."]
    start, end = span(thanks, "target", "لاستخدامك")
    proposals.append(make_issue(thanks, origin="ai", rule_id="mqm", category="style/language-register",
                                severity="neutral", side="target", start=start, end=end,
                                message="A manual may address the reader in the plural: “لاستخدامكم”.",
                                suggestion="لاستخدامكم", author="AI: sample/written by hand for this demo"))
    summary = RunSummary(provider="sample", model="written by hand for this demo", date="2026-11-10T12:00:00Z",
                         segments=10, issues_kept=2, issues_dropped=1)
    controller.add_ai_results(proposals, summary)
    pump()

    failing = os.path.join(work, "demo.llproj")
    window.save_project_to_file(failing)
    delivered = portable(json.load(open(failing, encoding="utf-8")))
    (SAMPLES / "demo-en-ar.llproj").write_text(json.dumps(delivered, ensure_ascii=False, indent=2) + "\n",
                                               encoding="utf-8")
    first = controller.score()

    # The review: correct the text, mark what was corrected as fixed, decide the rest.
    changed = set()
    for segment, (_, delivered_text, reviewed_text) in zip(segments, SENTENCES):
        if reviewed_text != delivered_text:
            changed.add(segment.id)
        segment.target = reviewed_text
        segment.status = "confirmed"
    for issue in controller.quality.issues.all():
        if issue.origin == "ai":
            issue.status = "rejected"            # the reviewer did not take the AI's proposals
        elif issue.origin == "human" or issue.segment_id in changed:
            issue.status = "fixed"
        else:
            issue.status = "rejected"            # looked at, and the text is right as it is
    controller.run_project()            # a clean run: the old findings stay as "fixed" history
    assert not [i for i in controller.quality.issues if i.status == "open"], \
        [(i.rule_id, i.message) for i in controller.quality.issues if i.status == "open"]
    passing = os.path.join(work, "demo-reviewed.llproj")
    window.project_modified = True
    window.save_project_to_file(passing)
    reviewed = portable(json.load(open(passing, encoding="utf-8")))
    reviewed["name"] = "Demo: pump maintenance guide (EN → AR), reviewed"
    (SAMPLES / "demo-en-ar-reviewed.llproj").write_text(
        json.dumps(reviewed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    second = controller.score()
    print(f"DEMO delivered: {len(delivered['quality']['issues'])} issues, score {first.score:.2f}, passed={first.passed}")
    print(f"DEMO reviewed: {len(reviewed['quality']['issues'])} issues, score {second.score:.2f}, passed={second.passed}")
    by_origin = {}
    for issue in delivered["quality"]["issues"]:
        by_origin.setdefault(issue["origin"], []).append(issue["rule_id"])
    print("DEMO origins:", {k: sorted(v) for k, v in by_origin.items()})
    assert glossary_check  # imported for the reader: the checks used above


def main():
    write_docx()
    work = tempfile.mkdtemp(prefix="ll-demo-")
    profile = tempfile.mkdtemp(prefix="ll-demo-profile-")
    os.environ.update({"HOME": profile, "USERPROFILE": profile, "APPDATA": os.path.join(profile, "Roaming"),
                       "LOCALAPPDATA": os.path.join(profile, "Local"),
                       "XDG_CONFIG_HOME": os.path.join(profile, "Roaming"),
                       "XDG_DATA_HOME": os.path.join(profile, "Local")})
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    sys.argv = [str(ROOT / "Supervertaler.py")]

    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication, QDialog, QMainWindow, QMessageBox

    accept = lambda self, *a, **k: int(QDialog.DialogCode.Accepted)      # noqa: E731
    QDialog.exec = accept
    QMessageBox.exec = accept
    for name in ("information", "warning", "critical"):
        setattr(QMessageBox, name, staticmethod(lambda *a, **k: None))
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    original_exec = QApplication.exec
    state = {"ok": False}

    def run_steps():
        app = QApplication.instance()
        window = next(w for w in app.topLevelWidgets() if isinstance(w, QMainWindow))
        try:
            steps(window, app, work)
            state["ok"] = True
        except Exception:
            traceback.print_exc()
        finally:
            window.project_modified = False
            window.close()

    def patched_exec(*a, **k):
        QTimer.singleShot(3000, run_steps)
        return original_exec()

    QApplication.exec = staticmethod(patched_exec)
    try:
        runpy.run_path(str(ROOT / "Supervertaler.py"), run_name="__main__")
    except SystemExit:
        pass
    return 0 if state["ok"] else 1


if __name__ == "__main__":
    # The app ends with os._exit(0); report failure before that happens.
    _real_exit = os._exit
    code = {"value": 1}
    os._exit = lambda _code: _real_exit(0 if os.path.exists(SAMPLES / "demo-en-ar-reviewed.llproj") else 1)
    sys.exit(main())
