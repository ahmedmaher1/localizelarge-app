"""The AI pre-annotation dialog (beta): which segments, where the text goes, progress
with Cancel, and a summary of what was kept and what was dropped."""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from PyQt6.QtCore import QThread, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QLabel, QProgressBar, QRadioButton, QVBoxLayout,
)

from localizelarge.mqm import ai_annotate


class AnnotateWorker(QThread):
    """Runs ``ai_annotate.annotate`` off the main thread."""
    progress = pyqtSignal(int, int)
    done = pyqtSignal(object, object)        # issues, summary

    def __init__(self, segments: Sequence[Any], ask: Callable[[str], Tuple[str, Dict[str, Any]]],
                 options: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.segments = list(segments)
        self.ask = ask
        self.options = options
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        issues, summary = ai_annotate.annotate(
            self.segments, self.ask, progress=self.progress.emit,
            cancelled=lambda: self._cancel, **self.options)
        self.done.emit(issues, summary)


class AiAnnotateDialog(QDialog):
    """Asks what to send, says where it goes, and runs the annotation."""

    def __init__(self, parent, *, destination: str, provider: str, model: str,
                 counts: Dict[str, int], start: Callable[[str], AnnotateWorker]):
        super().__init__(parent)
        self.setObjectName("aiAnnotateDialog")
        self.setWindowTitle("AI pre-annotation (beta)")
        self.setMinimumWidth(520)
        self._start = start
        self.worker: Optional[AnnotateWorker] = None
        self.issues: List = []
        self.summary = None
        layout = QVBoxLayout(self)

        # Where the text goes comes first.
        self.destination = QLabel(destination)
        self.destination.setObjectName("aiAnnotateDestination")
        self.destination.setStyleSheet("font-weight: bold; padding: 6px; border: 1px solid #52606d;")
        self.destination.setWordWrap(True)
        layout.addWidget(self.destination)
        layout.addWidget(QLabel(f"Provider: {provider}     Model: {model}"))

        intro = QLabel("The AI reads each chosen segment (source and target) and proposes issues. "
                       "Its proposals are added as open issues marked “AI (beta)”. They do not count "
                       "towards the score until you accept them. Proposals that point at words which "
                       "are not in the text are dropped.")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.scope = {}
        for key, label in (("selected", "Selected segments"), ("confirmed", "Confirmed segments"),
                           ("translated", "All translated segments")):
            radio = QRadioButton(f"{label} ({counts.get(key, 0)})")
            radio.setObjectName(f"aiAnnotateScope_{key}")
            radio.setEnabled(counts.get(key, 0) > 0)
            self.scope[key] = radio
            layout.addWidget(radio)
        for key in ("selected", "confirmed", "translated"):
            if self.scope[key].isEnabled():
                self.scope[key].setChecked(True)
                break

        self.bar = QProgressBar()
        self.bar.setObjectName("aiAnnotateProgress")
        self.bar.setVisible(False)
        layout.addWidget(self.bar)
        self.result = QLabel("")
        self.result.setObjectName("aiAnnotateResult")
        self.result.setWordWrap(True)
        self.result.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.result)

        self.buttons = QDialogButtonBox()
        self.start_button = self.buttons.addButton("Start", QDialogButtonBox.ButtonRole.ActionRole)
        self.start_button.setObjectName("aiAnnotateStart")
        self.cancel_button = self.buttons.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        self.cancel_button.setObjectName("aiAnnotateCancel")
        self.start_button.clicked.connect(self.begin)
        self.cancel_button.clicked.connect(self._cancel_or_close)
        self.start_button.setEnabled(any(r.isEnabled() for r in self.scope.values()))
        layout.addWidget(self.buttons)

    def chosen_scope(self) -> str:
        return next((key for key, radio in self.scope.items() if radio.isChecked()), "translated")

    def begin(self):
        self.start_button.setEnabled(False)
        for radio in self.scope.values():
            radio.setEnabled(False)
        self.worker = self._start(self.chosen_scope())
        self.bar.setVisible(True)
        self.bar.setRange(0, max(1, len(self.worker.segments)))
        self.result.setText("Working…")
        self.worker.progress.connect(lambda done, total: (self.bar.setMaximum(max(1, total)),
                                                         self.bar.setValue(done)))
        self.worker.done.connect(self._finished)
        self.worker.start()

    def _finished(self, issues, summary):
        self.issues, self.summary = list(issues), summary
        text = summary.text()
        if summary.errors:
            text += "\n\nProblems:\n" + "\n".join(summary.errors)
        self.result.setText(text)
        self.cancel_button.setText("Close")
        self.bar.setValue(self.bar.maximum())

    def _cancel_or_close(self):
        if self.worker is not None and self.worker.isRunning():
            self.worker.cancel()
            self.result.setText("Cancelling after the segment in progress…")
            return
        if self.summary is not None:
            self.accept()
        else:
            self.reject()

    def closeEvent(self, event):  # noqa: N802 (Qt name)
        if self.worker is not None and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(30000)
        super().closeEvent(event)
