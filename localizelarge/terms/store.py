"""Entries in and out of a termbase in the app's database."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .model import Entry, Variant


@dataclass
class ImportReport:
    added: int = 0
    merged: int = 0      # the entry existed; missing variants and details were added
    failed: int = 0


def _clean(text: Optional[str]) -> str:
    return (text or "").strip()


def _existing_variants(termbase_mgr, term_id: int, language: str) -> set:
    return {s["synonym_text"].lower() for s in termbase_mgr.get_synonyms(term_id, language=language)}


def _add_variants(termbase_mgr, term_id: int, variants: List[Variant], language: str,
                  main_term: str) -> None:
    have = _existing_variants(termbase_mgr, term_id, language)
    order = len(have)
    for variant in variants:
        text = _clean(variant.text)
        if not text or text.lower() in have or text.lower() == main_term.lower():
            continue
        order += 1
        termbase_mgr.add_synonym(term_id, text, language=language, display_order=order,
                                 forbidden=bool(variant.forbidden))
        have.add(text.lower())


def import_entries(termbase_mgr, termbase_id: int, entries: List[Entry],
                   source_lang: Optional[str] = None, target_lang: Optional[str] = None,
                   progress=None) -> ImportReport:
    """Add entries to a termbase. An entry whose source and target terms are already
    there is not added twice: its new variants are added, and its empty details filled.
    """
    report = ImportReport()
    cursor = termbase_mgr.db_manager.cursor
    total = len(entries)
    for number, entry in enumerate(entries, 1):
        if progress and (number % 50 == 0 or number == total):
            progress(number, total)
        source, target = _clean(entry.source), _clean(entry.target)
        if not source or not target:
            report.failed += 1
            continue
        try:
            term_id = termbase_mgr.add_term(
                termbase_id, source, target, domain=_clean(entry.domain),
                notes=_clean(entry.notes), forbidden=bool(entry.forbidden),
                source_lang=source_lang, target_lang=target_lang,
                definition=_clean(entry.definition))
            if term_id is None:
                # add_term stores a translatable term without its final full stop.
                from modules.termbase_manager import normalize_term_for_save
                term_id = termbase_mgr.find_duplicate_term(
                    termbase_id, normalize_term_for_save(source), normalize_term_for_save(target))
                if term_id is None:
                    report.failed += 1
                    continue
                report.merged += 1
                cursor.execute(
                    """UPDATE termbase_terms SET
                         domain = CASE WHEN COALESCE(domain, '') = '' THEN ? ELSE domain END,
                         notes = CASE WHEN COALESCE(notes, '') = '' THEN ? ELSE notes END,
                         definition = CASE WHEN COALESCE(definition, '') = '' THEN ? ELSE definition END
                       WHERE id = ?""",
                    (_clean(entry.domain), _clean(entry.notes), _clean(entry.definition), term_id))
            else:
                report.added += 1
            if _clean(entry.part_of_speech):
                cursor.execute(
                    "UPDATE termbase_terms SET part_of_speech = ? "
                    "WHERE id = ? AND COALESCE(part_of_speech, '') = ''",
                    (_clean(entry.part_of_speech), term_id))
            _add_variants(termbase_mgr, term_id, entry.source_variants, "source", source)
            _add_variants(termbase_mgr, term_id, entry.target_variants, "target", target)
        except Exception:
            report.failed += 1
    termbase_mgr.db_manager.connection.commit()
    return report


def export_entries(termbase_mgr, termbase_id: int) -> List[Entry]:
    """Every entry of a termbase, with its variants."""
    cursor = termbase_mgr.db_manager.cursor
    cursor.execute(
        """SELECT id, source_term, target_term, COALESCE(domain, ''), COALESCE(notes, ''),
                  COALESCE(forbidden, 0), COALESCE(term_uuid, ''),
                  COALESCE(definition, ''), COALESCE(part_of_speech, '')
           FROM termbase_terms WHERE termbase_id = CAST(? AS TEXT)
           ORDER BY source_term COLLATE NOCASE, id""", (termbase_id,))
    rows = cursor.fetchall()
    entries: List[Entry] = []
    for term_id, source, target, domain, notes, forbidden, uid, definition, pos in rows:
        entry = Entry(source=source, target=target, domain=domain, notes=notes,
                      forbidden=bool(forbidden), uid=uid, definition=definition,
                      part_of_speech=pos)
        for synonym in termbase_mgr.get_synonyms(term_id):
            variant = Variant(synonym["synonym_text"], bool(synonym["forbidden"]))
            if synonym["language"] == "source":
                entry.source_variants.append(variant)
            else:
                entry.target_variants.append(variant)
        entries.append(entry)
    return entries
