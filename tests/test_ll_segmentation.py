"""Phase 4: sentence segmentation of documents.

The sidecar splits with Okapi's default SRX document (ICU sentence breaks plus
exception rules) for every language. The user's own rules go in front of it.

The sidecar tests need the built JAR and Java; they are skipped otherwise.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from localizelarge.segmentation import sidecar_spec, with_segmentation  # noqa: E402
from modules.okapi_sidecar import OkapiSidecar  # noqa: E402
from modules.segmentation_rules import Rule, SegmentationRules  # noqa: E402


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


CASES = [
    # English: sentence ends and common abbreviations.
    ("en", "Dr. Smith arrived at 5 p.m. on Monday. He met Mr. Jones, e.g. for lunch. "
           "The U.S. team won! Did they? Yes.",
     ["Dr. Smith arrived at 5 p.m. on Monday.", "He met Mr. Jones, e.g. for lunch.",
      "The U.S. team won!", "Did they?", "Yes."]),
    ("en", "See Fig. 3 and No. 5 for details. The price is $3.50 per unit. Version 2.0 is out.",
     ["See Fig. 3 and No. 5 for details.", "The price is $3.50 per unit.", "Version 2.0 is out."]),
    ("en", 'He said "Stop." Then he left. Visit example.com today.',
     ['He said "Stop."', "Then he left.", "Visit example.com today."]),
    # French: titles, "c.-à-d.", and a space before ? and !.
    ("fr", "M. Dupont est arrivé. Mme Martin, c.-à-d. la directrice, est partie. Quoi ? Oui !",
     ["M. Dupont est arrivé.", "Mme Martin, c.-à-d. la directrice, est partie.", "Quoi ?", "Oui !"]),
    # German: titles, ordinal dates, "z. B.".
    ("de", "Dr. Müller kam am 3. Mai an. Das ist z. B. ein Test. Wirklich? Ja!",
     ["Dr. Müller kam am 3. Mai an.", "Das ist z. B. ein Test.", "Wirklich?", "Ja!"]),
    # Arabic: the Arabic question mark.
    ("ar", "ما اسمك؟ اسمي أحمد. هل أنت بخير؟ نعم! شكرا.",
     ["ما اسمك؟", "اسمي أحمد.", "هل أنت بخير؟", "نعم!", "شكرا."]),
    # Chinese and Japanese: full-width sentence ends, no spaces.
    ("zh", "你好。今天天气很好！你吃饭了吗？我们走吧。",
     ["你好。", "今天天气很好！", "你吃饭了吗？", "我们走吧。"]),
    ("ja", "こんにちは。今日はいい天気ですね！ご飯を食べましたか？行きましょう。",
     ["こんにちは。", "今日はいい天気ですね！", "ご飯を食べましたか？", "行きましょう。"]),
]


@pytest.mark.parametrize("language,text,expected", CASES, ids=[f"{c[0]}-{i}" for i, c in enumerate(CASES)])
def test_default_rules(sidecar, language, text, expected):
    assert sidecar.segment(text, language) == expected


def test_a_region_code_uses_the_rules_of_its_language(sidecar):
    assert sidecar.segment("Dr. Smith is here. He is early.", "en-GB") == \
        ["Dr. Smith is here.", "He is early."]
    assert sidecar.segment("ما اسمك؟ اسمي أحمد.", "ar-EG") == ["ما اسمك؟", "اسمي أحمد."]


# ── The user's rules ──────────────────────────────────────────────────

def test_no_user_rules_means_no_option():
    assert sidecar_spec(SegmentationRules()) is None
    assert sidecar_spec(None) is None
    assert with_segmentation({"word_hidden": False}, SegmentationRules()) == {"word_hidden": False}
    assert with_segmentation(None, SegmentationRules()) is None


def test_rules_abbreviations_and_line_breaks_become_sidecar_rules():
    rules = SegmentationRules(
        split_at_line_breaks=True,
        extra_abbreviations=["np", "m.in"],
        rules=[Rule(is_break=True, before=";", after=r"\s"),
               Rule(is_break=False, before=r"approx\.", after=r"\s", enabled=False)])
    spec = sidecar_spec(rules)
    assert spec["useDefault"] is True
    assert spec["rules"] == [
        {"break": True, "before": ";", "after": r"\s"},
        {"break": False, "before": r"(?i)\b\Qnp\E\.", "after": r"\s"},
        {"break": False, "before": r"(?i)\b\Qm.in\E\.", "after": r"\s"},
        {"break": True, "before": r"\n", "after": ""},
    ]
    assert with_segmentation({"word_hidden": False}, rules) == {"word_hidden": False,
                                                              "segmentation": spec}


def test_a_user_exception_stops_a_default_break(sidecar):
    text = "See Sect. Four for details. Then go on."
    assert sidecar.segment(text, "en") == ["See Sect.", "Four for details.", "Then go on."]
    spec = sidecar_spec(SegmentationRules(extra_abbreviations=["sect"]))
    assert sidecar.segment(text, "en", spec) == ["See Sect. Four for details.", "Then go on."]


def test_a_user_break_rule_adds_a_break(sidecar):
    text = "First part; second part. Third."
    assert sidecar.segment(text, "en") == ["First part; second part.", "Third."]
    spec = sidecar_spec(SegmentationRules(rules=[Rule(is_break=True, before=";", after=r"\s")]))
    assert sidecar.segment(text, "en", spec) == ["First part;", "second part.", "Third."]


def test_user_rules_alone_when_the_default_rules_are_off(sidecar):
    spec = sidecar_spec(SegmentationRules(use_builtin_rules=False,
                                          rules=[Rule(is_break=True, before=r"\|", after="")]))
    assert sidecar.segment("One. Two.|Three. Four.", "en", spec) == ["One. Two.|", "Three. Four."]


def test_a_broken_user_rule_is_skipped_not_fatal(sidecar):
    spec = {"rules": [{"break": True, "before": "(", "after": ""}], "useDefault": True}
    assert sidecar.segment("One. Two.", "en", spec) == ["One.", "Two."]


def test_user_rules_apply_to_a_document_import_and_its_export(sidecar, tmp_path):
    source = tmp_path / "doc.txt"
    source.write_text("See Sect. Four for details. Then go on.\n", encoding="utf-8")
    options = with_segmentation(None, SegmentationRules(extra_abbreviations=["sect"]))

    plain = sidecar.extract(str(source), "en", "fr", True, None)
    assert [s["source"] for s in plain["segments"]] == ["See Sect.", "Four for details.", "Then go on."]

    result = sidecar.extract(str(source), "en", "fr", True, options)
    sentences = [(s["id"], s["segmentIndex"], s["source"]) for s in result["segments"]]
    assert [t for _, _, t in sentences] == ["See Sect. Four for details.", "Then go on."]

    out = tmp_path / "out.txt"
    sidecar.merge(str(source), [{"id": uid, "segmentIndex": i, "translation": t.upper()}
                                for uid, i, t in sentences], "en", "fr", str(out), options)
    assert out.read_text(encoding="utf-8").strip() == "SEE SECT. FOUR FOR DETAILS. THEN GO ON."
