# Quality features

Code: `localizelarge/quality/` (issue model, QA checks, glossary checks, user interface)
and `localizelarge/mqm/` (typology, scoring, report, AI pre-annotation).

## One record for every finding

QA findings, glossary findings, issues a reviewer adds and AI proposals are all an `Issue`
(`localizelarge/quality/model.py`). An issue has an origin (`qa`, `glossary`, `human`,
`ai`), a rule, an MQM category, a severity, a status (`open`, `accepted`, `rejected`,
`fixed`), and optionally a span.

- A span counts characters in the text **without inline tags**.
- An issue stores a hash of that text. When the text changes, the issue shows as
  "needs check" and is no longer underlined. The span is never moved.
- Issues are saved in the project file under `"quality"`, with the quality profile and the
  record of AI runs.

## QA checks

`localizelarge/quality/checks/`. Each check is a class with an ID, a default severity and
a default MQM category; a profile can switch a check off or change its severity, category
and parameters. The list is in `CHANGELOG.md`; the tests in `tests/test_ll_qa_checks.py`
show what each one finds and what it leaves alone.

A new QA run keeps the decisions made on earlier findings: a finding someone rejected
stays rejected for as long as the text is unchanged.

## Glossary checks

`localizelarge/quality/glossary_check.py`, with the project's active glossaries.

| Rule | Finding |
|---|---|
| `glossary.required` | The source has a term; none of its approved translations is in the target (major). If one is found only through the Arabic rules below, the finding says "possibly the term" (minor). |
| `glossary.forbidden` | A forbidden translation of that term is in the target (major). |
| `glossary.inconsistent` | One term is translated with different approved variants in the project (minor). |

Matching is by whole words, in Unicode NFC, case-folded unless the entry is case-sensitive.
In Arabic the prefixes و ف ب ل ك ال may be attached to a term; that is a plain match. For
Arabic script, tatweel and diacritics are ignored and alef forms unified; a term found only
that way is the "possibly the term" case. Chinese, Japanese and Thai terms are searched as
strings.

## MQM

- **Typology**: MQM Core, 7 dimensions and 38 error types, in
  `localizelarge/data/mqm_core.json`, built by `tools/build_mqm_core.py` from the MQM
  Council's page. Names and definitions are unchanged.
- **Scoring** (`localizelarge/mqm/scoring.py`): the linear raw model and the linear
  calibrated model of the MQM Council (arXiv:2405.16969, Appendix A). The tests reproduce
  the worked examples given in the text of the paper and on the Council's scoring page.
  - The paper's scorecard figures are images; examples that exist only in a figure are
    not reproduced.
  - The non-linear model is not implemented.
  - A score below 0 is shown as 0.
- **Which issues count**: accepted ones; open ones if the profile says so (default: yes);
  open AI proposals only if the profile says so (default: no); rejected and fixed ones never.
- **Evaluated words**: the words of the source text of the project.

## Report

`localizelarge/mqm/report.py` builds the report once as data and writes HTML (one file,
nothing loaded from outside), PDF (Qt's `QTextDocument` and `QPrinter`), XLSX (Summary and
Issues sheets) and JSON (validated against `localizelarge/schemas/issues.schema.json`).

## AI pre-annotation (beta)

`localizelarge/mqm/ai_annotate.py`. The dialog shows where the text goes before anything
is sent. The reply must be a JSON array; it is validated, and a proposal is kept only when
the words it quotes are found exactly in the segment. Offsets are worked out by the app.
Dropped proposals are counted in the summary. The run's provider, model, token counts and
estimated cost go into the report.

It uses the same network layer as translation: no new connection.

## Not done

- Issues are not exported into XLIFF as ITS 2.0 Localization Quality Issue markup (the
  plan lists this as optional).
- The profile cannot be edited in the app yet; quality packs (Phase 6) supply profiles.
