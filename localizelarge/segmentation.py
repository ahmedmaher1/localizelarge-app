"""The user's segmentation rules, in the form the Okapi sidecar takes.

Documents are split into sentences by the sidecar, with Okapi's default rules: ICU
sentence breaks plus exception rules, for every language. The rules a user adds in
Settings → Segmentation Rules are sent with each import and export, and the sidecar
puts them in front of the default rules.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from modules.segmentation_rules import SegmentationRules

OPTION_KEY = "segmentation"


def sidecar_spec(rules: Optional[SegmentationRules]) -> Optional[Dict[str, Any]]:
    """The "segmentation" option for the sidecar, or None when the user has no rules of
    their own (the sidecar then uses the default rules unchanged).

    SRX rules are Java regular expressions, and the sidecar is Java, so the user's
    expressions are passed on as written.
    """
    if rules is None:
        return None
    out = []
    for rule in rules.rules:
        if not rule.enabled or not (rule.before or rule.after):
            continue
        out.append({"break": bool(rule.is_break), "before": rule.before, "after": rule.after})
    # No break after an abbreviation the user listed ("np" means "np.").
    for abbreviation in rules.extra_abbreviations:
        abbreviation = abbreviation.strip().rstrip(".")
        if abbreviation:
            out.append({"break": False, "before": r"(?i)\b\Q" + abbreviation + r"\E\.", "after": r"\s"})
    if rules.split_at_line_breaks:
        out.append({"break": True, "before": r"\n", "after": ""})
    if not out and rules.use_builtin_rules:
        return None
    return {"rules": out, "useDefault": bool(rules.use_builtin_rules)}


def with_segmentation(options: Optional[Dict[str, Any]],
                      rules: Optional[SegmentationRules]) -> Optional[Dict[str, Any]]:
    """The sidecar options with the user's segmentation rules added."""
    spec = sidecar_spec(rules)
    if spec is None:
        return options
    merged = dict(options or {})
    merged[OPTION_KEY] = spec
    return merged
