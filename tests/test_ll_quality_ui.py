"""Phase 5c: the quality user interface: controller, Add issue dialog, underlines and
status markers, and the Quality panel."""
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytest.importorskip("PyQt6")

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtGui import QTextCharFormat, QTextCursor  # noqa: E402
from PyQt6.QtWidgets import QDialogButtonBox, QMainWindow, QTableWidget, QTableWidgetItem, QTextEdit  # noqa: E402

from localizelarge import rtl  # noqa: E402
from localizelarge.quality.model import plain_text  # noqa: E402
from localizelarge.quality.project_store import quality_of  # noqa: E402
from localizelarge.quality.ui import marks, window_hooks  # noqa: E402
from localizelarge.quality.ui.add_issue_dialog import AddIssueDialog  # noqa: E402
from localizelarge.quality.ui.controller import QualityController  # noqa: E402
from localizelarge.quality.ui.panel import QualityPanel  # noqa: E402


class Cell(rtl.DirectionMixin, QTextEdit):
    def __init__(self, side, text):
        super().__init__()
        self.ll_side = side
        self.setPlainText(text)


class Window(QMainWindow):
    """A stand-in for the main window: a project, a grid, and what the controller reads."""

    def __init__(self, segments, source_lang="en", target_lang="fr"):
        super().__init__()
        self.current_project = SimpleNamespace(id=1, name="Demo", source_lang=source_lang,
                                               target_lang=target_lang, segments=segments)
        self.project_modified = False
        self.spellcheck_enabled = False
        self.navigated = []
        self.status_updates = []
        self.logged = []
        self.qa_menu = self.menuBar().addMenu("&QA")
        self.qa_menu.addAction("Existing action")
        self.table = QTableWidget(len(segments), 5)
        self.setCentralWidget(self.table)
        rtl.set_language_provider(lambda: (source_lang, target_lang))
        for row, segment in enumerate(segments):
            self.table.setItem(row, 0, QTableWidgetItem(str(segment.id)))
            self.table.setCellWidget(row, 2, Cell("source", segment.source))
            self.table.setCellWidget(row, 3, Cell("target", segment.target))

    def log(self, text):
        self.logged.append(text)

    def _navigate_to_segment_by_id(self, segment_id):
        self.navigated.append(segment_id)

    def _update_status_cell(self, row, segment):
        self.status_updates.append(segment.id)


def seg(id, source, target):
    return SimpleNamespace(id=id, source=source, target=target, file_name="demo.docx")


@pytest.fixture
def window(qtbot):
    segments = [seg(1, "Page 5 of 10.", "Page 6 sur 10."),
                seg(2, "Click <b>Save</b> now.", "Cliquez sur <b>Enregistrer</b> maintenant."),
                seg(3, "Close the valve.", "")]
    win = Window(segments)
    qtbot.addWidget(win)
    window_hooks.install(win, "1.0.0")
    yield win
    rtl.set_language_provider(None)


# ── Installing ────────────────────────────────────────────────────────

def test_install_adds_the_actions_and_a_hidden_dock(window):
    controller = window_hooks.controller_of(window)
    assert isinstance(controller, QualityController)
    assert window_hooks.install(window) is controller                 # only once
    texts = [a.text() for a in window.qa_menu.actions() if a.text()]
    assert texts[:5] == ["Run &QA (all checks)", "&Add issue…", "AI pre-annotation (&beta)…", "Quality &panel",
                         "&Export quality report…"]
    assert "Existing action" in texts
    add = next(a for a in window.qa_menu.actions() if a.text() == "&Add issue…")
    assert add.shortcut().toString() == "Ctrl+Shift+E"
    panel = window._ll_quality_panel
    assert isinstance(panel, QualityPanel) and panel.isHidden()
    assert [panel.tabs.tabText(i) for i in range(3)] == ["Issues", "Scorecard", "Profile"]


def test_ctrl_shift_e_is_not_used_by_another_shortcut():
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    for path in [root / "Supervertaler.py", *sorted((root / "modules").glob("*.py"))]:
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"""["']Ctrl\+Shift\+E["']""", text), path.name


# ── Running QA ────────────────────────────────────────────────────────

