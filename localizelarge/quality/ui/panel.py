"""The Quality panel: a dock with three tabs, Issues, Scorecard and Profile."""
from __future__ import annotations

from typing import List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView, QComboBox, QDockWidget, QFileDialog, QFormLayout, QHBoxLayout, QHeaderView,
    QLabel, QMenu, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout,
    QWidget,
)

from localizelarge.mqm import typology
from localizelarge.mqm.report import ORIGIN_LABEL, SEVERITY_LABEL, STATUS_LABEL

from .marks import LETTER, SEVERITY_ORDER, UNDERLINE_NAME

ALL = "__all__"
COLUMNS = ["Seg.", "Sev.", "Category", "Found by", "Status", "Issue"]
REPORT_FILTER = "HTML report (*.html);;PDF report (*.pdf);;Excel workbook (*.xlsx);;JSON data (*.json)"


class QualityPanel(QDockWidget):
    def __init__(self, controller, parent=None):
        super().__init__("Quality", parent)
        self.setObjectName("qualityPanel")
        self.controller = controller
        self.tabs = QTabWidget()
        self.tabs.setObjectName("qualityTabs")
        self.setWidget(self.tabs)
        self.tabs.addTab(self._build_issues_tab(), "Issues")
        self.tabs.addTab(self._build_scorecard_tab(), "Scorecard")
        self.tabs.addTab(self._build_profile_tab(), "Profile")
        controller.changed.connect(self.reload)
        self.reload()

    # ── Issues ─────────────────────────────────────────────────────
    def _combo(self, name: str, first: str, items) -> QComboBox:
        combo = QComboBox()
        combo.setObjectName(name)
        combo.addItem(first, ALL)
        for value, label in items:
            combo.addItem(label, value)
        combo.currentIndexChanged.connect(self._fill_issues)
        return combo

    def _build_issues_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        buttons = QHBoxLayout()
        self.run_button = QPushButton("Run QA")
        self.run_button.setObjectName("qualityRunQa")
        self.run_button.setToolTip("Run every QA and glossary check on the whole project")
        self.run_button.clicked.connect(self.run_qa)
        buttons.addWidget(self.run_button)
        self.report_button = QPushButton("Export report…")
        self.report_button.setObjectName("qualityExportReport")
        self.report_button.clicked.connect(self.export_report)
        buttons.addWidget(self.report_button)
        buttons.addStretch()
        self.count_label = QLabel("")
        self.count_label.setObjectName("qualityIssueCount")
        buttons.addWidget(self.count_label)
        layout.addLayout(buttons)

        filters = QHBoxLayout()
        self.origin_filter = self._combo("qualityFilterOrigin", "All origins", ORIGIN_LABEL.items())
        self.category_filter = self._combo(
            "qualityFilterCategory", "All categories",
            [(d["id"], d["name"]) for d in typology.load()["dimensions"]])
        self.severity_filter = self._combo("qualityFilterSeverity", "All severities", SEVERITY_LABEL.items())
        self.status_filter = self._combo("qualityFilterStatus", "All statuses",
                                         list(STATUS_LABEL.items()) + [("needs-check", "Needs check")])
        for combo in (self.origin_filter, self.category_filter, self.severity_filter, self.status_filter):
            filters.addWidget(combo)
        layout.addLayout(filters)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setObjectName("qualityIssueTable")
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        for column in range(len(COLUMNS) - 1):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(len(COLUMNS) - 1, QHeaderView.ResizeMode.Stretch)
        self.table.itemDoubleClicked.connect(self._jump)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._issue_menu)
        layout.addWidget(self.table, 1)

        hint = QLabel("Double-click an issue to go to its segment. Right-click to accept, reject or delete it. "
                      "Severity letters: N neutral, m minor, M major, C critical.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        return page

    def _shown_issues(self) -> List:
        quality = self.controller.quality
        if quality is None:
            return []
        order = {s.id: number for number, s in enumerate(self.controller.segments)}
        origin = self.origin_filter.currentData()
        category = self.category_filter.currentData()
        severity = self.severity_filter.currentData()
        status = self.status_filter.currentData()
        shown = []
        for issue in quality.issues:
            if origin != ALL and issue.origin != origin:
                continue
            if category != ALL and typology.dimension_of(issue.category) != category:
                continue
            if severity != ALL and issue.severity != severity:
                continue
            if status == "needs-check":
                if not self.controller.is_stale(issue):
                    continue
            elif status != ALL and issue.status != status:
                continue
            shown.append(issue)
        shown.sort(key=lambda i: (order.get(i.segment_id, 10 ** 9), i.start if i.start is not None else -1))
        return shown

    def _fill_issues(self, *_):
        issues = self._shown_issues()
        order = {s.id: number for number, s in enumerate(self.controller.segments, 1)}
        self.table.setRowCount(len(issues))
        for row, issue in enumerate(issues):
            stale = self.controller.is_stale(issue)
            status = STATUS_LABEL[issue.status] + (" · needs check" if stale else "")
            cells = [str(order.get(issue.segment_id, "–")),
                     f"{LETTER[issue.severity]}  {SEVERITY_LABEL[issue.severity]}",
                     typology.label(issue.category), ORIGIN_LABEL[issue.origin], status, issue.message]
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, issue.id)
                if column == len(cells) - 1:
                    details = [issue.message]
                    if issue.comment and issue.comment != issue.message:
                        details.append("Comment: " + issue.comment)
                    if issue.suggestion:
                        details.append("Suggestion: " + issue.suggestion)
                    details.append(f"By {issue.author}, {issue.created_at}")
                    item.setToolTip("\n".join(details))
                if issue.status in ("rejected", "fixed"):
                    font = item.font()
                    font.setStrikeOut(True)
                    item.setFont(font)
                self.table.setItem(row, column, item)
        quality = self.controller.quality
        total = len(quality.issues) if quality else 0
        self.count_label.setText(f"{len(issues)} of {total} issues" if len(issues) != total else f"{total} issues")

    def _issue_at(self, row: int):
        item = self.table.item(row, 0)
        quality = self.controller.quality
        return quality.issues.get(item.data(Qt.ItemDataRole.UserRole)) if item and quality else None

    def _jump(self, item):
        issue = self._issue_at(item.row())
        navigate = getattr(self.controller.window, "_navigate_to_segment_by_id", None)
        if issue is not None and callable(navigate):
            navigate(issue.segment_id)

    def _issue_menu(self, position):
        row = self.table.rowAt(position.y())
        issue = self._issue_at(row) if row >= 0 else None
        if issue is None:
            return
        menu = QMenu(self)
        for status, label in (("accepted", "Accept"), ("rejected", "Reject"), ("fixed", "Mark as fixed"),
                              ("open", "Set back to open")):
            if issue.status != status:
                action = menu.addAction(label)
                action.triggered.connect(lambda _=False, s=status: self.controller.set_status(issue.id, s))
        if self.controller.is_stale(issue):
            action = menu.addAction("Checked: still applies to the new text")
            action.triggered.connect(lambda _=False: self.controller.recheck(issue.id))
        menu.addSeparator()
        action = menu.addAction("Go to segment")
        action.triggered.connect(lambda _=False: self._jump(self.table.item(row, 0)))
        action = menu.addAction("Delete")
        action.triggered.connect(lambda _=False: self.controller.delete_issue(issue.id))
        menu.exec(self.table.viewport().mapToGlobal(position))

    # ── Scorecard ──────────────────────────────────────────────────
    def _build_scorecard_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.verdict_label = QLabel("")
        self.verdict_label.setObjectName("qualityVerdict")
        self.verdict_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.verdict_label)

        form = QFormLayout()
        self.score_values = {}
        for key, label in (("score", "Quality score"), ("threshold", "Pass mark"), ("words", "Evaluated words"),
                           ("issues", "Issues counted"), ("apt", "Penalty points"),
                           ("npt", "Penalty points per reference word count"), ("model", "Scoring model")):
            value = QLabel("–")
            value.setObjectName(f"qualityScore_{key}")
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.score_values[key] = value
            form.addRow(label + ":", value)
        layout.addLayout(form)

        self.category_table = QTableWidget(0, 7)
        self.category_table.setObjectName("qualityCategoryTable")
        self.category_table.setHorizontalHeaderLabels(
            ["Category", "Neutral", "Minor", "Major", "Critical", "Weight", "Penalty"])
        self.category_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.category_table.verticalHeader().setVisible(False)
        self.category_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.category_table, 1)
        return page

    def _fill_scorecard(self):
        score = self.controller.score()
        if score is None:
            self.verdict_label.setText("No project is open.")
            self.verdict_label.setStyleSheet("")
            for value in self.score_values.values():
                value.setText("–")
            self.category_table.setRowCount(0)
            return
        if score.passed is None:
            text, style = "NOT SCORED – no words to evaluate", "border: 2px solid #52606d; color: #52606d;"
        elif score.passed:
            text, style = "✔ PASS", "border: 2px solid #0b6b3a; color: #0b6b3a;"
        else:
            text, style = "✘ FAIL", "border: 2px solid #a61b1b; color: #a61b1b;"
        self.verdict_label.setText(text)
        self.verdict_label.setStyleSheet(style + " font-size: 16px; font-weight: bold; padding: 6px;")

        def number(value, digits=2):
            return "–" if value is None else f"{value:.{digits}f}"

        self.score_values["score"].setText(number(score.score))
        self.score_values["threshold"].setText(number(score.threshold))
        self.score_values["words"].setText(str(score.evaluation_word_count))
        self.score_values["issues"].setText(str(score.issue_count))
        self.score_values["apt"].setText(number(score.absolute_penalty_total))
        self.score_values["npt"].setText(number(score.normed_penalty_total))
        self.score_values["model"].setText("Linear, calibrated" if score.model == "calibrated" else "Linear, raw")
        self.category_table.setRowCount(len(score.by_category))
        for row, total in enumerate(score.by_category):
            cells = [typology.label(total.category)] + [str(total.counts.get(s, 0)) for s in SEVERITY_ORDER] \
                + [number(total.weight), number(total.penalty)]
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if column:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.category_table.setItem(row, column, item)

    # ── Profile ────────────────────────────────────────────────────
    def _build_profile_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.profile_label = QLabel("")
        self.profile_label.setObjectName("qualityProfileText")
        self.profile_label.setWordWrap(True)
        self.profile_label.setTextFormat(Qt.TextFormat.PlainText)
        self.profile_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.profile_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.profile_label, 1)
        return page

    def _fill_profile(self):
        quality = self.controller.quality
        if quality is None:
            self.profile_label.setText("No project is open.")
            return
        profile, s = quality.profile, quality.profile.scoring
        lines = [
            f"Profile: {profile.name}", f"Version: {profile.version}", f"From: {profile.source}", "",
            f"Scoring model: {'linear, calibrated' if s.model == 'calibrated' else 'linear, raw'}",
            "Severity multipliers: " + ", ".join(f"{name} {s.multiplier(name):g}" for name in SEVERITY_ORDER),
            f"Reference word count: {s.reference_word_count:g}",
            f"Acceptable penalty points per reference word count: {s.acceptable_penalty_points:g}",
            f"Pass mark: {s.passing_threshold:g} (calibrated), {s.raw_threshold:g} (raw)",
            "Open issues count towards the score: " + ("yes" if s.count_open else "no"),
            "Open AI proposals count towards the score: " + ("yes" if s.count_open_ai else "no"),
        ]
        if s.weights:
            lines += ["", "Category weights:"] + [f"  {typology.label(path)}: {weight:g}"
                                                 for path, weight in s.weights.items()]
        switched_off = [rule for rule, settings in profile.checks.items() if settings.get("enabled") is False]
        if switched_off:
            lines += ["", "Checks switched off: " + ", ".join(sorted(switched_off))]
        lines += ["", "Underlines in the editor: " + ", ".join(
            f"{name} = {UNDERLINE_NAME[name]} ({LETTER[name]})" for name in SEVERITY_ORDER), "",
            typology.attribution()]
        self.profile_label.setText("\n".join(lines))

    # ── actions ────────────────────────────────────────────────────
    def reload(self):
        has_project = self.controller.project is not None
        self.run_button.setEnabled(has_project)
        self.report_button.setEnabled(has_project)
        self._fill_issues()
        self._fill_scorecard()
        self._fill_profile()

    def run_qa(self):
        if self.controller.project is None:
            return
        count = self.controller.run_project()
        self.tabs.setCurrentIndex(0)
        log = getattr(self.controller.window, "log", None)
        if callable(log):
            log(f"🔎 QA run: {count} finding(s)")

    def export_report(self, path: Optional[str] = None):
        if self.controller.project is None:
            return
        if not path:
            name = (getattr(self.controller.project, "name", "") or "project").replace("/", "-")
            path, chosen = QFileDialog.getSaveFileName(self, "Export quality report",
                                                       f"{name} - quality report.html", REPORT_FILTER)
            if not path:
                return
            if "." not in path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]:
                path += {"HTML": ".html", "PDF ": ".pdf", "Exce": ".xlsx", "JSON": ".json"}.get(chosen[:4], ".html")
        try:
            self.controller.export_report(path)
        except Exception as error:
            QMessageBox.critical(self, "Export quality report", f"The report could not be written:\n{error}")
            return
        QMessageBox.information(self, "Export quality report", f"The report was written to\n{path}")
