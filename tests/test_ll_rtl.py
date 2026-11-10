"""Phase 4: right-to-left targets (Arabic, Hebrew, Persian, Urdu).

The target editor and the grid cells lay text out from the right; Latin words, numbers
and inline tags inside right-to-left text stay readable; and the marks used to keep
tags readable never leave the editor.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytest.importorskip("PyQt6")

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtWidgets import QTextEdit  # noqa: E402

from localizelarge import rtl  # noqa: E402

ARABIC = "اضغط <b>حفظ</b> ثم افتح الصفحة 2024 في Settings."


@pytest.fixture
def languages():
    """Set the "open project's" languages for a test; none afterwards."""
    current = {"pair": ("", "")}
    rtl.set_language_provider(lambda: current["pair"])
    yield lambda source, target: current.__setitem__("pair", (source, target))
    rtl.set_language_provider(None)


class TargetEdit(rtl.DirectionMixin, QTextEdit):
    ll_side = "target"


class SourceEdit(rtl.DirectionMixin, QTextEdit):
    ll_side = "source"


# ── Which languages ───────────────────────────────────────────────────

@pytest.mark.parametrize("language", ["ar", "ar-EG", "AR_sa", "he", "iw", "fa", "fa-IR", "ur",
                                      "Arabic", "Hebrew", "Persian", "Urdu", "Arabic (Egypt)"])
def test_right_to_left_languages(language):
    assert rtl.is_rtl(language)


@pytest.mark.parametrize("language", ["en", "fr-FR", "zh-CN", "ja", "de", "English", "", None,
                                      "arn", "Aragonese"])
def test_left_to_right_languages(language):
    assert not rtl.is_rtl(language)


# ── Tag protection is display only ────────────────────────────────────

def test_protect_and_unprotect_are_exact_opposites():
    for text in (ARABIC, "{1}نص{/1} و {2/}", "<bmk id=\"0\" name=\"a b\">نص</bmk>", "no tags",
                 "", "a < b and c > d", "x‎y"):
        shown = rtl.protect_tags(text)
        assert rtl.unprotect_tags(shown) == text
        assert rtl.protect_tags(shown) == shown          # protecting twice changes nothing
    assert rtl.protect_tags("<b>نص</b>") == "‎<b>‎نص‎</b>‎"
    assert rtl.protect_tags("a < b and c > d") == "a < b and c > d"   # not a tag


# ── The editors ───────────────────────────────────────────────────────

def test_target_editor_is_right_to_left_for_an_arabic_target(qtbot, languages):
    languages("en", "ar")
    editor = TargetEdit()
    qtbot.addWidget(editor)
    editor.setPlainText(ARABIC)
    option = editor.document().defaultTextOption()
    assert option.textDirection() == Qt.LayoutDirection.RightToLeft
    assert option.alignment() & Qt.AlignmentFlag.AlignRight
    # What the app reads back is exactly what was put in: no marks.
    assert editor.toPlainText() == ARABIC
    assert "‎" in QTextEdit.toPlainText(editor)

    # The source of the same project is English: left to right, untouched.
    source = SourceEdit()
    qtbot.addWidget(source)
    source.setPlainText("Click <b>Save</b>.")
    assert source.document().defaultTextOption().textDirection() == Qt.LayoutDirection.LeftToRight
    assert QTextEdit.toPlainText(source) == "Click <b>Save</b>."


def test_source_editor_is_right_to_left_for_an_arabic_source(qtbot, languages):
    languages("ar-EG", "en")
    source, target = SourceEdit(), TargetEdit()
    qtbot.addWidget(source)
    qtbot.addWidget(target)
    source.setPlainText(ARABIC)
    target.setPlainText("Press <b>Save</b>.")
    assert source.document().defaultTextOption().textDirection() == Qt.LayoutDirection.RightToLeft
    assert target.document().defaultTextOption().textDirection() == Qt.LayoutDirection.LeftToRight
    assert source.toPlainText() == ARABIC


def test_an_editor_follows_a_change_of_project_language(qtbot, languages):
    editor = TargetEdit()
    qtbot.addWidget(editor)
    languages("en", "fr")
    editor.setPlainText("Bonjour <b>le</b> monde")
    assert editor.document().defaultTextOption().textDirection() == Qt.LayoutDirection.LeftToRight
    assert "‎" not in QTextEdit.toPlainText(editor)
    languages("en", "he")
    editor.setPlainText("שלום <b>עולם</b>")
    assert editor.document().defaultTextOption().textDirection() == Qt.LayoutDirection.RightToLeft
    assert editor.toPlainText() == "שלום <b>עולם</b>"


def test_typed_text_is_read_back_without_marks(qtbot, languages):
    languages("en", "ur")
    editor = TargetEdit()
    qtbot.addWidget(editor)
    editor.setPlainText("متن <b>اہم</b>")
    cursor = editor.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    cursor.insertText(" 42 <i>نیا</i>")
    assert editor.toPlainText() == "متن <b>اہم</b> 42 <i>نیا</i>"


def _x_positions(editor, text, piece):
    """The x positions inside ``piece`` as drawn in the editor, in text order."""
    shown = QTextEdit.toPlainText(editor)
    start = shown.index(piece)
    block = editor.document().firstBlock()
    layout = block.layout()
    line = layout.lineForTextPosition(start)
    # Positions between the characters of the piece. The two outer edges are left out:
    # where a left-to-right run meets right-to-left text a cursor has two places.
    return [line.cursorToX(start + i)[0] for i in range(1, len(piece))]


def test_tags_and_numbers_read_left_to_right_inside_arabic_text(qtbot, languages):
    languages("en", "ar")
    editor = TargetEdit()
    qtbot.addWidget(editor)
    editor.resize(900, 120)
    editor.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
    editor.setPlainText(ARABIC)
    editor.show()
    qtbot.waitExposed(editor)

    # Each of these must be drawn left to right: "<" before "/" before "b" before ">".
    for piece in ("<b>", "</b>", "2024", "Settings"):
        xs = _x_positions(editor, ARABIC, piece)
        assert xs == sorted(xs) and xs[0] < xs[-1], (piece, xs)

    # The paragraph itself runs right to left: the first Arabic word is drawn to the
    # right of the last Latin word.
    first_word = _x_positions(editor, ARABIC, "اضغط")
    last_word = _x_positions(editor, ARABIC, "Settings")
    assert min(first_word) > max(last_word)


def test_without_the_marks_a_closing_tag_would_be_drawn_backwards(qtbot, languages):
    """Why the marks are needed: this is what plain Qt does with the same text."""
    languages("en", "ar")
    plain = QTextEdit()
    qtbot.addWidget(plain)
    plain.resize(900, 120)
    plain.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
    rtl.apply_direction(plain, True)
    plain.setPlainText(ARABIC)
    plain.show()
    qtbot.waitExposed(plain)
    xs = _x_positions(plain, ARABIC, "</b>")
    assert xs != sorted(xs)


# ── The grid's own editor classes ─────────────────────────────────────

def test_the_grid_editor_classes_use_the_direction_mixin():
    import ast
    from pathlib import Path
    tree = ast.parse((Path(__file__).resolve().parent.parent / "Supervertaler.py").read_text(encoding="utf-8"))
    bases = {node.name: [ast.unparse(b) for b in node.bases]
             for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
    assert bases["EditableGridTextEditor"][0] == "_ll_rtl.DirectionMixin"
    assert bases["ReadOnlyGridTextEditor"][0] == "_ll_rtl.DirectionMixin"


@pytest.fixture(scope="module")
def app_module():
    from PyQt6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    saved = sys.stdout, sys.stderr
    import Supervertaler   # re-wraps stdout/stderr on Windows at import
    app_module._wrappers = sys.stdout, sys.stderr   # keep alive, as in test_main_window_close
    sys.stdout, sys.stderr = saved
    return Supervertaler


def test_the_real_grid_cells_are_right_to_left_for_an_arabic_target(qtbot, languages, app_module):
    languages("en", "ar")
    source = app_module.ReadOnlyGridTextEditor("Press <b>Save</b> on page 2024.", None, 0)
    target = app_module.EditableGridTextEditor(ARABIC, None, 0, None)
    qtbot.addWidget(source)
    qtbot.addWidget(target)

    option = target.document().defaultTextOption()
    assert option.textDirection() == Qt.LayoutDirection.RightToLeft
    assert option.alignment() & Qt.AlignmentFlag.AlignRight
    assert target.toPlainText() == ARABIC
    assert source.document().defaultTextOption().textDirection() == Qt.LayoutDirection.LeftToRight
    assert source.toPlainText() == "Press <b>Save</b> on page 2024."

    # A later update of the cell (as after an AI translation) keeps the direction.
    target.setPlainText("نص <i>جديد</i> 15")
    assert target.document().defaultTextOption().textDirection() == Qt.LayoutDirection.RightToLeft
    assert target.toPlainText() == "نص <i>جديد</i> 15"


def test_the_real_grid_cells_stay_left_to_right_for_a_french_target(qtbot, languages, app_module):
    languages("en", "fr")
    target = app_module.EditableGridTextEditor("Appuyez sur <b>Enregistrer</b>.", None, 0, None)
    qtbot.addWidget(target)
    assert target.document().defaultTextOption().textDirection() == Qt.LayoutDirection.LeftToRight
    assert QTextEdit.toPlainText(target) == "Appuyez sur <b>Enregistrer</b>."
