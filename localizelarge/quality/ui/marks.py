"""How issues show in the editor and in the grid's status column.

Each severity has its own underline pattern and its own letter, so that nothing depends
on colour alone:

=========  ==================  ======
Severity   Underline           Letter
=========  ==================  ======
Neutral    dotted              N
Minor      dashed              m
Major      solid               M
Critical   wavy                C
=========  ==================  ======

An issue whose text changed since it was made ("needs check") is not underlined: its
span may no longer be right. It shows in the status column with a question mark.
"""
from __future__ import annotations

import re
from typing import Iterable, List, Optional, Tuple

from PyQt6.QtGui import QColor, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import QTextEdit

from localizelarge.rtl import LRM

SEVERITY_ORDER = ("neutral", "minor", "major", "critical")
LETTER = {"neutral": "N", "minor": "m", "major": "M", "critical": "C"}
COLOR = {"neutral": "#52606d", "minor": "#b7791f", "major": "#c2410c", "critical": "#b91c1c"}
UNDERLINE = {
    "neutral": QTextCharFormat.UnderlineStyle.DotLine,
    "minor": QTextCharFormat.UnderlineStyle.DashUnderline,
    "major": QTextCharFormat.UnderlineStyle.SingleUnderline,
    "critical": QTextCharFormat.UnderlineStyle.WaveUnderline,
}
UNDERLINE_NAME = {"neutral": "dotted", "minor": "dashed", "major": "solid", "critical": "wavy"}

_TAG = re.compile(r"<[^<>\s][^<>\n]{0,200}>")


def plain_to_display(display_text: str, compact_tags: Optional[Iterable[str]] = None) -> List[int]:
    """For each character of the plain text (tags removed), its position in the text an
    editor shows. The editor may show tags, compact tags such as {1}, and the
    left-to-right marks put around tags in right-to-left text; none of those count.

    The list has one more entry at the end: the position after the last character.
    """
    skip = [(m.start(), m.end()) for m in _TAG.finditer(display_text)]
    for token in sorted(set(compact_tags or ()), key=len, reverse=True):
        start = display_text.find(token)
        while start >= 0:
            skip.append((start, start + len(token)))
            start = display_text.find(token, start + len(token))
    skip.sort()
    positions: List[int] = []
    index, next_skip = 0, 0
    while index < len(display_text):
        while next_skip < len(skip) and skip[next_skip][1] <= index:
            next_skip += 1
        if next_skip < len(skip) and skip[next_skip][0] <= index < skip[next_skip][1]:
            index = skip[next_skip][1]
            continue
        if display_text[index] == LRM and (
                (index + 1 < len(display_text) and display_text[index + 1] in "<{")
                or (index > 0 and display_text[index - 1] in ">}")):
            index += 1
            continue
        positions.append(index)
        index += 1
    positions.append(len(display_text))
    return positions


def selections_for(editor: QTextEdit, issues: Iterable, side: str, side_text: str) -> list:
    """Extra selections that underline the spans of a segment's issues in an editor."""
    display = QTextEdit.toPlainText(editor)
    compact = list((getattr(editor, "_compact_tag_map", None) or {}).keys())
    positions = plain_to_display(display, compact)
    plain_length = len(positions) - 1
    out = []
    for issue in sorted(issues, key=lambda i: SEVERITY_ORDER.index(i.severity)):
        if issue.side != side or issue.start is None or issue.status in ("rejected", "fixed"):
            continue
        if issue.is_stale(side_text) or issue.end > plain_length or issue.start >= issue.end:
            continue
        selection = QTextEdit.ExtraSelection()
        cursor = QTextCursor(editor.document())
        cursor.setPosition(positions[issue.start])
        cursor.setPosition(positions[issue.end - 1] + 1, QTextCursor.MoveMode.KeepAnchor)
        selection.cursor = cursor
        fmt = QTextCharFormat()
        fmt.setUnderlineStyle(UNDERLINE[issue.severity])
        fmt.setUnderlineColor(QColor(COLOR[issue.severity]))
        fmt.setToolTip(issue.message)
        selection.format = fmt
        out.append(selection)
    return out


def summary(issues: Iterable, source_text: str, target_text: str) -> Tuple[str, str]:
    """(marker text, tooltip) for the status column of a segment, or ("", "").

    The marker is the letter of the worst severity and the number of issues, for example
    "M2"; "?" is added when an issue needs a check.
    """
    active = [i for i in issues if i.status in ("open", "accepted")]
    if not active:
        return "", ""
    worst = max(active, key=lambda i: SEVERITY_ORDER.index(i.severity)).severity
    stale = any(i.is_stale(source_text if i.side == "source" else target_text) for i in active)
    marker = f"{LETTER[worst]}{len(active)}" + ("?" if stale else "")
    lines = [f"{len(active)} quality issue(s); worst: {worst}"]
    for issue in active[:6]:
        note = " (needs check: the text changed)" if issue.is_stale(
            source_text if issue.side == "source" else target_text) else ""
        lines.append(f"[{LETTER[issue.severity]}] {issue.message}{note}")
    if len(active) > 6:
        lines.append(f"… and {len(active) - 6} more")
    return marker, "\n".join(lines)
