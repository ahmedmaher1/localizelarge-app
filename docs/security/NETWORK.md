# Network connections

Every connection Localize Large can make. The same list, as data, is in
`network-connections.json` beside this file; `tests/test_network_inventory.py` fails if the
source code names a host that is not declared.

**Status:** this describes the code on `main`. No release build exists yet, so every row is
marked `confirmed: false` in the data file until it has been checked against a Windows build.

## Summary

- With no AI provider set up, the app contacts nothing outside the computer.
- With Ollama on this computer, no text leaves the computer.
- With Claude, OpenAI or Gemini, text goes only to that provider, under your own API key,
  and only when you start an AI feature.
- The app sends nothing to Localize Large: no telemetry, no update check, no licence check.

The status bar always shows one of two lines: **Text stays on this computer** or
**Text is sent to {provider}**. The same line is in Settings → AI Settings and in the batch
translate dialog before you start.

## The connections

| Connection | Goes to | When | On by default |
|---|---|---|---|
| Anthropic Claude | `api.anthropic.com` (HTTPS) | When you use an AI feature with Claude selected and a key saved | No |
| OpenAI | `api.openai.com` (HTTPS) | As above, with OpenAI | No |
| Google Gemini | `generativelanguage.googleapis.com` (HTTPS) | As above, with Gemini | No |
| Ollama | `http://localhost:11434` by default; you can change the address | When you select Ollama or refresh its model list, when you translate with it, and every four minutes if you turn on "keep the model warm" | No |
| LanguageTool | Only a server address you enter, for example `http://localhost:8081` | Only when you run QA → Check with LanguageTool | No |
| Okapi file-format service | `127.0.0.1`, a free port chosen at each start | While the app is open | Yes (this computer only) |

### What is sent to an AI provider

The text you ask the AI to work on and its context: the segment, neighbouring segments,
matching translation memory entries, glossary terms, your prompt instructions, and any
document you attach in the AI Assistant. Your API key travels in the request header.

Nothing is sent until you start an AI feature: translating a segment or a batch with AI, the
AI Assistant, or QuickTrans.

### Ollama on another computer

If you enter an Ollama address that is not this computer, the app says so: the line reads
"Text is sent to Ollama at {host}".

### LanguageTool

LanguageTool is off until you enter the address of a LanguageTool server you run yourself.
There is no default server. LanguageTool's public service (`api.languagetool.org`) is never
used, and the app refuses it if you enter it.

To run LanguageTool on your own computer, download the LanguageTool server from
languagetool.org, start it (it needs Java), and enter its address, normally
`http://localhost:8081`, in the LanguageTool dialog.

### The Okapi file-format service

A small Java program that ships inside the app and reads and writes document formats. It is
not an internet connection:

- It listens on `127.0.0.1` only. Other computers on the network cannot reach it.
- It uses a different free port each time the app starts.
- Every request must carry a random token created for that session. Another program on the
  same computer cannot use it without that token.
- It stops when the app closes, including when the app is killed.

## How this is enforced

`localizelarge/security/net.py` is the only place that creates HTTP clients for the AI
providers and LanguageTool.

- The three cloud addresses are fixed in the code. A setting or an environment variable
  cannot point the app at another address.
- A request to any host that is not configured is refused before it is sent. This includes
  redirects.
- Each request is logged as its purpose and host name, for example
  `[net] claude -> api.anthropic.com`. Text, addresses beyond the host name, headers and keys
  are never logged by the network layer.
- Requests to this computer never go through a proxy.

A company proxy, if you set one under Settings → AI Settings, is used for the cloud
providers, and for Ollama only when Ollama is on another computer.

## Links the app can open in your browser

These open in your own web browser when you click them. The app itself does not fetch them.

- `localizelarge.com`: Help, the download page ("Check for updates") and the website link in
  the About dialog.
- `ollama.com`: where to get Ollama, from the Ollama setup dialog.
- Links to spelling dictionaries and spellcheck libraries in Settings → Spellcheck
  (`github.com`, `hunspell.memoq.com`, `extensions.libreoffice.org`, `hunspell.github.io`).

## What the app never does

- No telemetry or usage statistics.
- No automatic update check, and no manual one made by the app: "Check for updates" opens
  the download page in your browser.
- No download of any part of itself at first run or later.
- No machine-translation services, web lookups or embedded browser.
- No model list is fetched unless you select Ollama or click its refresh button.