def test_run_qa_finds_issues_marks_the_grid_and_fills_the_panel(window):
    controller = window_hooks.controller_of(window)
    window_hooks.run_qa(window)
    panel = window._ll_quality_panel
    assert not panel.isHidden()
    rules = sorted(i.rule_id for i in controller.quality.issues)
    assert rules == ["qa.empty", "qa.numbers", "qa.numbers"]
    assert window.project_modified is True
    assert set(window.status_updates) == {1, 2, 3}
    assert panel.table.rowCount() == 3
    assert panel.count_label.text() == "3 issues"
    assert panel.table.item(0, 1).text().startswith("M")              # a letter, not only a colour
    assert window.logged[-1].endswith("3 finding(s)")

    # The number that is not in the source is underlined in the target cell.
    target_cell = window.table.cellWidget(0, 3)
    (selection,) = target_cell.extraSelections()
    assert selection.cursor.selectedText() == "6"
    assert selection.format.underlineStyle() == QTextCharFormat.UnderlineStyle.SingleUnderline

    marker, tooltip = controller.status_marker(window.current_project.segments[0])
    assert marker == "M2" and "qa" not in marker and "The number" in tooltip
    assert controller.status_marker(window.current_project.segments[1]) == ("", "")


def test_filters_and_double_click(window):
    window_hooks.run_qa(window)
    panel = window._ll_quality_panel
    panel.category_filter.setCurrentIndex(panel.category_filter.findData("accuracy"))
    assert panel.table.rowCount() == 3
    panel.category_filter.setCurrentIndex(panel.category_filter.findData("style"))
    assert panel.table.rowCount() == 0 and panel.count_label.text() == "0 of 3 issues"
    panel.category_filter.setCurrentIndex(0)
    panel.origin_filter.setCurrentIndex(panel.origin_filter.findData("human"))
    assert panel.table.rowCount() == 0
    panel.origin_filter.setCurrentIndex(0)
    panel.table.itemDoubleClicked.emit(panel.table.item(2, 0))
    assert window.navigated == [3]


def test_decisions_survive_a_second_run_and_rejected_issues_lose_their_underline(window):
    controller = window_hooks.controller_of(window)
    controller.run_project()
    extra = next(i for i in controller.quality.issues if i.start is not None)
    assert controller.set_status(extra.id, "rejected") is True
    assert window.table.cellWidget(0, 3).extraSelections() == []
    controller.run_project()
    assert controller.quality.issues.get(extra.id).status == "rejected"
    assert controller.status_marker(window.current_project.segments[0])[0] == "M1"


def test_confirming_a_segment_checks_only_that_segment(window):
    controller = window_hooks.controller_of(window)
    window_hooks.segment_confirmed(window, window.current_project.segments[0])
    assert {i.segment_id for i in controller.quality.issues} == {1}
    # Fix the number and confirm again: the findings go away.
    window.current_project.segments[0].target = "Page 5 sur 10."
    window_hooks.segment_confirmed(window, window.current_project.segments[0])
    assert len(controller.quality.issues) == 0


# ── Adding an issue by hand ───────────────────────────────────────────

def select(editor, text):
    shown = QTextEdit.toPlainText(editor)
    start = shown.index(text)
    cursor = editor.textCursor()
    cursor.setPosition(start)
    cursor.setPosition(start + len(text), QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)


def test_the_selection_is_counted_in_the_text_without_tags(window):
    editor = window.table.cellWidget(1, 3)
    select(editor, "Enregistrer")
    start, end = window_hooks.selection_in_plain_text(editor)
    assert plain_text(window.current_project.segments[1].target)[start:end] == "Enregistrer"
    select(editor, "<b>Enregistrer</b> maintenant")
    start, end = window_hooks.selection_in_plain_text(editor)
    assert plain_text(window.current_project.segments[1].target)[start:end] == "Enregistrer maintenant"
    assert window_hooks.selection_in_plain_text(window.table.cellWidget(0, 3)) == (None, None)


def test_add_issue_from_a_selection(window, monkeypatch):
    controller = window_hooks.controller_of(window)
    editor = window.table.cellWidget(1, 3)
    select(editor, "Enregistrer")

    def fake_exec(dialog):
        assert "Enregistrer" in dialog.quote_label.text() and "target" in dialog.quote_label.text()
        dialog.search.setText("mistransl")
        dialog.severity_buttons["major"].click()
        dialog.comment.setPlainText("Wrong verb")
        dialog.suggestion.setText("Sauvegarder")
        return AddIssueDialog.DialogCode.Accepted

    monkeypatch.setattr(AddIssueDialog, "exec", fake_exec)
    issue = window_hooks.add_issue(window, editor)
    assert (issue.origin, issue.rule_id, issue.category, issue.severity, issue.status) == \
        ("human", "mqm", "accuracy/mistranslation", "major", "accepted")
    assert (issue.comment, issue.suggestion, issue.side) == ("Wrong verb", "Sauvegarder", "target")
    assert issue.quoted(window.current_project.segments[1].target) == "Enregistrer"
    assert controller.quality.issues.all() == [issue]
    assert not window._ll_quality_panel.isHidden()
    # Underlined in the cell, although the cell shows the tags.
    (selection,) = editor.extraSelections()
    assert selection.cursor.selectedText() == "Enregistrer"
    assert controller.status_marker(window.current_project.segments[1])[0] == "M1"


