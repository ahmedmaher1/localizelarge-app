"""Phase 4: every file format survives extract → pseudo-translate → merge → re-extract.

For each sample in tests/fixtures/formats/ the test checks that:

* every text unit of the merged file equals its pseudo-translation, inline tags included;
* the merged file opens (python-docx, openpyxl, an XML parser, json.loads, …).

PO and XLIFF are bilingual: the translation goes into the target field and the source
stays, so their targets are read from the merged file itself.

Needs the built sidecar JAR and Java; skipped otherwise.
"""
import json
import os
import re
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lxml import etree  # noqa: E402

from localizelarge import formats  # noqa: E402
from modules.okapi_sidecar import OkapiSidecar  # noqa: E402
from modules.pseudo_translate import pseudo_translate_text  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "formats"
SAMPLES = sorted(f"sample{ext}" for fmt in formats.import_formats() for ext in fmt.extensions[:1])
BILINGUAL = {".po", ".xlf", ".xlf2"}
ARABIC = "مرحبا بالعالم"
CHINESE = "你好，世界"


@pytest.fixture(scope="module")
def sidecar():
    sc = OkapiSidecar()
    if not sc.is_installed() or sc._find_java() is None:
        pytest.skip("Okapi sidecar JAR or Java not available")
    if not sc.start():
        pytest.skip("Okapi sidecar could not be started")
    try:
        if sc.get_version() != OkapiSidecar.EXPECTED_VERSION:
            pytest.skip("the sidecar JAR is not the version the client expects: rebuild it")
        yield sc
    finally:
        sc.stop()


def pseudo(text):
    # Accents only: no markers and no added words, so sentence ends stay sentence ends.
    return pseudo_translate_text(text, expansion=0, markers=False)


def units(sc, path, segment=False):
    result = sc.extract(str(path), "en", "fr", segment, None)
    return [(s["id"], s["segmentIndex"], s.get("sourceWithTags") or s["source"])
            for s in result["segments"] if s["source"].strip()]


def round_trip(sc, name, out_dir):
    source = FIXTURES / name
    extracted = units(sc, source)
    assert extracted, f"nothing was extracted from {name}"
    expected = [pseudo(text) for _, _, text in extracted]
    merged = out_dir / name
    sc.merge(str(source), [{"id": uid, "segmentIndex": 0, "translation": text}
                           for (uid, _, _), text in zip(extracted, expected)],
             "en", "fr", str(merged), None)
    return extracted, expected, merged


def xml_parses(data):
    etree.fromstring(data)


def package_opens(path):
    with zipfile.ZipFile(path) as package:
        assert package.testzip() is None
        for name in package.namelist():
            if name.endswith((".xml", ".rels")) and package.getinfo(name).file_size:
                xml_parses(package.read(name))


def po_targets(text):
    return [json.loads('"' + m + '"') for m in re.findall(r'^msgstr "(.*)"$', text, re.M) if m]


def xliff_targets(data):
    root = etree.fromstring(data)
    return ["".join(t.itertext()) for t in root.iter("{*}target")]


def output_opens(path):
    """Open the merged file with a reader for its format; return its text."""
    ext = path.suffix
    if ext == ".docx":
        import docx
        document = docx.Document(str(path))
        return "\n".join(p.text for p in document.paragraphs)
    if ext == ".xlsx":
        import openpyxl
        book = openpyxl.load_workbook(str(path))
        return "\n".join(str(c.value) for sheet in book for row in sheet.iter_rows() for c in row
                         if c.value is not None)
    if ext in (".pptx", ".odt", ".ods", ".odp", ".idml"):
        package_opens(path)
        with zipfile.ZipFile(path) as package:
            return "\n".join(package.read(n).decode("utf-8", "replace") for n in package.namelist()
                             if n.endswith(".xml"))
    data = path.read_bytes()
    text = data.decode("utf-8")
    if ext in (".xml", ".xlf", ".xlf2"):
        xml_parses(data)
    elif ext == ".html":
        assert etree.HTML(text) is not None
    elif ext == ".json":
        loaded = json.loads(text)
        assert loaded["count"] == 3, "a number in the JSON file changed"
        text = json.dumps(loaded, ensure_ascii=False)
    elif ext == ".properties":
        text = text.encode("ascii", "replace").decode("unicode_escape") if "\\u" in text else text
    elif ext == ".vtt":
        assert text.startswith("WEBVTT")
    elif ext == ".srt":
        assert re.search(r"^\d\d:\d\d:\d\d,\d{3} --> ", text, re.M)
    return text


@pytest.mark.parametrize("name", SAMPLES)
def test_round_trip(sidecar, name, tmp_path):
    extracted, expected, merged = round_trip(sidecar, name, tmp_path)
    ext = merged.suffix

    if ext in BILINGUAL:
        # The source stays; the translation is the target.
        assert [t for _, _, t in units(sidecar, merged)] == [t for _, _, t in extracted]
        text = merged.read_text(encoding="utf-8")
        targets = po_targets(text) if ext == ".po" else xliff_targets(merged.read_bytes())
        plain = [re.sub(r"<[^>]+>", "", t) for t in expected]
        if ext == ".po":
            assert targets == expected
        else:
            assert targets == plain
            # Inline tags are in the targets, not only the text.
            tagged = sum(1 for t in expected if "<" in t)
            inline = re.findall(r"<target[^>]*>.*?</target>", text, re.S)
            assert sum(1 for t in inline if re.search(r"<(g|x|pc|ph)\b", t)) == tagged
    else:
        again = [t for _, _, t in units(sidecar, merged)]
        assert again == expected

    opened = output_opens(merged)
    # Something was translated, and the non-Latin text is still there.
    assert "Qúářtéřlý" in opened or "qúářtéřlý" in opened
    assert ARABIC in opened and CHINESE in opened


