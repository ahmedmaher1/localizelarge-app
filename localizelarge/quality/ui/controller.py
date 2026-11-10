"""The link between the main window and the quality code.

The main window makes one ``QualityController`` and calls a handful of its methods; the
controller reads what it needs from the window (the open project, the termbases, the
spell checker, the grid) and never the other way round.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QTextEdit

from localizelarge.mqm import report as mqm_report
from localizelarge.mqm import scoring
from localizelarge.quality import engine, glossary_check
from localizelarge.quality.checks import Context
from localizelarge.quality.model import Issue, make_issue, plain_text
from localizelarge.quality.project_store import ProjectQuality, quality_of

from . import marks


class QualityController(QObject):
    changed = pyqtSignal()          # issues or the profile changed

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self._glossary_key = None
        self._glossary: Optional[glossary_check.Glossary] = None

    # ── what the window has ────────────────────────────────────────
    @property
    def project(self):
        return getattr(self.window, "current_project", None)

    @property
    def segments(self) -> list:
        project = self.project
        return list(getattr(project, "segments", None) or []) if project else []

    @property
    def quality(self) -> Optional[ProjectQuality]:
        project = self.project
        return quality_of(project) if project is not None else None

    @property
    def ai_runs(self) -> List[Dict[str, Any]]:
        quality = self.quality
        return quality.ai_runs if quality is not None else []

    def segment(self, segment_id: int):
        return next((s for s in self.segments if s.id == segment_id), None)

    def _log(self, text: str):
        log = getattr(self.window, "log", None)
        if callable(log):
            log(text)

    def _modified(self):
        if hasattr(self.window, "project_modified"):
            self.window.project_modified = True

    # ── running the checks ─────────────────────────────────────────
    def _spell_check(self):
        if not getattr(self.window, "spellcheck_enabled", False):
            return None
        manager = getattr(self.window, "spellcheck_manager", None)
        check = getattr(manager, "check_word", None)
        return check if callable(check) else None

    def _regex_checks(self) -> list:
        folder = getattr(self.window, "user_data_path", None)
        if not folder:
            return []
        try:
            from modules.qa_checks import checks_in, load_sets
            return [op for fr_set in load_sets(Path(folder) / "find_replace_sets") for op in checks_in(fr_set)]
        except Exception:
            return []

    def context(self, with_project_checks: bool = True) -> Context:
        project, quality = self.project, self.quality
        return Context(
            source_lang=getattr(project, "source_lang", "") or "",
            target_lang=getattr(project, "target_lang", "") or "",
            segments=self.segments,
            settings=quality.profile.checks if quality else {},
            spell_check=self._spell_check(),
            regex_checks=self._regex_checks() if with_project_checks else (),
        )

    def glossary(self) -> Optional[glossary_check.Glossary]:
        """The project's active glossaries, ready for checking. Built once and rebuilt
        when the set of glossaries or their size changes."""
        project = self.project
        manager = getattr(self.window, "termbase_mgr", None)
        if project is None or manager is None:
            return None
        try:
            active = manager.get_active_termbases_for_project(getattr(project, "id", None)) or []
        except Exception:
            active = []
        key = tuple((t.get("id"), t.get("term_count")) for t in active) + (
            project.source_lang, project.target_lang)
        if key != self._glossary_key:
            entries = []
            for termbase in active:
                try:
                    entries.extend(glossary_check.entries_from_termbase(
                        manager, termbase["id"], termbase.get("name", "")))
                except Exception as error:
                    self._log(f"⚠ Glossary “{termbase.get('name')}” could not be read for checking: {error}")
            self._glossary = glossary_check.Glossary(entries, project.source_lang, project.target_lang)
            self._glossary_key = key
        return self._glossary

    def invalidate_glossary(self):
        self._glossary_key = None

    def run_project(self, progress=None) -> int:
        """Run every QA and glossary check on the whole project. Returns the number of
        findings. Decisions made on earlier findings are kept."""
        quality = self.quality
        if quality is None:
            return 0
        segments = self.segments
        ctx = self.context()
        found = engine.run_project(segments, ctx, progress=progress)
        glossary = self.glossary()
        has_glossary = glossary is not None and len(glossary) > 0
        if has_glossary:
            found.extend(glossary_check.run(segments, glossary, quality.profile.checks))
        # Without an active glossary nothing can be said about glossary findings made
        # earlier (on another computer, say): they stay as they are.
        quality.issues.replace_automatic(found, origins=("qa", "glossary") if has_glossary else ("qa",))
        self._modified()
        self.refresh()
        return len(found)

    def segment_confirmed(self, segment) -> int:
        """Run the checks that need only this segment (called when it is confirmed)."""
        quality = self.quality
        if quality is None or segment is None:
            return 0
        if not quality.profile.checks.get("_engine", {}).get("check_on_confirm", True):
            return 0
        found = engine.run_segment(segment, self.context(with_project_checks=False))
        glossary = self.glossary()
        has_glossary = glossary is not None and len(glossary) > 0
        if has_glossary:
            found.extend(glossary_check.check_segment(segment, glossary, quality.profile.checks))
        # Project-wide findings of this segment (inconsistency) stay until the next full run.
        project_wide = {c.id for c in engine.checks() if c.project_wide} | {glossary_check.INCONSISTENT}
        origins = ("qa", "glossary") if has_glossary else ("qa",)
        kept = [i for i in quality.issues.for_segment(segment.id)
                if i.origin in origins and i.rule_id in project_wide]
        before = len(quality.issues)
        quality.issues.replace_automatic(found + kept, origins=origins, segment_ids=[segment.id])
        if found or len(quality.issues) != before:
            self._modified()
        self.refresh([segment.id])
        return len(found)

    # ── issues made by a person ────────────────────────────────────
    def add_issue(self, segment, *, side: str, start: Optional[int], end: Optional[int],
                  category: str, severity: str, comment: str = "", suggestion: str = "",
                  origin: str = "human", author: str = "", message: str = "") -> Issue:
        side_text = segment.source if side == "source" else segment.target
        quote = plain_text(side_text)[start:end] if start is not None else ""
        issue = make_issue(
            segment, origin=origin, rule_id="mqm", category=category, severity=severity, side=side,
            start=start, end=end, message=message or comment or (f"“{quote}”" if quote else ""),
            comment=comment or None, suggestion=suggestion or None, author=author,
            status="accepted" if origin == "human" else "open")
        self.quality.issues.add(issue)
        self._modified()
        self.refresh([segment.id])
        return issue

    def set_status(self, issue_id: str, status: str) -> bool:
        issue = self.quality.issues.get(issue_id) if self.quality else None
        if issue is None or issue.status == status:
            return False
        issue.status = status
        self._modified()
        self.refresh([issue.segment_id])
        return True

    def update_issue(self, issue_id: str, **fields) -> bool:
        issue = self.quality.issues.get(issue_id) if self.quality else None
        if issue is None:
            return False
        for name in ("category", "severity", "comment", "suggestion"):
            if name in fields:
                setattr(issue, name, fields[name] or (None if name in ("comment", "suggestion") else getattr(issue, name)))
        self._modified()
        self.refresh([issue.segment_id])
        return True

    def recheck(self, issue_id: str) -> bool:
        """A person looked at a "needs check" issue and says it still applies to the
        text as it is now. Its span is dropped: the old offsets may point elsewhere."""
        issue = self.quality.issues.get(issue_id) if self.quality else None
        segment = self.segment(issue.segment_id) if issue else None
        if issue is None or segment is None:
            return False
        from localizelarge.quality.model import text_hash
        issue.text_hash = text_hash(segment.source if issue.side == "source" else segment.target)
        issue.start = issue.end = None
        self._modified()
        self.refresh([issue.segment_id])
        return True

    def delete_issue(self, issue_id: str) -> bool:
        issue = self.quality.issues.get(issue_id) if self.quality else None
        if issue is None:
            return False
        self.quality.issues.remove(issue_id)
        self._modified()
        self.refresh([issue.segment_id])
        return True

    # ── AI proposals ───────────────────────────────────────────────
    def glossary_terms_for(self, segment) -> list:
        """(source term, approved targets) for the glossary terms in a segment's source."""
        glossary = self.glossary()
        if glossary is None or not len(glossary):
            return []
        return [(hit.term, hit.entry.targets) for hit in glossary.source_hits(segment.source)
                if hit.entry.targets]

    def add_ai_results(self, issues, summary) -> int:
        """Add the proposals of an AI run. Earlier open proposals for the same segments
        are replaced; ones a person accepted, rejected or fixed stay."""
        quality = self.quality
        if quality is None:
            return 0
        touched = {i.segment_id for i in issues}
        for old in [i for i in quality.issues if i.origin == "ai" and i.status == "open"
                    and i.segment_id in touched]:
            quality.issues.remove(old.id)
        for issue in issues:
            quality.issues.add(issue)
        self.ai_runs.append(summary.to_report())
        if issues:
            self._modified()
        self.refresh(sorted(touched) or None)
        return len(issues)

    # ── the score and the report ───────────────────────────────────
    def score(self) -> Optional[scoring.Score]:
        quality = self.quality
        if quality is None:
            return None
        return scoring.calculate(quality.issues.all(), scoring.word_count(self.segments),
                                 quality.profile.scoring)

    def build_report(self) -> Dict[str, Any]:
        project = self.project
        version = getattr(self, "version", "")
        return mqm_report.build(
            project_name=getattr(project, "name", "") or "", source_lang=project.source_lang,
            target_lang=project.target_lang, segments=self.segments, quality=self.quality,
            ai_runs=self.ai_runs, app_version=version, files=self._file_names())

    def _file_names(self) -> List[str]:
        """The source documents of the project, by name."""
        import os
        project = self.project
        names = [f.get("name") for f in (getattr(project, "files", None) or []) if isinstance(f, dict) and f.get("name")]
        if not names:
            for field in ("original_docx_path", "original_txt_path", "po_source_path"):
                value = getattr(project, field, None)
                if value:
                    names.append(os.path.basename(str(value)))
                    break
        return names

    def export_report(self, path: str) -> None:
        mqm_report.write(self.build_report(), path)

    # ── showing issues in the grid ─────────────────────────────────
    def is_stale(self, issue: Issue) -> bool:
        segment = self.segment(issue.segment_id)
        if segment is None:
            return True
        return issue.is_stale(segment.source if issue.side == "source" else segment.target)

    def status_marker(self, segment) -> tuple:
        quality = self.quality
        if quality is None:
            return "", ""
        return marks.summary(quality.issues.for_segment(segment.id), segment.source, segment.target)

    def underline(self, segment, source_editor, target_editor) -> None:
        """Underline the spans of a segment's issues in its two cell editors."""
        quality = self.quality
        issues = quality.issues.for_segment(segment.id) if quality else []
        for editor, side, text in ((source_editor, "source", segment.source),
                                   (target_editor, "target", segment.target)):
            if isinstance(editor, QTextEdit):
                editor.setExtraSelections(marks.selections_for(editor, issues, side, text) if issues else [])

    def refresh(self, segment_ids: Optional[List[int]] = None) -> None:
        """Bring the grid's markers and underlines up to date and tell the panel."""
        table = getattr(self.window, "table", None)
        project = self.project
        if table is not None and project is not None:
            wanted = set(segment_ids) if segment_ids is not None else None
            try:
                for row in range(table.rowCount()):
                    item = table.item(row, 0)
                    if item is None:
                        continue
                    try:
                        segment_id = int(item.text())
                    except (TypeError, ValueError):
                        continue
                    if wanted is not None and segment_id not in wanted:
                        continue
                    segment = self.segment(segment_id)
                    if segment is None:
                        continue
                    self.underline(segment, table.cellWidget(row, 2), table.cellWidget(row, 3))
                    update = getattr(self.window, "_update_status_cell", None)
                    if callable(update):
                        update(row, segment)
            except RuntimeError:
                pass        # the grid is being rebuilt
        self.changed.emit()
