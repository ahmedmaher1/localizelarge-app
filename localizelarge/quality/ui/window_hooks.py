"""What the main window calls. Each function is one thin hook in Supervertaler.py."""
from __future__ import annotations

from typing import Optional, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import QApplication, QDialog, QLabel, QMessageBox, QTextEdit

from . import marks
from .add_issue_dialog import AddIssueDialog
from .controller import QualityController
from .panel import QualityPanel

ADD_ISSUE_SHORTCUT = "Ctrl+Shift+E"


def controller_of(window) -> Optional[QualityController]:
    return getattr(window, "_ll_quality", None)


def install(window, version: str = "") -> QualityController:
    """Create the controller and the Quality panel, and add the actions to the QA menu."""
    existing = controller_of(window)
    if existing is not None:
        return existing
    controller = QualityController(window)
    controller.version = version
    window._ll_quality = controller

    panel = QualityPanel(controller, window)
    window._ll_quality_panel = panel
    window.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, panel)
    panel.hide()

    menu = getattr(window, "qa_menu", None)
    if menu is not None:
        run = QAction("Run &QA (all checks)", window)
        run.setObjectName("llRunQaAction")
        run.setToolTip("Run the QA checks and the glossary checks on the whole project")
        run.triggered.connect(lambda: run_qa(window))
        add = QAction("&Add issue…", window)
        add.setObjectName("llAddIssueAction")
        add.setShortcut(QKeySequence(ADD_ISSUE_SHORTCUT))
        add.setToolTip("Mark the selected text as an MQM issue")
        add.triggered.connect(lambda: add_issue(window))
        toggle = panel.toggleViewAction()
        toggle.setText("Quality &panel")
        toggle.setObjectName("llQualityPanelAction")
        export = QAction("&Export quality report…", window)
        export.setObjectName("llExportQualityReportAction")
        export.triggered.connect(lambda: (panel.show(), panel.export_report()))
        ai = QAction("AI pre-annotation (&beta)…", window)
        ai.setObjectName("llAiAnnotateAction")
        ai.setToolTip("Let the configured AI propose MQM issues; you accept or reject them")
        ai.triggered.connect(lambda: ai_annotate(window))
        first = menu.actions()[0] if menu.actions() else None
        for action in (run, add, ai, toggle, export):
            menu.insertAction(first, action)
        menu.insertSeparator(first)
        window._ll_quality_actions = (run, add, ai, toggle, export)
    return controller


def show_panel(window, tab: int = 0) -> None:
    panel = getattr(window, "_ll_quality_panel", None)
    if panel is not None:
        panel.show()
        panel.raise_()
        panel.tabs.setCurrentIndex(tab)


def run_qa(window) -> None:
    controller = controller_of(window)
    if controller is None or controller.project is None:
        QMessageBox.information(window, "Run QA", "Open a project first.")
        return
    show_panel(window)
    window._ll_quality_panel.run_qa()


def grid_loaded(window) -> None:
    """The grid was rebuilt: put the underlines back and reload the panel."""
    controller = controller_of(window)
    if controller is not None:
        controller.refresh()


def segment_confirmed(window, segment) -> None:
    controller = controller_of(window)
    if controller is not None:
        try:
            controller.segment_confirmed(segment)
        except Exception as error:      # a check must never stop a confirmation
            log = getattr(window, "log", None)
            if callable(log):
                log(f"⚠ QA on confirm failed: {error}")


def add_status_marker(window, layout, segment) -> None:
    """Add the issue marker (for example "M2") to a status cell."""
    controller = controller_of(window)
    if controller is None:
        return
    marker, tooltip = controller.status_marker(segment)
    if not marker:
        return
    label = QLabel(marker)
    label.setObjectName("qualityMarker")
    label.setToolTip(tooltip)
    worst = {v: k for k, v in marks.LETTER.items()}[marker[0]]
    label.setStyleSheet(f"color: {marks.COLOR[worst]}; font-weight: bold; font-size: 10px; "
                        f"border: 1px solid {marks.COLOR[worst]}; border-radius: 3px; padding: 0 2px;")
    layout.addWidget(label)


def add_context_action(editor, menu) -> None:
    """"Add issue…" in the right-click menu of a source or target cell."""
    window = editor.window()
    if controller_of(window) is None:
        return
    menu.addSeparator()
    action = QAction(f"Add issue… ({ADD_ISSUE_SHORTCUT})", menu)
    action.triggered.connect(lambda: add_issue(window, editor))
    menu.addAction(action)


def _row_of(window, editor) -> int:
    table = getattr(window, "table", None)
    if table is None:
        return -1
    for row in range(table.rowCount()):
        if table.cellWidget(row, 2) is editor or table.cellWidget(row, 3) is editor:
            return row
    return table.currentRow()


def selection_in_plain_text(editor) -> Tuple[Optional[int], Optional[int]]:
    """The editor's selection as offsets in the plain text (tags removed), or (None, None)
    when nothing is selected."""
    cursor = editor.textCursor()
    if not cursor.hasSelection():
        return None, None
    display = QTextEdit.toPlainText(editor)
    compact = list((getattr(editor, "_compact_tag_map", None) or {}).keys())
    positions = marks.plain_to_display(display, compact)[:-1]
    start = sum(1 for p in positions if p < cursor.selectionStart())
    end = sum(1 for p in positions if p < cursor.selectionEnd())
    return (start, end) if end > start else (None, None)


