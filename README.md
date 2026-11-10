# Localize Large

A free Windows desktop CAT (computer-assisted translation) tool for localization managers
in companies that translate in-house with AI.

**Status: in development. A preview (1.0.0-preview.1, unsigned) is on localizelarge.com;
version 1.0.0 is not released yet.** This file describes the
state of the code, not the finished product. The build plan has eight phases; see
`CHANGELOG.md` for what is done.

Localize Large is based on Supervertaler Workbench by Michael Beijer (MIT License).

## What it is meant to do

- **Files stay in the company.** With a local model (Ollama) no text leaves the computer.
  With Claude, OpenAI or Gemini, text goes only to the provider the company chose, under
  its own key.
- **Every translation can be checked.** Quality checks, glossary checks and MQM error
  annotation with scores are part of the free app. Quality packs (rules, categories and
  thresholds for one client) are data files the same app loads.

## What works today

Inherited from the base and working: projects, translation memory, termbases, AI
translation, find and replace, spellcheck, the analysis report (HTML, XLSX, CSV), the
file-based bilingual formats (memoQ, Trados, Phrase, CafeTran, Déjà Vu).

Done for Localize Large so far (Phases 1 to 5 of 8):

- **Identity.** The new name and icon, fixed data folders, the `.llproj` project format
  (older `.svproj` files open and are saved as `.llproj`), the About dialog.
- **Scope.** Everything outside the v1 scope is removed or disabled; `docs/REMOVED.md` lists
  each item, and which parts are disabled but not yet deleted.
- **Security.** The file-format service listens on `127.0.0.1` only, on a random port, and
  needs a per-session token. API keys live in one file locked by Windows DPAPI and nowhere
  in clear text. One network layer allows only Claude, OpenAI, Gemini, the configured Ollama
  address and a LanguageTool server you enter, and logs host names only. The app says where
  text goes. See `docs/security/`.

- **File formats.** DOCX, XLSX, PPTX, ODT, ODS, ODP, HTML, XLIFF 1.2 and 2.0, PO, IDML,
  Markdown, JSON, YAML, Java properties, CSV, plain text, XML, WebVTT and SRT, each with a
  round-trip test (import, translate, export, import again).
- **Translation memory.** Fuzzy scores where 100% means the same text; a lookup in a
  100,000-unit memory takes about 0.12 s (`docs/PERFORMANCE.md`).
- **Glossaries.** TBX-Basic import and export; XLSX and CSV import with column mapping.
- **Segmentation.** Okapi's default rules for every language, with your own rules in front.
- **Right-to-left.** Arabic, Hebrew, Persian and Urdu in the grid and the editor.

- **Quality.** QA checks, glossary checks, MQM issue annotation with scores, a Quality
  panel, quality reports (HTML, PDF, XLSX, JSON) and AI pre-annotation (beta). A demo
  project is in `samples/`. Details: `docs/QUALITY.md`.

Not done yet: quality packs (Phase 6), the AI provider
rework (Phase 7) and the release work (Phase 8: SBOM, signing, user guide, test on a clean
Windows 11 machine). A preview ZIP is published for testing (see `docs/RELEASING.md`).

## Where it keeps data

| What | Windows folder |
|---|---|
| Settings, API keys (locked), prompts, quality packs | `%APPDATA%\LocalizeLarge\` |
| Databases, logs, caches | `%LOCALAPPDATA%\LocalizeLarge\` |

`localizelarge/paths.py` owns every path. The app does not read or write any Supervertaler
folder. Details: `docs/DATA_LOCATIONS.md` and `docs/security/SECURITY_FACTS.md`.

## Development

See `docs/DEV_SETUP.md`. In short: Python 3.12, a virtual environment,
`pip install -r requirements.txt pytest pytest-qt`, JDK 17 or newer and Maven for the
sidecar in `okapi-sidecar/`.

Run the tests with a throwaway profile:

```bash
HOME=$(mktemp -d) QT_QPA_PLATFORM=offscreen python -m pytest tests/ -q
```

New code goes in the `localizelarge/` package. `Supervertaler.py` and `modules/` are the
base; they keep their internal names so upstream fixes are easier to bring over.

## Building the Windows ZIP

See `docs/RELEASING.md`. The build runs on a GitHub Actions Windows runner
(**Actions → Build Windows ZIP → Run workflow**) and keeps the ZIP as a private artifact.

## License

GPL-3.0-or-later; see `LICENSE`. Files from Supervertaler Workbench keep their MIT notice;
see `NOTICE`. Third-party software is listed in `THIRD_PARTY_LICENSES.md`.

Website: [localizelarge.com](https://localizelarge.com) · Support: contact@localizelarge.com