def test_add_issue_on_the_source_for_an_omission_and_without_a_selection(window, monkeypatch):
    monkeypatch.setattr(AddIssueDialog, "exec", lambda d: (d._select("accuracy/omission"),
                                                          AddIssueDialog.DialogCode.Accepted)[1])
    source_editor = window.table.cellWidget(1, 2)
    select(source_editor, "now")
    issue = window_hooks.add_issue(window, source_editor)
    assert issue.side == "source" and issue.quoted(window.current_project.segments[1].source) == "now"
    assert source_editor.extraSelections()[0].cursor.selectedText() == "now"
    whole = window_hooks.add_issue(window, window.table.cellWidget(0, 3))
    assert whole.start is None and whole.segment_id == 1


def test_cancelling_the_dialog_adds_nothing(window, monkeypatch):
    monkeypatch.setattr(AddIssueDialog, "exec", lambda d: AddIssueDialog.DialogCode.Rejected)
    assert window_hooks.add_issue(window, window.table.cellWidget(0, 3)) is None
    assert len(window_hooks.controller_of(window).quality.issues) == 0


def test_the_dialog_searches_categories_and_takes_keys_1_to_4(qtbot):
    dialog = AddIssueDialog("pump", "target")
    qtbot.addWidget(dialog)
    assert dialog.categories.count() == 7 + 38                         # MQM Core: dimensions and subtypes
    assert dialog.severity() == "minor" and dialog.category() == ""
    dialog._accept()
    assert dialog.problem.text() == "Choose a category." and dialog.result() == 0

    dialog.search.setText("omiss")
    visible = [dialog.categories.item(i).data(Qt.ItemDataRole.UserRole)
               for i in range(dialog.categories.count()) if not dialog.categories.item(i).isHidden()]
    # The Accuracy dimension stays too (its definition names omission); the subtype is chosen.
    assert visible == ["accuracy", "accuracy/omission"] and dialog.category() == "accuracy/omission"
    assert "missing in the target" in dialog.definition.text()
    dialog.search.setText("term wrong")                                # words in any order, in name or definition
    assert dialog.category() == "terminology/wrong-term"

    dialog.categories.setFocus()
    for key, severity in (("4", "critical"), ("1", "neutral"), ("3", "major"), ("2", "minor")):
        qtbot.keyClicks(dialog, key)
        assert dialog.severity() == severity
    # Typing a digit in the comment is text, not a severity.
    dialog.comment.setFocus()
    qtbot.keyClicks(dialog.comment, "4 items")
    assert dialog.severity() == "minor" and dialog.comment_text() == "4 items"
    assert dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).text() == "Add issue"


def test_a_profile_can_limit_the_categories_offered(qtbot):
    dialog = AddIssueDialog("", "target", categories=["accuracy", "terminology/wrong-term"])
    qtbot.addWidget(dialog)
    paths = [dialog.categories.item(i).data(Qt.ItemDataRole.UserRole) for i in range(dialog.categories.count())]
    assert "accuracy/omission" in paths and "terminology/wrong-term" in paths
    assert "style/awkward-style" not in paths and "terminology/inconsistent-use-of-terminology" not in paths


# ── Needs check ───────────────────────────────────────────────────────

def test_an_issue_whose_text_changed_needs_a_check_and_is_not_underlined(window, monkeypatch):
    controller = window_hooks.controller_of(window)
    monkeypatch.setattr(AddIssueDialog, "exec", lambda d: (d._select("style/awkward-style"),
                                                          AddIssueDialog.DialogCode.Accepted)[1])
    editor = window.table.cellWidget(1, 3)
    select(editor, "maintenant")
    issue = window_hooks.add_issue(window, editor)

    segment = window.current_project.segments[1]
    segment.target = "Cliquez <b>Enregistrer</b> tout de suite."
    editor.setPlainText(segment.target)
    controller.refresh([2])
    assert controller.is_stale(issue)
    assert editor.extraSelections() == []                              # the span is not moved silently
    assert (issue.start, issue.end) != (None, None)
    marker, tooltip = controller.status_marker(segment)
    assert marker == "m1?" and "needs check" in tooltip
    panel = window._ll_quality_panel
    assert "needs check" in panel.table.item(0, 4).text()
    panel.status_filter.setCurrentIndex(panel.status_filter.findData("needs-check"))
    assert panel.table.rowCount() == 1

    assert controller.recheck(issue.id) is True
    assert not controller.is_stale(issue) and issue.start is None
    assert controller.status_marker(segment)[0] == "m1"


