"""The glossary import and export dialogs for TBX, XLSX and CSV.

The main window's Glossaries tab calls ``import_file`` and ``export_tbx``; TSV keeps its
existing importer.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QMessageBox,
    QProgressDialog, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from . import store, tabular, tbx

IMPORT_FILTER = ("Glossary files (*.tbx *.xlsx *.csv *.tsv *.txt);;TBX (*.tbx);;"
                 "Excel (*.xlsx);;CSV (*.csv);;TSV (*.tsv *.txt);;All Files (*.*)")
EXPORT_FILTER = "TSV Files (*.tsv);;TBX (*.tbx);;Text Files (*.txt);;All Files (*.*)"
_OWN_IMPORT = (".tbx", ".xlsx", ".xlsm", ".csv")
NOT_USED = "(not used)"


def handles_import(path: str) -> bool:
    """True for the files this module imports (TBX, XLSX, CSV)."""
    return os.path.splitext(str(path))[1].lower() in _OWN_IMPORT


def is_tbx(path: str) -> bool:
    return os.path.splitext(str(path))[1].lower() == ".tbx"


class ColumnMappingDialog(QDialog):
    """Shows the first rows of a spreadsheet and asks which column is which field."""

    def __init__(self, headers: List[str], rows: List[List[str]], mapping: Dict[str, int],
                 parent=None):
        super().__init__(parent)
        self.setObjectName("glossaryColumnMappingDialog")
        self.setWindowTitle("Import glossary – choose the columns")
        self.setMinimumWidth(640)
        self._headers = headers
        layout = QVBoxLayout(self)

        intro = QLabel("Choose which column holds each kind of information. Source term and "
                       "target term are needed; the rest is optional. Several variants in one "
                       "cell are separated by ; or |.")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        self.combos: Dict[str, QComboBox] = {}
        for key, label in tabular.FIELDS:
            combo = QComboBox()
            combo.setObjectName(f"glossaryColumn_{key}")
            combo.addItem(NOT_USED, -1)
            for index, header in enumerate(headers):
                combo.addItem(f"{index + 1}: {header}", index)
            combo.setCurrentIndex(mapping.get(key, -1) + 1)
            combo.currentIndexChanged.connect(self._update_state)
            self.combos[key] = combo
            form.addRow(label + (" *" if key in tabular.REQUIRED else "") + ":", combo)
        layout.addLayout(form)

        layout.addWidget(QLabel(f"First rows of the file ({len(rows)} rows in all):"))
        preview = QTableWidget(min(len(rows), 8), len(headers))
        preview.setObjectName("glossaryColumnPreview")
        preview.setHorizontalHeaderLabels(headers)
        preview.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for r, row in enumerate(rows[:8]):
            for c, cell in enumerate(row[:len(headers)]):
                preview.setItem(r, c, QTableWidgetItem(cell))
        preview.resizeColumnsToContents()
        layout.addWidget(preview)

        self.problem = QLabel("")
        self.problem.setObjectName("glossaryColumnProblem")
        self.problem.setWordWrap(True)
        layout.addWidget(self.problem)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Import")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self._update_state()

    def mapping(self) -> Dict[str, int]:
        """Field key → column index for the fields that have a column."""
        chosen = {}
        for key, combo in self.combos.items():
            index = combo.currentData()
            if index is not None and index >= 0:
                chosen[key] = index
        return chosen

    def _problem_text(self) -> str:
        chosen = self.mapping()
        missing = [label for key, label in tabular.FIELDS
                   if key in tabular.REQUIRED and key not in chosen]
        if missing:
            return "Choose a column for: " + ", ".join(missing) + "."
        if chosen["source"] == chosen["target"]:
            return "Source term and target term cannot be the same column."
        return ""

    def _update_state(self):
        text = self._problem_text()
        self.problem.setText(text)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(not text)


class TbxLanguagesDialog(QDialog):
    """Asks which two languages of a TBX file to import."""

    def __init__(self, languages: List[str], source: str, target: str, parent=None):
        super().__init__(parent)
        self.setObjectName("glossaryTbxLanguagesDialog")
        self.setWindowTitle("Import TBX – choose the languages")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("This TBX file holds these languages: " + ", ".join(languages)))
        form = QFormLayout()
        self.source = QComboBox()
        self.source.setObjectName("glossaryTbxSource")
        self.target = QComboBox()
        self.target.setObjectName("glossaryTbxTarget")
        for combo, current in ((self.source, source), (self.target, target)):
            combo.addItems(languages)
            if current in languages:
                combo.setCurrentText(current)
        form.addRow("Source language:", self.source)
        form.addRow("Target language:", self.target)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept(self):
        if self.source.currentText() == self.target.currentText():
            QMessageBox.warning(self, "Import TBX", "Choose two different languages.")
            return
        self.accept()


def _same_language(a: str, b: str) -> bool:
    def base(code):
        return (code or "").replace("_", "-").split("-")[0].lower()
    return bool(a) and base(a) == base(b)


def _entries_from_file(parent, path: str, source_lang: str, target_lang: str):
    """The entries of a file, after asking what has to be asked. None when cancelled."""
    if is_tbx(path):
        languages = tbx.languages_in(path)
        if len(languages) < 2:
            QMessageBox.warning(parent, "Import glossary",
                                "This TBX file has terms in fewer than two languages.")
            return None
        probe = tbx.read_tbx(path, source_lang or None, target_lang or None)
        source, target = probe.source_lang, probe.target_lang
        exact = _same_language(source, source_lang) and _same_language(target, target_lang)
        if not exact:
            dialog = TbxLanguagesDialog(languages, source, target, parent)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return None
            probe = tbx.read_tbx(path, dialog.source.currentText(), dialog.target.currentText())
        return probe.entries, probe.skipped

    headers, rows = tabular.read_table(path)
    if not headers or not rows:
        QMessageBox.warning(parent, "Import glossary", "This file has no rows to import.")
        return None
    dialog = ColumnMappingDialog(headers, rows, tabular.guess_mapping(headers, source_lang, target_lang),
                                 parent)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return tabular.to_entries(rows, dialog.mapping())


def import_file(parent, termbase_mgr, termbase_id: int, path: str) -> Optional[store.ImportReport]:
    """Import a TBX, XLSX or CSV file into a termbase. Returns the report, or None when
    the user cancelled or the file could not be read."""
    info = termbase_mgr.get_termbase(termbase_id) or {}
    source_lang = info.get("source_lang") or ""
    target_lang = info.get("target_lang") or ""
    try:
        found = _entries_from_file(parent, path, source_lang, target_lang)
    except Exception as error:
        QMessageBox.critical(parent, "Import glossary",
                             f"The file could not be read:\n{error}")
        return None
    if found is None:
        return None
    entries, skipped = found
    if not entries:
        QMessageBox.information(parent, "Import glossary",
                                "No entry with both a source term and a target term was found.")
        return None

    progress = QProgressDialog("Importing glossary…", None, 0, len(entries), parent)
    progress.setWindowModality(Qt.WindowModality.WindowModal)
    progress.setMinimumDuration(400)

    def step(done, _total):
        progress.setValue(done)
        QApplication.processEvents()

    try:
        report = store.import_entries(termbase_mgr, termbase_id, entries,
                                      source_lang or None, target_lang or None, progress=step)
    finally:
        progress.close()

    lines = [f"Added: {report.added}", f"Already there (variants and details merged): {report.merged}"]
    if skipped:
        lines.append(f"Skipped (no term in one of the two languages): {skipped}")
    if report.failed:
        lines.append(f"Could not be saved: {report.failed}")
    QMessageBox.information(parent, "Import glossary", "\n".join(lines))
    return report


def export_tbx(parent, termbase_mgr, termbase_id: int, path: str) -> bool:
    """Export a termbase as TBX-Basic."""
    info = termbase_mgr.get_termbase(termbase_id) or {}
    try:
        entries = store.export_entries(termbase_mgr, termbase_id)
        written = tbx.write_tbx(path, entries, info.get("source_lang") or "en",
                                info.get("target_lang") or "und", info.get("name") or "Glossary")
    except Exception as error:
        QMessageBox.critical(parent, "Export glossary", f"The TBX file could not be written:\n{error}")
        return False
    QMessageBox.information(parent, "Export glossary",
                            f"{written} entries were written to\n{path}")
    return True
