# Localize Large — reference for AI-assisted development

Localize Large is a Windows desktop CAT tool (PyQt6) for in-house localization teams. It is
a fork of Supervertaler Workbench 1.10.376 by Michael Beijer (MIT), commit `f83e520`. The
build plan has eight phases; `CHANGELOG.md` and `docs/` show what is done.

## Layout

| What | Path |
|---|---|
| Main window (one very large file; read and edit by line range only) | `Supervertaler.py` |
| Base modules | `modules/` |
| **New code** | `localizelarge/` |
| Every data path | `localizelarge/paths.py` |
| Project file format (`.llproj`) | `localizelarge/project_format.py` |
| About dialog | `localizelarge/about.py` |
| Okapi sidecar (Java, Javalin REST) | `okapi-sidecar/` |
| Tests | `tests/` |
| Version (source of truth) | `pyproject.toml` |
| Removed features and why | `docs/REMOVED.md` |

## Rules

1. Search with grep before editing. Never read `Supervertaler.py` whole.
2. New code goes in `localizelarge/`. The monolith gets thin hooks only: a menu action, a
   panel, a call.
3. Change every user-visible string, path, user agent, URL and file extension to Localize
   Large. Python module and class names that users never see may keep "supervertaler".
4. Never remove the attribution to Michael Beijer or the MIT text in `NOTICE`.
5. Do not copy code from OmegaT or any other GPL CAT tool. Never add AGPL code. Record each
   new dependency, version and license in `THIRD_PARTY_LICENSES.md` in the same commit.
6. Nothing builds a data path by hand; ask `localizelarge/paths.py`. Never read or write a
   Supervertaler folder.
7. No silent network calls. A new connection must be listed in
   `docs/security/network-connections.json` in the same commit.
8. Never claim a feature in docs or UI that is not built and tested.
9. Each change ends with passing tests. A feature is done only when a test covers it.

## Tests

```bash
HOME=$(mktemp -d) QT_QPA_PLATFORM=offscreen python -m pytest tests/ -q --timeout=120
```

Always use a temporary home (and on Windows temporary `APPDATA` and `LOCALAPPDATA`), so no
real data is touched.

## Identity

Name "Localize Large"; app ID `com.localizelarge.app`; executable `LocalizeLarge.exe`;
project files `.llproj` (opens `.svproj`); quality packs `.llqp`; version 1.0.0; website
`localizelarge.com`; support `contact@localizelarge.com`.