# ── Scorecard, profile, report ────────────────────────────────────────

def test_the_scorecard_updates_live_and_shows_pass_and_fail(window):
    controller = window_hooks.controller_of(window)
    panel = window._ll_quality_panel
    assert "PASS" in panel.verdict_label.text()
    assert panel.score_values["score"].text() == "100.00"
    assert panel.score_values["words"].text() == "10"

    segment = window.current_project.segments[1]
    controller.add_issue(segment, side="target", start=0, end=7, category="accuracy/mistranslation",
                         severity="critical")
    # 25 penalty points in 10 words.
    assert "FAIL" in panel.verdict_label.text()
    assert panel.score_values["apt"].text() == "25.00"
    assert panel.category_table.rowCount() == 1
    assert panel.category_table.item(0, 0).text() == "Accuracy › Mistranslation"
    assert panel.category_table.item(0, 4).text() == "1"

    issue = controller.quality.issues.all()[0]
    controller.set_status(issue.id, "rejected")
    assert "PASS" in panel.verdict_label.text()
    controller.delete_issue(issue.id)
    assert panel.table.rowCount() == 0


def test_the_profile_tab_names_the_profile_and_its_numbers(window):
    panel = window._ll_quality_panel
    text = panel.profile_label.text()
    for needle in ("Profile: Default profile", "linear, calibrated", "neutral 0, minor 1, major 5, critical 25",
                   "Pass mark: 90", "The MQM Council", "critical = wavy (C)"):
        assert needle in text, needle
    quality = quality_of(window.current_project)
    quality.profile.name = "Client X"
    quality.profile.checks["qa.length"] = {"enabled": False}
    window_hooks.controller_of(window).changed.emit()
    assert "Profile: Client X" in panel.profile_label.text()
    assert "Checks switched off: qa.length" in panel.profile_label.text()


def test_export_report_from_the_panel(window, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: shown.append(a[2]))
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: shown.append("ERROR " + a[2]))
    window_hooks.run_qa(window)
    panel = window._ll_quality_panel
    for name in ("r.html", "r.json", "r.xlsx", "r.pdf"):
        panel.export_report(str(tmp_path / name))
        assert (tmp_path / name).stat().st_size > 500, name
    assert not any(text.startswith("ERROR") for text in shown)
    assert "Demo" in (tmp_path / "r.html").read_text(encoding="utf-8")
    panel.export_report(str(tmp_path / "r.docx"))
    assert shown[-1].startswith("ERROR")


# ── Marks ─────────────────────────────────────────────────────────────

def test_plain_to_display_skips_tags_compact_tags_and_direction_marks():
    assert marks.plain_to_display("a<b>bc</b>d") == [0, 4, 5, 10, 11]
    assert marks.plain_to_display("a{1}b{/1}", ["{1}", "{/1}"]) == [0, 4, 9]
    assert marks.plain_to_display("a{0}b") == [0, 1, 2, 3, 4, 5]        # {0} is text when it is no compact tag
    shown = rtl.protect_tags("نص <b>مهم</b>")
    positions = marks.plain_to_display(shown)
    assert "".join(shown[p] for p in positions[:-1]) == "نص مهم"


def test_each_severity_has_its_own_underline_and_letter():
    assert len(set(marks.UNDERLINE.values())) == 4 and len(set(marks.LETTER.values())) == 4


def test_underlines_in_a_right_to_left_cell(qtbot):
    segments = [seg(1, "Check the <b>pump</b>.", "افحص <b>الطلمبة</b> الآن.")]
    win = Window(segments, "en", "ar")
    qtbot.addWidget(win)
    try:
        controller = window_hooks.install(win)
        text = plain_text(segments[0].target)
        start = text.index("الطلمبة")
        controller.add_issue(segments[0], side="target", start=start, end=start + len("الطلمبة"),
                             category="terminology/wrong-term", severity="critical")
        (selection,) = win.table.cellWidget(0, 3).extraSelections()
        assert selection.cursor.selectedText() == "الطلمبة"
        assert selection.format.underlineStyle() == QTextCharFormat.UnderlineStyle.WaveUnderline
    finally:
        rtl.set_language_provider(None)


