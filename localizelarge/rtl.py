"""Right-to-left text in the editors.

For Arabic, Hebrew, Persian and Urdu (and other right-to-left languages) an editor lays
its text out from the right and aligns it right. Unicode's bidirectional rules then put
Latin words and numbers inside the text in the right order.

Inline tags need help. A tag such as ``</b>`` or ``{/1}`` is made of brackets and a
slash, which have no direction of their own; in a right-to-left paragraph they would be
drawn mirrored and in reverse order ("<b/>"). To keep a tag readable, the editor shows it
between two left-to-right marks (U+200E). The marks are display only: ``toPlainText``
takes them out again, so they never reach the project, the translation memory or an
export.
"""
from __future__ import annotations

import re
from typing import Callable, Optional, Tuple

LRM = "‎"

_RTL_CODES = {"ar", "he", "iw", "fa", "ur", "ps", "sd", "ug", "yi", "dv", "ckb", "syr", "nqo"}
_RTL_NAMES = {"arabic", "hebrew", "persian", "farsi", "urdu", "pashto", "sindhi", "uyghur",
              "uighur", "yiddish", "dhivehi", "sorani", "central kurdish", "syriac"}

# What counts as a tag in an editor: <b>, </g1>, <x1/>, <bmk id="0">, and the compact
# forms {1}, {/1}, {1/}. "a < b" is not a tag (a tag has no space after "<").
_TAG = re.compile(r"<[^<>\s][^<>\n]{0,200}>|\{/?\d+/?\}")
_PROTECTED = re.compile(LRM + r"(<[^<>\s][^<>\n]{0,200}>|\{/?\d+/?\})" + LRM)

_provider: Optional[Callable[[], Tuple[str, str]]] = None


def is_rtl(language: Optional[str]) -> bool:
    """True for a right-to-left language, given as a code ("ar", "ar-EG", "he_IL") or
    an English name ("Arabic", "Persian (Iran)")."""
    if not language:
        return False
    text = str(language).strip().lower()
    code = text.replace("_", "-").split("-")[0]
    if code in _RTL_CODES:
        return True
    name = text.split("(")[0].strip()
    return name in _RTL_NAMES


def set_language_provider(provider: Optional[Callable[[], Tuple[str, str]]]) -> None:
    """Tell this module how to learn the open project's (source, target) languages."""
    global _provider
    _provider = provider


def side_is_rtl(side: str) -> bool:
    """True when the open project's source ("source") or target ("target") language is
    written right to left. False when no project is open."""
    if _provider is None:
        return False
    try:
        source, target = _provider()
    except Exception:
        return False
    return is_rtl(source if side == "source" else target)


def protect_tags(text: str) -> str:
    """Put a left-to-right mark on each side of every tag, for display."""
    if not text:
        return text
    return _TAG.sub(lambda m: f"{LRM}{m.group(0)}{LRM}", unprotect_tags(text))


def unprotect_tags(text: str) -> str:
    """Take the display marks out again."""
    if not text or LRM not in text:
        return text
    return _PROTECTED.sub(r"\1", text)


def apply_direction(editor, rtl: bool) -> None:
    """Set the base direction and alignment of a QTextEdit's document."""
    from PyQt6.QtCore import Qt
    option = editor.document().defaultTextOption()
    wanted = Qt.LayoutDirection.RightToLeft if rtl else Qt.LayoutDirection.LeftToRight
    alignment = (Qt.AlignmentFlag.AlignRight if rtl else Qt.AlignmentFlag.AlignLeft) \
        | Qt.AlignmentFlag.AlignAbsolute
    if option.textDirection() != wanted or option.alignment() != alignment:
        option.setTextDirection(wanted)
        option.setAlignment(alignment)
        editor.document().setDefaultTextOption(option)


class DirectionMixin:
    """For QTextEdit subclasses that show source or target text.

    Put it before QTextEdit in the bases and set ``ll_side`` to "source" or "target".
    """
    ll_side = "target"

    def ll_is_rtl(self) -> bool:
        return side_is_rtl(self.ll_side)

    def setPlainText(self, text):  # noqa: N802 (Qt name)
        rtl = self.ll_is_rtl()
        apply_direction(self, rtl)
        super().setPlainText(protect_tags(text) if rtl else text)

    def toPlainText(self):  # noqa: N802 (Qt name)
        return unprotect_tags(super().toPlainText())


def make_text_edit(side: str):
    """A plain QTextEdit that follows the direction of the project's source or target."""
    from PyQt6.QtWidgets import QTextEdit

    class DirectionalTextEdit(DirectionMixin, QTextEdit):
        ll_side = side

    return DirectionalTextEdit()
