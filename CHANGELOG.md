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

### File formats

- Import and export through Okapi for DOCX, XLSX, PPTX, ODT, ODS, ODP, HTML, XLIFF 1.2 and
  2.0, PO, IDML, Markdown, JSON, YAML, Java properties, CSV, plain text, XML, WebVTT and
  SRT. One table, `okapi-sidecar/src/main/resources/formats.json`, is read by both the
  file-format service and the app.
- An XLIFF 2.0 file named `.xlf` or `.xliff` is recognised by its content.
- Export keeps what stood between the sentences of a paragraph: a line break inside a PO or
  JSON string is kept, and Chinese, Japanese and Thai targets get no space between
  sentences.
- Tags written as text in a file (`<b>` inside a JSON or YAML string) are kept on export.
- XLIFF 1.2 export keeps `<g>` formatting tags in the target.

### Security

- The Okapi file-format service listens on `127.0.0.1` only, on a free port chosen at each
  start, and requires a random per-session token. It has no CORS, sanitises upload names,
  deletes temporary files after each request and exits when the app closes or is killed.
- Okapi Framework 1.48.0, Javalin 6.7.0, Jackson 2.22.4.
- API keys are stored in one file, `%APPDATA%\LocalizeLarge\api-keys.locked.json`,
  encrypted by Windows DPAPI for your Windows account. They are never written in clear text.
  A key found in clear text in an old settings file is moved into the locked file.
- One network layer creates every connection to an AI provider or LanguageTool. It allows
  only the configured hosts, refuses everything else and logs host names only.
- The status bar, AI Settings and the batch translate dialog say "Text stays on this
  computer" or "Text is sent to {provider}".
- LanguageTool is off until you enter the address of your own server. The public
  LanguageTool service is never used.
- Model lists are never fetched at start-up. You can type any model ID.
- The app writes nothing to the Windows registry.
- Fixed a crash that could happen while the app was closing.

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
