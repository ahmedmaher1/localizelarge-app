# Security facts

What Localize Large installs, writes, runs and contacts. This document feeds the website's
Security page, so every line must be true of the build.

**Status: the code on `main`, after Phase 3. No release build exists yet.** Lines that depend
on the Windows build are marked *(build: not yet verified)*. They are checked in Phase 8 on a
clean Windows 11 machine, and this document is updated then.

## Install

- **How it is delivered:** a ZIP file. There is no installer. *(build: not yet verified)*
- **Install location:** the folder where you extract the ZIP. Nothing is copied to Program
  Files or the Windows folder.
- **Admin rights:** none needed, to install or to run.
- **Windows registry:** the app writes nothing to it. A test checks that no code uses the
  registry or Qt's registry-backed settings.
- **Start-up entries, services, scheduled tasks, shell extensions, file associations:** none.
- **Background running:** none. There is no tray icon. Closing the window ends every process
  the app started.
- **System-wide hotkeys:** none. Shortcuts work only while the app's window has focus.

## What it writes, and where

The app has two data folders. Their locations are fixed; `localizelarge/paths.py` is the only
code that builds these paths.

### `%APPDATA%\LocalizeLarge\` (settings)

| File or folder | Contents |
|---|---|
| `api-keys.locked.json` | Your API keys, each encrypted by Windows for your Windows account (see "API keys") |
| `workbench\settings\settings.json` | Settings. Never an API key |
| `workbench\settings\` (other files) | Themes, keyboard shortcuts, recent projects, the last folder used in file dialogs, the QuickTrans window position |
| `prompt_library\` | The AI prompts that ship with the app and any you write |
| `workbench\dictionaries\` | Words you add to the spelling dictionary, and dictionaries you add |
| `workbench\ai_assistant\` | Documents you attach in the AI Assistant, converted to text. **This holds your content** |
| `workbench\backups\` | Timestamped copies of project files, if you turn that on. **This holds your content** |
| `workbench\usage\usage-YYYY-MM.jsonl` | One line per AI call: date, provider, model, token counts, estimated cost, project and file name, language pair. Never the text sent or received |
| `packs\` | Quality packs you install (from Phase 6) |

### `%LOCALAPPDATA%\LocalizeLarge\` (data that stays on this computer)

| File or folder | Contents |
|---|---|
| `resources\localizelarge.db` | Your translation memories and glossaries (SQLite). **This holds your content** |
| `logs\localizelarge.log`, `logs\localizelarge-previous.log` | The diagnostic log (see "Logs") |
| `cache\` | Reserved for caches. Nothing is written there yet |

### Your project files

Project files (`.llproj`), their backups (`.llproj.bak`), exported documents and reports are
written where you choose to save them. A project saved in its own folder can also keep a
copy of the source documents and a TMX backup of its translation memory in that folder.

### Temporary files

The file-format service copies each file it processes to a temporary folder (named
`okapi-…`, under the Windows temp folder) and deletes it when that request ends. A test
checks the deletion.

### What it never writes

In a Windows account folder that is completely empty, Windows itself adds an empty folder
`%LOCALAPPDATA%\Microsoft\Windows\Caches` when the app starts (seen in the build's start-up
test on Windows Server 2025). The app does not use it; on a normal computer it already
exists.

It never reads or writes a Supervertaler folder, and never writes API keys in clear text
anywhere: not to settings, logs, project files or exports. Tests check the folders and the
places keys are saved.

## API keys

- **One store:** `%APPDATA%\LocalizeLarge\api-keys.locked.json`.
- **Protection:** each key is encrypted with the Windows Data Protection API (DPAPI) for the
  current Windows account before it is written. The file cannot be unlocked on another
  computer or under another Windows account.
- **Which keys:** Claude, OpenAI and Gemini. Ollama needs no key.
- **In the app:** keys are shown masked in Settings, with a Show button.
- **Where keys go:** only in the request header to the provider they belong to.
- **Old settings files:** if a settings file from the base app holds a key in clear text, the
  app moves it into the locked store at start-up and removes it from the settings file.
- **Verified on Windows:** the automated tests, including the real DPAPI tests and a test
  that saves keys through the app and then searches every file for them, pass on a GitHub
  Actions Windows runner.

## Local services and ports

| Service | Address | Purpose |
|---|---|---|
| Okapi file-format service (Java) | `127.0.0.1`, a free port chosen at each start | Reads and writes document formats |

- It listens on the loopback address only; other computers cannot reach it.
- Every request must carry a random token created for that session.
- It starts with the app and exits when the app closes or is killed.
- There is no other local service, and no fixed port.

Running `netstat -ano` while the app is open shows one listening entry for the app's Java
process, on `127.0.0.1`. *(build: not yet verified by hand on Windows; an automated test
checks the listening address on the Windows runner.)*

## Network

See `NETWORK.md` and `network-connections.json`. In short: nothing leaves the computer unless
you set up a cloud AI provider and start an AI feature; the app sends nothing to Localize
Large; there is no telemetry and no update check.

## Bundled runtimes

*(build: not yet verified. The release build is Phase 8.)* The plan for the release ZIP:

- A Python runtime and the Python packages listed in `THIRD_PARTY_LICENSES.md`, packaged with
  PyInstaller.
- A minimal Java runtime built with `jlink` from Eclipse Temurin 17, used only by the
  file-format service. The app will not use a Java installed on the computer.
- The Okapi Framework 1.48.0 and the other Java libraries listed in
  `THIRD_PARTY_LICENSES.md`.

Until that build exists, the app runs from source and uses the Java found on the computer.

## Logs

- **Where:** `%LOCALAPPDATA%\LocalizeLarge\logs\`.
- **How long they are kept:** the log is one file that grows to about 2 MB, then becomes
  `localizelarge-previous.log` and a new file starts. At most two files, about 4 MB. Older
  content is overwritten. Nothing deletes the logs by date.
- **What they contain:** start-up information, the steps the app takes, errors, the host
  name of each network request, and messages from the file-format service.
- **Content warning:** some log lines include short excerpts of the text you are working on
  (for example the first 50 characters of a segment when a project is saved). Treat the logs
  as confidential. They never leave the computer unless you send them to someone.
- **API keys:** the app does not write API keys to the log. The network layer logs host
  names only.
- **Usage ledger:** the monthly `usage-YYYY-MM.jsonl` files described above are kept until you
  delete them.

## Offline behaviour

| Mode | Works without a network connection |
|---|---|
| No AI provider | Everything: projects, import and export, translation memory, glossaries, spellcheck, find and replace |
| Ollama on this computer | Everything, including AI translation |
| Claude, OpenAI or Gemini | Everything except the AI features, which show an error and keep your text |
| LanguageTool on this computer | The grammar check works |

The app needs no network connection to start and makes no request to another computer at
start-up. *(Checked on the source code; "network cable unplugged" on a Windows build: not yet
verified.)*

Getting an Ollama model is done by Ollama itself, which downloads it from `ollama.com`. That
is a download made by Ollama, at your request, not by Localize Large.

## Removing the app completely

1. Close the app.
2. Delete the folder where you extracted the ZIP.
3. Delete `%APPDATA%\LocalizeLarge\`. This removes settings, the locked API keys, prompts,
   backups, AI Assistant attachments and the usage ledger.
4. Delete `%LOCALAPPDATA%\LocalizeLarge\`. This removes your translation memories,
   glossaries and logs.
5. Your project files and exported documents are wherever you saved them; delete them if you
   want to.

Nothing else is left: no registry entries, services or start-up items.

## Signing

*(build: not yet verified.)* No signed build exists yet. Signing is an optional step of the
Phase 8 release; each release states whether it is signed.
