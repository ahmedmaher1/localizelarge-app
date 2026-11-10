"""TBX-Basic import and export.

Writes TBX-Basic in the TBX 2 form (ISO 30042:2008, root ``martif``), which is the one
CAT tools read most widely. Reads that form and the TBX 3 form (root ``tbx``, 2019).

How a termbase entry maps to TBX:

=====================  =========================================================
Termbase               TBX
=====================  =========================================================
entry                  ``termEntry`` (TBX 3: ``conceptEntry``), ``id`` = the uid
domain                 ``descrip type="subjectField"`` on the entry
definition             ``descrip type="definition"`` on the entry
notes                  ``note`` on the entry
main term              the first ``tig``/``termSec`` of a ``langSet``/``langSec``
variants               the following ones
part of speech         ``termNote type="partOfSpeech"`` on the main source term
forbidden              ``termNote type="administrativeStatus"`` =
                       ``deprecatedTerm-admn-sts``
=====================  =========================================================
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from lxml import etree

from .model import Entry, Variant

XML_NS = "http://www.w3.org/XML/1998/namespace"
XML_LANG = f"{{{XML_NS}}}lang"
PREFERRED = "preferredTerm-admn-sts"
ADMITTED = "admittedTerm-admn-sts"
DEPRECATED = "deprecatedTerm-admn-sts"
# TBX-Basic values for part of speech.
PARTS_OF_SPEECH = ("noun", "verb", "adjective", "adverb", "properNoun", "other")


@dataclass
class TbxFile:
    """What a TBX file holds for one language pair."""
    entries: List[Entry] = field(default_factory=list)
    languages: List[str] = field(default_factory=list)   # every language in the file
    source_lang: str = ""
    target_lang: str = ""
    skipped: int = 0     # entries without a term in both languages
    title: str = ""


def _local(element) -> str:
    tag = element.tag
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _children(element, *names):
    return [child for child in element if _local(child) in names]


def _text(element) -> str:
    return " ".join("".join(element.itertext()).split())


def _base(code: str) -> str:
    return (code or "").replace("_", "-").split("-")[0].lower()


def _parser():
    # No network, no entity expansion: a TBX file is data from outside.
    return etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False,
                           huge_tree=False, remove_comments=True)


def languages_in(path: str) -> List[str]:
    """The language codes used in a TBX file, in order of first use."""
    root = etree.parse(str(path), _parser()).getroot()
    found: List[str] = []
    for element in root.iter():
        if _local(element) in ("langSet", "langSec"):
            code = element.get(XML_LANG) or element.get("lang") or ""
            if code and code not in found:
                found.append(code)
    return found


def _pick(languages: List[str], wanted: Optional[str], fallback_index: int,
          exclude: str = "") -> str:
    if wanted:
        for code in languages:
            if code.lower() == wanted.lower():
                return code
        for code in languages:
            if _base(code) == _base(wanted):
                return code
    others = [code for code in languages if code != exclude]
    if len(others) > fallback_index:
        return others[fallback_index]
    return others[0] if others else ""


def _terms_of(lang_element) -> List[Tuple[str, Dict[str, str]]]:
    """(term, notes) for each term of a language section, in file order."""
    out = []
    containers = [el for el in lang_element.iter() if _local(el) in ("tig", "ntig", "termSec")]
    for container in containers:
        term = next((el for el in container.iter() if _local(el) == "term"), None)
        if term is None or not _text(term):
            continue
        notes: Dict[str, str] = {}
        for el in container.iter():
            if _local(el) == "termNote" and el.get("type"):
                notes[el.get("type")] = _text(el)
        out.append((_text(term), notes))
    return out


def _is_forbidden(notes: Dict[str, str]) -> bool:
    status = notes.get("administrativeStatus", "")
    return status.startswith("deprecated") or status.startswith("superseded")


def read_tbx(path: str, source_lang: Optional[str] = None,
             target_lang: Optional[str] = None) -> TbxFile:
    """Read the entries of a TBX file for one language pair.

    Without language codes, the first language in the file is the source and the
    second the target. A code matches exactly or by its language part ("en" finds
    "en-GB").
    """
    root = etree.parse(str(path), _parser()).getroot()
    result = TbxFile(languages=languages_in(path))
    result.source_lang = _pick(result.languages, source_lang, 0)
    result.target_lang = _pick(result.languages, target_lang, 0, exclude=result.source_lang)
    title = next((el for el in root.iter() if _local(el) == "title"), None)
    result.title = _text(title) if title is not None else ""

    for entry_el in root.iter():
        if _local(entry_el) not in ("termEntry", "conceptEntry"):
            continue
        by_lang: Dict[str, List[Tuple[str, Dict[str, str]]]] = {}
        for lang_el in _children(entry_el, "langSet", "langSec"):
            code = lang_el.get(XML_LANG) or lang_el.get("lang") or ""
            by_lang.setdefault(code, []).extend(_terms_of(lang_el))
        source_terms = by_lang.get(result.source_lang, [])
        target_terms = by_lang.get(result.target_lang, [])
        if not source_terms or not target_terms:
            result.skipped += 1
            continue

        entry = Entry(source=source_terms[0][0], target=target_terms[0][0],
                      uid=entry_el.get("id") or "")
        entry.forbidden = _is_forbidden(target_terms[0][1])
        entry.part_of_speech = (source_terms[0][1].get("partOfSpeech")
                                or target_terms[0][1].get("partOfSpeech") or "")
        entry.source_variants = [Variant(text, _is_forbidden(notes))
                                 for text, notes in source_terms[1:]]
        entry.target_variants = [Variant(text, _is_forbidden(notes))
                                 for text, notes in target_terms[1:]]

        # Entry-level information: direct children and those in descripGrp.
        notes_found: List[str] = []
        for child in entry_el:
            name = _local(child)
            holders = [child] if name in ("descrip", "note") else (
                list(child) if name == "descripGrp" else [])
            for holder in holders:
                kind = _local(holder)
                if kind == "descrip" and holder.get("type") == "subjectField":
                    entry.domain = entry.domain or _text(holder)
                elif kind == "descrip" and holder.get("type") == "definition":
                    entry.definition = entry.definition or _text(holder)
                elif kind == "note" and _text(holder):
                    notes_found.append(_text(holder))
        entry.notes = "\n".join(notes_found)
        result.entries.append(entry)
    return result


def _add(parent, tag: str, text: Optional[str] = None, **attributes):
    element = etree.SubElement(parent, tag)
    for key, value in attributes.items():
        element.set(XML_LANG if key == "lang" else key, value)
    if text is not None:
        element.text = text
    return element


def _add_term(lang_set, text: str, status: str, part_of_speech: str = ""):
    tig = _add(lang_set, "tig")
    _add(tig, "term", text)
    if part_of_speech:
        _add(tig, "termNote", part_of_speech, type="partOfSpeech")
    _add(tig, "termNote", status, type="administrativeStatus")


def write_tbx(path: str, entries: List[Entry], source_lang: str, target_lang: str,
              title: str = "Glossary") -> int:
    """Write entries as a TBX-Basic file. Returns the number of entries written."""
    root = etree.Element("martif")
    root.set("type", "TBX-Basic")
    root.set(XML_LANG, source_lang or "en")
    header = _add(root, "martifHeader")
    file_desc = _add(header, "fileDesc")
    _add(_add(file_desc, "titleStmt"), "title", title)
    _add(_add(file_desc, "sourceDesc"), "p", "Exported from Localize Large")
    _add(_add(header, "encodingDesc"), "p", "TBXBasiccoreStructV02.dtd", type="XCSURI")
    body = _add(_add(root, "text"), "body")

    used_ids = set()
    written = 0
    for number, entry in enumerate(entries, 1):
        if not (entry.source or "").strip() or not (entry.target or "").strip():
            continue
        entry_id = entry.uid.strip() if entry.uid else ""
        # An XML id must start with a letter or an underscore, and be unique.
        if not entry_id or not (entry_id[0].isalpha() or entry_id[0] == "_"):
            entry_id = f"c{entry_id or number}"
        entry_id = "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in entry_id)
        while entry_id in used_ids:
            entry_id += "-x"
        used_ids.add(entry_id)

        term_entry = _add(body, "termEntry", id=entry_id)
        if entry.domain:
            _add(term_entry, "descrip", entry.domain, type="subjectField")
        if entry.definition:
            _add(term_entry, "descrip", entry.definition, type="definition")
        for line in (entry.notes or "").split("\n"):
            if line.strip():
                _add(term_entry, "note", line.strip())

        source_set = _add(term_entry, "langSet", lang=source_lang)
        _add_term(source_set, entry.source, PREFERRED, entry.part_of_speech)
        for variant in entry.source_variants:
            _add_term(source_set, variant.text, DEPRECATED if variant.forbidden else ADMITTED)

        target_set = _add(term_entry, "langSet", lang=target_lang)
        _add_term(target_set, entry.target, DEPRECATED if entry.forbidden else PREFERRED)
        for variant in entry.target_variants:
            _add_term(target_set, variant.text, DEPRECATED if variant.forbidden else ADMITTED)
        written += 1

    tree = etree.ElementTree(root)
    tree.write(str(path), xml_declaration=True, encoding="UTF-8", pretty_print=True,
               doctype='<!DOCTYPE martif SYSTEM "TBXBasiccoreStructV02.dtd">')
    return written