# ── AI pre-annotation (beta) ──────────────────────────────────────────

def _fake_ai(replies):
    """A stand-in for the configured AI: (provider, model, ask)."""
    calls = []

    def setup(_window):
        def ask(prompt):
            calls.append(prompt)
            return replies[min(len(calls), len(replies)) - 1], {"input_tokens": 50, "output_tokens": 10}
        return "ollama", "llama3", ask

    return setup, calls


def test_ai_pre_annotation_shows_where_text_goes_and_adds_open_proposals(window, qtbot, monkeypatch):
    import json
    from localizelarge.quality.ui.ai_dialog import AiAnnotateDialog
    controller = window_hooks.controller_of(window)
    window._where_text_goes = lambda provider=None: "Text stays on this computer"
    good = {"side": "target", "quote": "Enregistrer", "category": "accuracy/mistranslation",
            "severity": "major", "explanation": "Wrong verb.", "suggestion": "Sauvegarder"}
    invented = {**good, "quote": "words that are not there"}
    setup, calls = _fake_ai([json.dumps([]), json.dumps([good, invented])])
    seen = {}

    def fake_exec(dialog):
        seen["destination"] = dialog.destination.text()
        seen["scopes"] = {key: (radio.isEnabled(), radio.text()) for key, radio in dialog.scope.items()}
        dialog.scope["translated"].setChecked(True)
        dialog.begin()
        qtbot.waitUntil(lambda: dialog.summary is not None, timeout=10000)
        seen["result"] = dialog.result.text()
        return AiAnnotateDialog.DialogCode.Accepted

    monkeypatch.setattr(AiAnnotateDialog, "exec", fake_exec)
    summary = window_hooks.ai_annotate(window, setup)

    assert seen["destination"] == "Text stays on this computer"
    assert seen["scopes"]["translated"] == (True, "All translated segments (2)")
    assert seen["scopes"]["selected"][0] is False
    assert len(calls) == 2                                             # the untranslated segment is not sent
    assert (summary.issues_kept, summary.issues_dropped, summary.segments) == (1, 1, 2)
    assert "Proposals dropped" in seen["result"] and "kept: 1" in seen["result"]

    (issue,) = controller.quality.issues.all()
    assert (issue.origin, issue.status, issue.author, issue.segment_id) == ("ai", "open", "AI: ollama/llama3", 2)
    assert issue.quoted(window.current_project.segments[1].target) == "Enregistrer"
    # Not counted until a person accepts it.
    assert controller.score().absolute_penalty_total == 0
    controller.set_status(issue.id, "accepted")
    assert controller.score().absolute_penalty_total == 5
    # The run is recorded for the report.
    report = controller.build_report()
    assert report["ai"][0]["provider"] == "ollama" and report["ai"][0]["issuesDropped"] == 1
    assert report["ai"][0]["inputTokens"] == 100 and report["ai"][0]["estimatedCostUsd"] == 0.0
    assert window._ll_quality_panel.table.item(0, 3).text() == "AI (beta)"


def test_a_second_ai_run_replaces_open_proposals_but_keeps_decided_ones(window):
    from localizelarge.mqm.ai_annotate import RunSummary
    from localizelarge.quality.model import make_issue
    controller = window_hooks.controller_of(window)
    segment = window.current_project.segments[1]

    def proposal(message):
        return make_issue(segment, origin="ai", rule_id="mqm", category="style/awkward-style",
                          severity="minor", message=message, author="AI: ollama/llama3")

    first, second = proposal("first"), proposal("second")
    controller.add_ai_results([first, second], RunSummary("ollama", "llama3"))
    controller.set_status(first.id, "rejected")
    controller.add_ai_results([proposal("third")], RunSummary("ollama", "llama3"))
    assert sorted(i.message for i in controller.quality.issues) == ["first", "third"]
    assert len(controller.ai_runs) == 2


def test_ai_pre_annotation_needs_a_configured_provider(window, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: shown.append(a[2]))

    def no_key(_window):
        raise RuntimeError("There is no API key for claude. Add it in Settings → AI.")

    assert window_hooks.ai_annotate(window, no_key) is None
    assert shown == ["There is no API key for claude. Add it in Settings → AI."]
    assert len(window_hooks.controller_of(window).quality.issues) == 0


def test_the_ai_action_is_in_the_qa_menu_and_marked_beta(window):
    texts = [a.text() for a in window.qa_menu.actions() if a.text()]
    assert "AI pre-annotation (&beta)…" in texts
