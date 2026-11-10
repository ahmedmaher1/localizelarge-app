# Localize Large

A free Windows desktop CAT (computer-assisted translation) tool for localization managers
in companies that translate in-house with AI.

**Status: in development. Version 1.0.0 is not released yet.** This file describes the
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

Inherited from the base and working: projects, DOCX and other imports through the Okapi
sidecar, translation memory, termbases, AI translation, find and replace, spellcheck.

Done for Localize Large so far: the new name and icon, fixed data folders, the `.llproj`
project format (older `.svproj` files open and are saved as `.llproj`), the About dialog.

Not done yet: removing the out-of-scope features, the security hardening, the extra file
formats, the quality features, quality packs and the Windows release build.

## Where it keeps data

| What | Windows folder |
|---|---|
| Settings, API keys (locked), prompts, quality packs | `%APPDATA%\LocalizeLarge\` |
| Databases, logs, caches | `%LOCALAPPDATA%\LocalizeLarge\` |

`localizelarge/paths.py` owns every path. The app does not read or write any Supervertaler
folder.

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

## License

GPL-3.0-or-later; see `LICENSE`. Files from Supervertaler Workbench keep their MIT notice;
see `NOTICE`. Third-party software is listed in `THIRD_PARTY_LICENSES.md`.

Website: [localizelarge.com](https://localizelarge.com) · Support: contact@localizelarge.com
