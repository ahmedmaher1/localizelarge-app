# Demo project

A short English → Arabic project that shows the quality features.

| File | What it is |
|---|---|
| `demo-en-ar.docx` | The English source document (a pump maintenance guide, 11 sentences). |
| `demo-en-ar.llproj` | The translation as delivered, with errors planted for the demo, and its issues. The scorecard says **FAIL**. |
| `demo-en-ar-reviewed.llproj` | The same after review: the text corrected, the issues marked fixed or rejected. The scorecard says **PASS**. |
| `demo-glossary.tbx` | The glossary the glossary findings were made with. |

Open a project with **Project → Open**, then **QA → Quality panel**.

What the delivered project holds:

- **QA findings**: a missing full stop, a wrong number, a word written twice, a wrong e-mail
  address, an empty target.
- **Glossary findings**: a forbidden term, and approved terms that are missing.
- **Issues a reviewer added**: an omission in a safety instruction (critical) and a
  mistranslation (minor).
- **Two AI proposals**, open and not counted. They were written by hand for this sample
  and say so in their author field; no AI was called to make this demo.

To see glossary checks run live, import `demo-glossary.tbx` into a glossary
(**Termbases → Import**), activate it for the project, and choose **QA → Run QA**. Without
it, Run QA leaves the saved glossary findings as they are.

The projects are built by `tools/build_demo.py`, which drives the real app.
