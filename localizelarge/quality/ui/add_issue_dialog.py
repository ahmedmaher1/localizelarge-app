"""The "Add issue" panel: pick an MQM category, a severity, and write a comment and an
optional suggested fix. Keys 1 to 4 choose the severity."""
from __future__ import annotations

from typing import List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QButtonGroup, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPlainTextEdit, QPushButton, QVBoxLayout,
)

from localizelarge.mqm import typology

from .marks import LETTER, UNDERLINE_NAME

SEVERITIES = ("neutral", "minor", "major", "critical")


class AddIssueDialog(QDialog):
    def __init__(self, quote: str, side: str, parent=None, categories: Optional[List[str]] = None,
                 category: str = "", severity: str = "minor", comment: str = "", suggestion: str = "",
                 title: str = "Add issue"):
        super().__init__(parent)
        self.setObjectName("addIssueDialog")
        self.setWindowTitle(title)
        self.setMinimumSize(520, 560)
        layout = QVBoxLayout(self)

        where = "source" if side == "source" else "target"
        shown = quote if len(quote) <= 120 else quote[:117] + "…"
        self.quote_label = QLabel(f"Selected in the {where}: “{shown}”" if quote
                                  else f"No text selected: the issue is for the whole {where}.")
        self.quote_label.setObjectName("addIssueQuote")
        self.quote_label.setWordWrap(True)
        layout.addWidget(self.quote_label)

        layout.addWidget(QLabel("Category (type to search):"))
        self.search = QLineEdit()
        self.search.setObjectName("addIssueSearch")
        self.search.setPlaceholderText("for example: omission, grammar, term")
        self.search.textChanged.connect(self._filter)
        layout.addWidget(self.search)

        self.categories = QListWidget()
        self.categories.setObjectName("addIssueCategories")
        allowed = set(categories) if categories else None
        for item in typology.categories():
            if allowed is not None and item.path not in allowed and item.dimension not in allowed:
                continue
            row = QListWidgetItem(("" if "/" not in item.path else "      ") + item.name)
            row.setData(Qt.ItemDataRole.UserRole, item.path)
            row.setData(Qt.ItemDataRole.UserRole + 1, f"{item.label} {item.definition}".casefold())
            row.setToolTip(item.definition)
            if "/" not in item.path:
                font = row.font()
                font.setBold(True)
                row.setFont(font)
            self.categories.addItem(row)
        self.categories.currentItemChanged.connect(self._show_definition)
        self.categories.itemDoubleClicked.connect(lambda _item: self._accept())
        layout.addWidget(self.categories, 1)

        self.definition = QLabel("")
        self.definition.setObjectName("addIssueDefinition")
        self.definition.setWordWrap(True)
        layout.addWidget(self.definition)

        layout.addWidget(QLabel("Severity (keys 1 to 4):"))
        row = QHBoxLayout()
        self.severity_group = QButtonGroup(self)
        self.severity_buttons = {}
        for number, name in enumerate(SEVERITIES, 1):
            button = QPushButton(f"{number}  {name.capitalize()}  [{LETTER[name]}]")
            button.setObjectName(f"addIssueSeverity_{name}")
            button.setCheckable(True)
            button.setToolTip(f"{name.capitalize()}: {UNDERLINE_NAME[name]} underline, letter {LETTER[name]}")
            self.severity_group.addButton(button, number)
            self.severity_buttons[name] = button
            row.addWidget(button)
            shortcut = QShortcut(QKeySequence(f"Alt+{number}"), self)
            shortcut.activated.connect(button.click)
        layout.addLayout(row)

        layout.addWidget(QLabel("Comment:"))
        self.comment = QPlainTextEdit(comment)
        self.comment.setObjectName("addIssueComment")
        self.comment.setMaximumHeight(70)
        self.comment.setTabChangesFocus(True)
        layout.addWidget(self.comment)

        layout.addWidget(QLabel("Suggested fix (optional):"))
        self.suggestion = QLineEdit(suggestion)
        self.suggestion.setObjectName("addIssueSuggestion")
        layout.addWidget(self.suggestion)

        self.problem = QLabel("")
        self.problem.setObjectName("addIssueProblem")
        layout.addWidget(self.problem)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText(title)
        self.buttons.accepted.connect(self._accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self.severity_buttons.get(severity, self.severity_buttons["minor"]).setChecked(True)
        self._select(category)
        self.search.setFocus()

    # Keys 1–4 pick the severity unless the user is typing in a text field.
    def keyPressEvent(self, event):  # noqa: N802 (Qt name)
        typing = self.comment.hasFocus() or self.suggestion.hasFocus() or self.search.hasFocus()
        if not typing and event.text() in ("1", "2", "3", "4"):
            self.severity_buttons[SEVERITIES[int(event.text()) - 1]].click()
            return
        if self.search.hasFocus() and event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up):
            self._move(1 if event.key() == Qt.Key.Key_Down else -1)
            return
        super().keyPressEvent(event)

    def _visible_rows(self) -> List[int]:
        return [i for i in range(self.categories.count()) if not self.categories.item(i).isHidden()]

    def _move(self, step: int):
        rows = self._visible_rows()
        if not rows:
            return
        current = self.categories.currentRow()
        position = rows.index(current) if current in rows else -1
        self.categories.setCurrentRow(rows[max(0, min(len(rows) - 1, position + step))])

    def _filter(self, text: str):
        words = text.casefold().split()
        first = None
        for index in range(self.categories.count()):
            item = self.categories.item(index)
            haystack = item.data(Qt.ItemDataRole.UserRole + 1)
            hidden = bool(words) and not all(word in haystack for word in words)
            item.setHidden(hidden)
            if not hidden and first is None and (not words or "/" in item.data(Qt.ItemDataRole.UserRole)):
                first = index
        if words and first is not None:
            self.categories.setCurrentRow(first)

    def _select(self, path: str):
        for index in range(self.categories.count()):
            if self.categories.item(index).data(Qt.ItemDataRole.UserRole) == path:
                self.categories.setCurrentRow(index)
                return

    def _show_definition(self, item, _previous=None):
        self.definition.setText(item.toolTip() if item is not None else "")
        self.problem.setText("")

    def _accept(self):
        if not self.category():
            self.problem.setText("Choose a category.")
            return
        self.accept()

    # ── what was chosen ────────────────────────────────────────────
    def category(self) -> str:
        item = self.categories.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None and not item.isHidden() else ""

    def severity(self) -> str:
        checked = self.severity_group.checkedId()
        return SEVERITIES[checked - 1] if checked > 0 else "minor"

    def comment_text(self) -> str:
        return self.comment.toPlainText().strip()

    def suggestion_text(self) -> str:
        return self.suggestion.text().strip()
