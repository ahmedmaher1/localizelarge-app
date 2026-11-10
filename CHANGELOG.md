# Changelog

Localize Large is based on Supervertaler Workbench 1.10.376 by Michael Beijer (MIT
License). The history of that project is in its own repository.

## 1.0.0 — not released yet

### Changed

- New name, logo and icon: Localize Large.
- Data folders are fixed: `%APPDATA%\LocalizeLarge\` for settings and
  `%LOCALAPPDATA%\LocalizeLarge\` for databases, logs and caches. There is no data-location
  choice at first run. No Supervertaler folder is read or written.
- Projects are saved as `.llproj`. An older `.svproj` opens as before and is saved as a
  `.llproj` beside it; the `.svproj` is left untouched.
- New About dialog with a Licenses button. "Check for updates" opens the download page in
  the browser; the app itself sends nothing.
- The default light theme uses the accent colour `#0F766E`.
- License of the app as a whole: GPL-3.0-or-later. Files from Supervertaler Workbench keep
  their MIT notice (see `NOTICE`).

### Removed

Details and reasons are in `docs/REMOVED.md`.

- Global (system-wide) hotkeys, AutoHotkey support, start with the computer, the tray icon
  and running in the background.
- Voice commands.
- The embedded browser, Superbrowser and SuperLookup's web resources. SuperLookup keeps its
  translation-memory and termbase search.
- PDF Rescue and the image extractor.
- Machine-translation services (Google Translate, DeepL, Microsoft, Amazon, ModernMT,
  MyMemory) and AI providers other than Claude, OpenAI, Gemini and Ollama.
- The Trados and memoQ live bridges. The file-based bilingual formats stay.
- The usage ping, the GitHub update check, the setup wizard and links to Supervertaler
  sites.
- The download of the Okapi sidecar and Java runtime at first use.
