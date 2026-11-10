"""Glossaries kept in a spreadsheet: XLSX, CSV and TSV.

``read_table`` gives the header row and the data rows. ``guess_mapping`` proposes which
column is which field, ``to_entries`` builds entries from the rows with a mapping. The
import dialog shows the proposal and lets the user change it.
"""
from __future__ import annotations

import csv
import os
import re
from typing import Dict, List, Optional, Tuple

from .model import Entry, Variant

# Field key → label shown in the mapping dialog. The order is the dialog's order.
FIELDS: List[Tuple[str, str]] = [
    ("source", "Source term"),
    ("target", "Target term"),
    ("source_variants", "Source variants"),
    ("target_variants", "Target variants"),
    ("forbidden_targets", "Forbidden target terms"),
    ("forbidden", "Forbidden (yes/no)"),
    ("part_of_speech", "Part of speech"),
    ("definition", "Definition"),
    ("notes", "Notes"),
    ("domain", "Domain"),
]
REQUIRED = ("source", "target")

# Header words that suggest a field, most telling first.
_HINTS: List[Tuple[str, Tuple[str, ...]]] = [
    ("forbidden_targets", ("forbidden term", "forbidden target", "do not use", "banned", "deprecated")),
    ("forbidden", ("forbidden", "prohibited", "status")),
    ("source_variants", ("source synonym", "source variant", "source alternative")),
    ("target_variants", ("target synonym", "target variant", "target alternative", "synonym", "variant", "alternative")),
    ("part_of_speech", ("part of speech", "pos", "word class", "grammar")),
    ("definition", ("definition", "meaning", "description")),
    ("notes", ("note", "comment", "remark", "context", "usage")),
    ("domain", ("domain", "subject", "category", "field", "area")),
    ("source", ("source", "term (source)", "original")),
    ("target", ("target", "translation", "term (target)")),
]
_TRUE = {"1", "true", "yes", "y", "x", "forbidden", "deprecated", "prohibited"}
_SPLIT = re.compile(r"\s*[;|]\s*")


def read_table(path: str, max_rows: Optional[int] = None) -> Tuple[List[str], List[List[str]]]:
    """The header row and the data rows of an XLSX, CSV or TSV file, as text."""
    ext = os.path.splitext(str(path))[1].lower()
    rows: List[List[str]] = []
    if ext in (".xlsx", ".xlsm"):
        import openpyxl
        book = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
        try:
            sheet = book.worksheets[0]
            for row in sheet.iter_rows(values_only=True):
                rows.append(["" if value is None else str(value).strip() for value in row])
                if max_rows is not None and len(rows) > max_rows:
                    break
        finally:
            book.close()
    else:
        with open(path, "r", encoding="utf-8-sig", newline="") as handle:
            sample = handle.read(8192)
            handle.seek(0)
            if ext in (".tsv", ".tab"):
                delimiter = "\t"
            else:
                try:
                    delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
                except csv.Error:
                    delimiter = "\t" if sample.count("\t") > sample.count(",") else ","
            for row in csv.reader(handle, delimiter=delimiter):
                rows.append([cell.strip() for cell in row])
                if max_rows is not None and len(rows) > max_rows:
                    break
    rows = [row for row in rows if any(cell for cell in row)]
    if not rows:
        return [], []
    width = max(len(row) for row in rows)
    rows = [row + [""] * (width - len(row)) for row in rows]
    headers = [cell or f"Column {index + 1}" for index, cell in enumerate(rows[0])]
    return headers, rows[1:]


def guess_mapping(headers: List[str], source_lang: str = "", target_lang: str = "") -> Dict[str, int]:
    """Field key → column index, for the columns whose header suggests a field.

    A header that is a language code or name ("en", "English", "fr-FR") is taken as
    the source or target term when it matches the termbase's language.
    """
    mapping: Dict[str, int] = {}
    lowered = [header.strip().lower() for header in headers]

    def base(code: str) -> str:
        return (code or "").replace("_", "-").split("-")[0].lower()

    for index, header in enumerate(lowered):
        if source_lang and "source" not in mapping and header and base(header) == base(source_lang):
            mapping["source"] = index
        elif target_lang and "target" not in mapping and header and base(header) == base(target_lang):
            mapping["target"] = index

    for field, hints in _HINTS:
        if field in mapping:
            continue
        for index, header in enumerate(lowered):
            if index in mapping.values():
                continue
            if any(hint in header for hint in hints):
                mapping[field] = index
                break

    # Two unnamed leading columns: source, then target.
    free = [i for i in range(len(headers)) if i not in mapping.values()]
    if "source" not in mapping and free:
        mapping["source"] = free.pop(0)
    if "target" not in mapping and free:
        mapping["target"] = free.pop(0)
    return mapping


def _cell(row: List[str], mapping: Dict[str, int], field: str) -> str:
    index = mapping.get(field)
    if index is None or index < 0 or index >= len(row):
        return ""
    return row[index].strip()


def _list(text: str) -> List[str]:
    return [part for part in _SPLIT.split(text) if part] if text else []


def to_entries(rows: List[List[str]], mapping: Dict[str, int]) -> Tuple[List[Entry], int]:
    """Entries from data rows. Returns (entries, rows skipped for a missing term).

    Several variants in one cell are separated by ``;`` or ``|``.
    """
    missing = [field for field in REQUIRED if field not in mapping]
    if missing:
        raise ValueError("No column is chosen for: " + ", ".join(missing))
    entries: List[Entry] = []
    skipped = 0
    for row in rows:
        source = _cell(row, mapping, "source")
        target = _cell(row, mapping, "target")
        if not source or not target:
            skipped += 1
            continue
        entry = Entry(source=source, target=target)
        entry.source_variants = [Variant(t) for t in _list(_cell(row, mapping, "source_variants"))]
        entry.target_variants = [Variant(t) for t in _list(_cell(row, mapping, "target_variants"))]
        entry.target_variants += [Variant(t, forbidden=True)
                                  for t in _list(_cell(row, mapping, "forbidden_targets"))]
        entry.forbidden = _cell(row, mapping, "forbidden").lower() in _TRUE
        entry.part_of_speech = _cell(row, mapping, "part_of_speech")
        entry.definition = _cell(row, mapping, "definition")
        entry.notes = _cell(row, mapping, "notes")
        entry.domain = _cell(row, mapping, "domain")
        entries.append(entry)
    return entries, skipped