def test_tags_survive_in_formats_that_have_them(sidecar, tmp_path):
    for name, tags in (("sample.docx", ("<b>", "<i>")), ("sample.html", ("<b>", "<i>")),
                       ("sample.xlf", ("<b>", "<i>", "<x1/>")), ("sample.json", ("<b>", "<i>"))):
        extracted, expected, merged = round_trip(sidecar, name, tmp_path)
        joined = " ".join(t for _, _, t in extracted)
        for tag in tags:
            assert tag in joined, f"{name}: {tag} not in the extracted text"


def test_tags_written_as_text_in_json_are_kept(sidecar, tmp_path):
    """<b> inside a JSON string is text, not an inline code. It must not be dropped."""
    _, _, merged = round_trip(sidecar, "sample.json", tmp_path)
    body = json.loads(merged.read_text(encoding="utf-8"))["body"]
    assert body == "Thíš šéñtéñçé háš <b>bóld</b> áñd <i>ítálíç</i> wóřdš."


def test_a_tag_the_source_does_not_have_is_dropped(sidecar, tmp_path):
    source = FIXTURES / "sample.txt"
    (uid, _, text), *_ = units(sidecar, source)
    merged = tmp_path / "sample.txt"
    sidecar.merge(str(source), [{"id": uid, "segmentIndex": 0, "translation": "<b>Rapport</b>"}],
                  "en", "fr", str(merged), None)
    assert merged.read_text(encoding="utf-8").splitlines()[0] == "Rapport"


def test_the_docx_link_and_formatting_are_kept(sidecar, tmp_path):
    import docx
    _, _, merged = round_trip(sidecar, "sample.docx", tmp_path)
    document = docx.Document(str(merged))
    runs = {r.text: r for p in document.paragraphs for r in p.runs}
    assert runs["bóld"].bold and runs["ítálíç"].italic
    xml = zipfile.ZipFile(merged).read("word/document.xml").decode("utf-8")
    assert "<w:hyperlink" in xml and "úšéř ğúídé" in xml
    rels = zipfile.ZipFile(merged).read("word/_rels/document.xml.rels").decode("utf-8")
    assert "https://example.com/guide" in rels


def test_opendocument_parts_do_not_overwrite_each_other(sidecar, tmp_path):
    """OpenDocument numbers its text units again in every part of the package.
    The ids the sidecar reports are unique, so the body text is not replaced by
    the document properties."""
    extracted, _, merged = round_trip(sidecar, "sample.odt", tmp_path)
    ids = [uid for uid, _, _ in extracted]
    assert len(ids) == len(set(ids))
    content = zipfile.ZipFile(merged).read("content.xml").decode("utf-8")
    assert "Qúářtéřlý řépóřt" in content


def test_xliff_2_with_an_xliff_1_extension_is_recognised(sidecar, tmp_path):
    copy = tmp_path / "version2.xlf"
    copy.write_bytes((FIXTURES / "sample.xlf2").read_bytes())
    result = sidecar.extract(str(copy), "en", "fr", False, None)
    assert result["filterUsed"] == "okf_xliff2"
    assert sidecar.extract(str(FIXTURES / "sample.xlf"), "en", "fr", False, None)["filterUsed"] == "okf_xliff"


def _merge_sentences(sc, source, target_lang, translate, out):
    sentences = units(sc, source, segment=True)
    sc.merge(str(source), [{"id": uid, "segmentIndex": index, "translation": translate(text)}
                           for uid, index, text in sentences],
             "en", target_lang, str(out), None)
    return sentences


def test_a_line_break_between_sentences_is_kept(sidecar, tmp_path):
    """Two sentences of one PO string, separated by a line break in the source."""
    source = tmp_path / "lines.po"
    source.write_text('msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n\n'
                      'msgid "Save the file.\\nThen close it."\nmsgstr ""\n', encoding="utf-8")
    merged = tmp_path / "out.po"
    sentences = _merge_sentences(sidecar, source, "fr", pseudo, merged)
    assert [t for _, _, t in sentences] == ["Save the file.", "Then close it."]
    assert po_targets(merged.read_text(encoding="utf-8")) == ["Šávé thé fílé.\nThéñ çlóšé ít."]


def test_sentences_are_joined_with_a_space_or_with_nothing_by_target_language(sidecar, tmp_path):
    source = tmp_path / "two.txt"
    source.write_text("Save the file. Then close it.\n", encoding="utf-8")

    french = tmp_path / "fr.txt"
    sentences = _merge_sentences(sidecar, source, "fr", pseudo, french)
    assert len(sentences) == 2
    assert french.read_text(encoding="utf-8").strip() == "Šávé thé fílé. Théñ çlóšé ít."

    chinese = tmp_path / "zh.txt"
    replies = iter(["保存文件。", "然后关闭它。"])
    _merge_sentences(sidecar, source, "zh-CN", lambda _text: next(replies), chinese)
    assert chinese.read_text(encoding="utf-8").strip() == "保存文件。然后关闭它。"