def add_issue(window, editor=None):
    """Open the Add issue panel for the selection in the focused cell (or the whole
    target of the current segment) and add the issue. Returns the issue, or None."""
    controller = controller_of(window)
    if controller is None or controller.project is None:
        return None
    if editor is None:
        focused = QApplication.focusWidget()
        editor = focused if isinstance(focused, QTextEdit) and hasattr(focused, "ll_side") else None
    table = getattr(window, "table", None)
    row = _row_of(window, editor) if editor is not None else (table.currentRow() if table is not None else -1)
    item = table.item(row, 0) if table is not None and row >= 0 else None
    try:
        segment = controller.segment(int(item.text())) if item is not None else None
    except (TypeError, ValueError):
        segment = None
    if segment is None:
        QMessageBox.information(window, "Add issue", "Click in a segment first.")
        return None

    side = getattr(editor, "ll_side", "target") if editor is not None else "target"
    start, end = selection_in_plain_text(editor) if editor is not None else (None, None)
    # What is in the cell may be newer than the segment (typing is saved after a pause).
    if editor is not None and side == "target":
        sync = getattr(window, "_sync_grid_targets_to_segments", None)
        if callable(sync):
            try:
                sync([segment])
            except Exception:
                pass
    from localizelarge.quality.model import plain_text
    text = plain_text(segment.source if side == "source" else segment.target)
    if start is not None and end > len(text):
        start = end = None
    quote = text[start:end] if start is not None else ""

    dialog = AddIssueDialog(quote, side, window, categories=controller.quality.profile.categories)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    issue = controller.add_issue(segment, side=side, start=start, end=end, category=dialog.category(),
                                 severity=dialog.severity(), comment=dialog.comment_text(),
                                 suggestion=dialog.suggestion_text())
    show_panel(window)
    return issue


def _ai_setup(window):
    """(provider, model, ask) for the configured AI, or raises RuntimeError with a
    message for the user."""
    settings = window.load_llm_settings()
    provider = settings.get("provider", "") or ""
    from modules.llm_clients import SUPPORTED_PROVIDERS, LLMClient
    if provider not in SUPPORTED_PROVIDERS:
        raise RuntimeError("Choose an AI provider in Settings → AI first.")
    model = settings.get(f"{provider}_model") or ""
    if not model:
        from modules.llm_clients import _load_default_models
        model = (_load_default_models() or {}).get(provider, "")
    if not model:
        raise RuntimeError(f"Choose a model for {provider} in Settings → AI first.")
    keys = window.load_api_keys()
    key = keys.get(provider, "") or ("not-needed" if provider == "ollama" else "")
    if not key:
        raise RuntimeError(f"There is no API key for {provider}. Add it in Settings → AI.")
    proxy = getattr(window, "_get_proxy_url", lambda: None)() if provider != "gemini" else None
    client = LLMClient(api_key=key, provider=provider, model=model, http_proxy=proxy)

    def ask(prompt: str):
        return client.translate_with_usage(text="", source_lang="", target_lang="", custom_prompt=prompt)

    return provider, model, ask


def ai_annotate(window, setup=None):
    """QA → AI pre-annotation (beta). ``setup`` replaces the real AI in tests."""
    from .ai_dialog import AiAnnotateDialog, AnnotateWorker
    controller = controller_of(window)
    if controller is None or controller.project is None:
        QMessageBox.information(window, "AI pre-annotation", "Open a project first.")
        return None
    try:
        provider, model, ask = (setup or _ai_setup)(window)
    except RuntimeError as error:
        QMessageBox.information(window, "AI pre-annotation", str(error))
        return None
    except Exception as error:
        QMessageBox.critical(window, "AI pre-annotation", f"The AI could not be set up:\n{error}")
        return None

    segments = controller.segments
    table = getattr(window, "table", None)
    selected_ids = set()
    if table is not None:
        for index in table.selectionModel().selectedRows() if table.selectionModel() else []:
            item = table.item(index.row(), 0)
            if item is not None and item.text().isdigit():
                selected_ids.add(int(item.text()))
    translated = [s for s in segments if (s.target or "").strip()]
    groups = {
        "selected": [s for s in translated if s.id in selected_ids],
        "confirmed": [s for s in translated if getattr(s, "status", "") == "confirmed"],
        "translated": translated,
    }
    where = getattr(window, "_where_text_goes", None)
    destination = where(provider) if callable(where) else f"Text is sent to {provider}"
    project = controller.project

    def start(scope: str):
        options = dict(provider=provider, model=model, source_lang=project.source_lang,
                       target_lang=project.target_lang, categories=controller.quality.profile.categories,
                       glossary_for=controller.glossary_terms_for)
        if setup is not None:
            options["min_interval"] = 0
        return AnnotateWorker(groups[scope], ask, options, window)

    controller.glossary()        # read on this thread, before the worker starts
    dialog = AiAnnotateDialog(window, destination=destination, provider=provider, model=model,
                              counts={key: len(value) for key, value in groups.items()}, start=start)
    window._ll_ai_dialog = dialog
    dialog.exec()
    if dialog.summary is None:
        return None
    controller.add_ai_results(dialog.issues, dialog.summary)
    show_panel(window)
    return dialog.summary
