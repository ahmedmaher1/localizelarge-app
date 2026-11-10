"""Rebuild the sample files in this folder.

    python tests/fixtures/formats/make_samples.py

The samples are small files with bold and italic text, a link, a line break, inline
tags and non-Latin text. The round-trip tests in tests/test_ll_format_roundtrip.py
read them; they are committed, so the tests do not need this script.

The text formats are written out below. DOCX and XLSX need python-docx and openpyxl.
PPTX needs python-pptx; ODT, ODS and ODP are converted from the Office files with
LibreOffice (`soffice`). Those two tools are only needed to rebuild the samples: the
app does not use them. IDML is written by hand as a minimal package.
"""
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent

ARABIC = "مرحبا بالعالم"
CHINESE = "你好，世界"

TEXT_FILES = {
    "sample.html": f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Sample page</title>
</head>
<body>
<h1>Quarterly report</h1>
<p>This sentence has <b>bold</b> and <i>italic</i> words.</p>
<p>Read the <a href="https://example.com/guide">user guide</a> first.</p>
<p>First line<br>second line.</p>
<p>{ARABIC} and {CHINESE}.</p>
<img src="chart.png" alt="Sales chart">
</body>
</html>
""",
    "sample.xlf": f"""<?xml version="1.0" encoding="UTF-8"?>
<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">
<file original="sample.txt" source-language="en" target-language="fr" datatype="plaintext">
<body>
<trans-unit id="1"><source>Quarterly report</source></trans-unit>
<trans-unit id="2"><source>This sentence has <g id="1" ctype="bold">bold</g> and <g id="2" ctype="italic">italic</g> words.</source></trans-unit>
<trans-unit id="3"><source>First line<x id="1" ctype="lb"/>second line.</source></trans-unit>
<trans-unit id="4"><source>{ARABIC} and {CHINESE}.</source></trans-unit>
</body>
</file>
</xliff>
""",
    "sample.xlf2": f"""<?xml version="1.0" encoding="UTF-8"?>
<xliff version="2.0" xmlns="urn:oasis:names:tc:xliff:document:2.0" srcLang="en" trgLang="fr">
<file id="f1">
<unit id="1"><segment><source>Quarterly report</source></segment></unit>
<unit id="2"><segment><source>This sentence has <pc id="1">bold</pc> and <pc id="2">italic</pc> words.</source></segment></unit>
<unit id="3"><segment><source>First line<ph id="1"/>second line.</source></segment></unit>
<unit id="4"><segment><source>{ARABIC} and {CHINESE}.</source></segment></unit>
</file>
</xliff>
""",
    "sample.po": f"""msgid ""
msgstr ""
"Content-Type: text/plain; charset=UTF-8\\n"
"Content-Transfer-Encoding: 8bit\\n"

#: app.py:10
msgid "Quarterly report"
msgstr ""

#: app.py:11
msgid "This sentence has <b>bold</b> and <i>italic</i> words."
msgstr ""

#: app.py:12
msgid "First line\\nsecond line."
msgstr ""

#: app.py:13
msgid "{ARABIC} and {CHINESE}."
msgstr ""
""",
    "sample.md": f"""# Quarterly report

This sentence has **bold** and *italic* words.

Read the [user guide](https://example.com/guide) first.

- First item
- Second item with `code`

{ARABIC} and {CHINESE}.
""",
    "sample.json": f"""{{
  "title": "Quarterly report",
  "body": "This sentence has <b>bold</b> and <i>italic</i> words.",
  "lines": "First line\\nsecond line.",
  "nested": {{
    "greeting": "{ARABIC} and {CHINESE}."
  }},
  "count": 3
}}
""",
    "sample.yaml": f"""title: Quarterly report
body: "This sentence has <b>bold</b> and <i>italic</i> words."
nested:
  greeting: "{ARABIC} and {CHINESE}."
  link: "Read the user guide first."
count: 3
""",
    "sample.properties": """# Sample
title=Quarterly report
body=This sentence has <b>bold</b> and <i>italic</i> words.
lines=First line\\nsecond line.
greeting=\\u0645\\u0631\\u062d\\u0628\\u0627 \\u0628\\u0627\\u0644\\u0639\\u0627\\u0644\\u0645 and \\u4f60\\u597d\\uff0c\\u4e16\\u754c.
""",
    "sample.csv": f"""id,text,note
1,Quarterly report,heading
2,"This sentence has bold, and italic words.",body
3,{ARABIC} and {CHINESE}.,greeting
""",
    "sample.txt": f"""Quarterly report
This sentence has bold and italic words.
{ARABIC} and {CHINESE}.
""",
    "sample.xml": f"""<?xml version="1.0" encoding="UTF-8"?>
<doc xmlns:its="http://www.w3.org/2005/11/its" its:version="2.0">
<its:rules version="2.0">
<its:translateRule selector="//code" translate="no"/>
<its:withinTextRule selector="//b|//i|//br" withinText="yes"/>
</its:rules>
<title>Quarterly report</title>
<para>This sentence has <b>bold</b> and <i>italic</i> words.</para>
<para>First line<br/>second line.</para>
<para>{ARABIC} and {CHINESE}.</para>
<code>do_not_translate()</code>
</doc>
""",
    "sample.vtt": f"""WEBVTT

00:00:01.000 --> 00:00:04.000
This is the quarterly report.

00:00:05.000 --> 00:00:08.000
This sentence has <b>bold</b> and <i>italic</i> words.

00:00:09.000 --> 00:00:12.000
{ARABIC} and {CHINESE}.
""",
    "sample.srt": f"""1
00:00:01,000 --> 00:00:04,000
This is the quarterly report.

2
00:00:05,000 --> 00:00:08,000
This sentence has <b>bold</b> and <i>italic</i> words.

3
00:00:09,000 --> 00:00:12,000
{ARABIC} and {CHINESE}.
""",
}


def write_text_files():
    for name, text in TEXT_FILES.items():
        (HERE / name).write_text(text, encoding="utf-8", newline="\n")


def write_docx():
    import docx
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    document = docx.Document()
    document.add_heading("Quarterly report", level=1)
    p = document.add_paragraph("This sentence has ")
    p.add_run("bold").bold = True
    p.add_run(" and ")
    p.add_run("italic").italic = True
    p.add_run(" words.")

    p = document.add_paragraph("Read the ")
    rel = document.part.relate_to(
        "https://example.com/guide",
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
        is_external=True)
    link = OxmlElement("w:hyperlink")
    link.set(qn("r:id"), rel)
    run = OxmlElement("w:r")
    text = OxmlElement("w:t")
    text.text = "user guide"
    run.append(text)
    link.append(run)
    p._p.append(link)
    p.add_run(" first.")

    p = document.add_paragraph()
    run = p.add_run("First line")
    run.add_break()
    run.add_text("second line.")
    document.add_paragraph(f"{ARABIC} and {CHINESE}.")
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Left cell"
    table.cell(0, 1).text = "Right cell"
    document.save(str(HERE / "sample.docx"))


def write_xlsx():
    import openpyxl
    from openpyxl.cell.rich_text import CellRichText, TextBlock
    from openpyxl.cell.text import InlineFont

    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "Report"
    sheet["A1"] = "Quarterly report"
    sheet["A2"] = CellRichText(
        "This sentence has ", TextBlock(InlineFont(b=True), "bold"), " and ",
        TextBlock(InlineFont(i=True), "italic"), " words.")
    sheet["A3"] = f"{ARABIC} and {CHINESE}."
    sheet["B1"] = 1250
    book.save(str(HERE / "sample.xlsx"))


def write_pptx():
    from pptx import Presentation

    deck = Presentation()
    slide = deck.slides.add_slide(deck.slide_layouts[1])
    slide.shapes.title.text = "Quarterly report"
    frame = slide.placeholders[1].text_frame
    p = frame.paragraphs[0]
    p.add_run().text = "This sentence has "
    run = p.add_run()
    run.text = "bold"
    run.font.bold = True
    p.add_run().text = " and "
    run = p.add_run()
    run.text = "italic"
    run.font.italic = True
    p.add_run().text = " words."
    frame.add_paragraph().text = f"{ARABIC} and {CHINESE}."
    deck.save(str(HERE / "sample.pptx"))


def convert_with_libreoffice():
    soffice = shutil.which("soffice")
    if not soffice:
        print("LibreOffice not found: ODT, ODS and ODP not rebuilt")
        return
    for source, target in (("sample.docx", "odt"), ("sample.xlsx", "ods"), ("sample.pptx", "odp")):
        subprocess.run([soffice, "--headless", "--convert-to", target, "--outdir", str(HERE),
                        str(HERE / source)], check=True, capture_output=True)


IDML_FILES = {
    "mimetype": "application/vnd.adobe.indesign-idml-package",
    "designmap.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<?aid style="50" type="document" readerVersion="6.0" featureSet="257" product="8.0(370)" ?>
<Document xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging" DOMVersion="8.0" Self="d" StoryList="u10" ActiveLayer="ub">
<Language Self="Language/$ID/English%3a USA" Name="$ID/English: USA" SingleQuotes="‘’" DoubleQuotes="“”" PrimaryLanguageName="$ID/English" SublanguageName="$ID/USA" Id="269" HyphenationVendor="Hunspell" SpellingVendor="Hunspell"/>
<idPkg:Graphic src="Resources/Graphic.xml"/>
<idPkg:Fonts src="Resources/Fonts.xml"/>
<idPkg:Styles src="Resources/Styles.xml"/>
<idPkg:Preferences src="Resources/Preferences.xml"/>
<Layer Self="ub" Name="Layer 1" Visible="true" Locked="false" IgnoreWrap="false" ShowGuides="true" LockGuides="false" UI="true" Expendable="true" Printable="true"/>
<idPkg:MasterSpread src="MasterSpreads/MasterSpread_ud.xml"/>
<idPkg:Spread src="Spreads/Spread_uc.xml"/>
<idPkg:BackingStory src="XML/BackingStory.xml"/>
<idPkg:Story src="Stories/Story_u10.xml"/>
</Document>
""",
    "Resources/Graphic.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<idPkg:Graphic xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging" DOMVersion="8.0">
</idPkg:Graphic>
""",
    "Resources/Fonts.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<idPkg:Fonts xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging" DOMVersion="8.0">
</idPkg:Fonts>
""",
    "Resources/Styles.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<idPkg:Styles xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging" DOMVersion="8.0">
<RootCharacterStyleGroup Self="rc">
<CharacterStyle Self="CharacterStyle/$ID/[No character style]" Imported="false" Name="$ID/[No character style]"/>
</RootCharacterStyleGroup>
<RootParagraphStyleGroup Self="rp">
<ParagraphStyle Self="ParagraphStyle/$ID/[No paragraph style]" Name="$ID/[No paragraph style]" Imported="false" FontStyle="Regular" PointSize="12"/>
<ParagraphStyle Self="ParagraphStyle/$ID/NormalParagraphStyle" Name="$ID/NormalParagraphStyle" Imported="false">
<Properties><BasedOn type="string">$ID/[No paragraph style]</BasedOn></Properties>
</ParagraphStyle>
</RootParagraphStyleGroup>
<RootCellStyleGroup Self="rcell">
<CellStyle Self="CellStyle/$ID/[None]" Name="$ID/[None]"/>
</RootCellStyleGroup>
<RootTableStyleGroup Self="rtable">
<TableStyle Self="TableStyle/$ID/[No table style]" Name="$ID/[No table style]"/>
</RootTableStyleGroup>
<RootObjectStyleGroup Self="robject">
<ObjectStyle Self="ObjectStyle/$ID/[None]" Name="$ID/[None]"/>
</RootObjectStyleGroup>
</idPkg:Styles>
""",
    "Resources/Preferences.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<idPkg:Preferences xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging" DOMVersion="8.0">
<StoryPreference OpticalMarginAlignment="false" OpticalMarginSize="12" FrameType="TextFrameType" StoryOrientation="Horizontal" StoryDirection="LeftToRightDirection"/>
</idPkg:Preferences>
""",
    "MasterSpreads/MasterSpread_ud.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<idPkg:MasterSpread xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging" DOMVersion="8.0">
<MasterSpread Self="ud" ItemTransform="1 0 0 1 0 0" Name="A-Master" NamePrefix="A" BaseName="Master" ShowMasterItems="true" PageCount="1" OverriddenPageItemProps="">
<Page Self="ue" Name="A" GeometricBounds="0 0 792 612" ItemTransform="1 0 0 1 0 -396"/>
</MasterSpread>
</idPkg:MasterSpread>
""",
    "Spreads/Spread_uc.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<idPkg:Spread xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging" DOMVersion="8.0">
<Spread Self="uc" FlattenerOverride="Default" AllowPageShuffle="true" ItemTransform="1 0 0 1 0 0" ShowMasterItems="true" PageCount="1" BindingLocation="0" AppliedMaster="ud" Hidden="false">
<Page Self="uf" Name="1" AppliedMaster="ud" GeometricBounds="0 0 792 612" ItemTransform="1 0 0 1 0 -396"/>
<TextFrame Self="u11" ParentStory="u10" PreviousTextFrame="n" NextTextFrame="n" ContentType="TextType" ItemLayer="ub" Visible="true" Locked="false" Name="$ID/" ItemTransform="1 0 0 1 36 -360">
<Properties>
<PathGeometry>
<GeometryPathType PathOpen="false">
<PathPointArray>
<PathPointType Anchor="0 0" LeftDirection="0 0" RightDirection="0 0"/>
<PathPointType Anchor="0 720" LeftDirection="0 720" RightDirection="0 720"/>
<PathPointType Anchor="540 720" LeftDirection="540 720" RightDirection="540 720"/>
<PathPointType Anchor="540 0" LeftDirection="540 0" RightDirection="540 0"/>
</PathPointArray>
</GeometryPathType>
</PathGeometry>
</Properties>
</TextFrame>
</Spread>
</idPkg:Spread>
""",
    "XML/BackingStory.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<idPkg:BackingStory xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging" DOMVersion="8.0">
<XmlStory Self="ubs" AppliedTOCStyle="n" TrackChanges="false" StoryTitle="$ID/" AppliedNamedGrid="n">
<ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/$ID/NormalParagraphStyle">
<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/$ID/[No character style]"/>
</ParagraphStyleRange>
</XmlStory>
</idPkg:BackingStory>
""",
    "Stories/Story_u10.xml": f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<idPkg:Story xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging" DOMVersion="8.0">
<Story Self="u10" AppliedTOCStyle="n" TrackChanges="false" StoryTitle="$ID/" AppliedNamedGrid="n">
<StoryPreference OpticalMarginAlignment="false" OpticalMarginSize="12" FrameType="TextFrameType" StoryOrientation="Horizontal" StoryDirection="LeftToRightDirection"/>
<ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/$ID/NormalParagraphStyle">
<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/$ID/[No character style]"><Content>Quarterly report</Content><Br/></CharacterStyleRange>
</ParagraphStyleRange>
<ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/$ID/NormalParagraphStyle">
<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/$ID/[No character style]"><Content>This sentence has </Content></CharacterStyleRange>
<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/$ID/[No character style]" FontStyle="Bold"><Content>bold</Content></CharacterStyleRange>
<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/$ID/[No character style]"><Content> and </Content></CharacterStyleRange>
<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/$ID/[No character style]" FontStyle="Italic"><Content>italic</Content></CharacterStyleRange>
<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/$ID/[No character style]"><Content> words.</Content><Br/></CharacterStyleRange>
</ParagraphStyleRange>
<ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/$ID/NormalParagraphStyle">
<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/$ID/[No character style]"><Content>{ARABIC} and {CHINESE}.</Content></CharacterStyleRange>
</ParagraphStyleRange>
</Story>
</idPkg:Story>
""",
}


def write_idml():
    path = HERE / "sample.idml"
    with zipfile.ZipFile(path, "w") as package:
        package.writestr(zipfile.ZipInfo("mimetype"), IDML_FILES["mimetype"],
                         compress_type=zipfile.ZIP_STORED)
        for name, text in IDML_FILES.items():
            if name != "mimetype":
                package.writestr(name, text.encode("utf-8"), compress_type=zipfile.ZIP_DEFLATED)


def main():
    write_text_files()
    write_idml()
    write_docx()
    write_xlsx()
    try:
        write_pptx()
    except ImportError:
        print("python-pptx not installed: PPTX not rebuilt")
    convert_with_libreoffice()
    print("Samples written to", HERE)


if __name__ == "__main__":
    sys.exit(main())
