**English** | [Español](README.es.md)

# Router and Open WebUI

How the llama.cpp router works and how to use it from VS Code and Open WebUI.
For the initial setup (example files, builds and models), see the
[main README](../../README.md).

## How the router works

`Router/router.sh` starts `llama-server` with no model of its own and with
`--models-preset Router/models.ini`, which turns it into a router on `:10001`:

1. A client (Copilot, Open WebUI) sends a request with `"model": "<id>"`.
2. The router looks for the section `[<id>]` in `models.ini`.
3. If that profile is not loaded, it unloads the current one (`--models-max 1`)
   and starts a child `llama-server` with the section's flags on an internal port.
4. It forwards the request to that child.

Consequences:

- The client's model `id` and the section name must be **identical**.
- Every model is a separate process: to stop everything, stop every
  `llama-server`, not only the one listening on `:10001` (`llama stop` does it).
- Switching models takes as long as loading the new one (seconds).
- Every switch is a new load into VRAM. After many switches Windows can degrade
  the VRAM: if everything gets slow, `llama vram` confirms it and a reboot fixes it.
- `router.sh` reads the active build from `llm.conf` (`SERVER_BUILD`). A
  `SERVER_BUILD` environment variable takes precedence, to try a build once.

## VS Code (Copilot)

Copilot cannot start processes, so start the router first and then pick the model
in Copilot:

```bash
llama start                      # router + DEFAULT_MODEL preloaded
llama start <model-id>           # or preload another profile
llama status                     # which model is loaded
llama stop                       # stop everything
```

## Open WebUI

Double-click `Router\LocalLLM-Launcher.exe`. It:

1. Reuses the router if `llama start` is already running. If another
   llama-server that is not the router is running, it stops it and starts the
   router with a hidden window.
2. Starts Open WebUI in the background (`start-open-webui.sh`, with `uvx`, no
   Docker) and shows its progress until it answers on `:3000`.
3. Opens a dedicated browser window (`--app` with its own Chromium/Edge/Brave
   profile), without tabs or address bar.
4. Hides its console and waits for that window to close.
5. On close, it shuts down Open WebUI and, only if it started it, the router.

VS Code and Open WebUI can be used at the same time. If they ask for different
models at once, the router switches back and forth on every request.

### Recommended Open WebUI settings (once, in Admin Panel)

- **Hide coding-only profiles** (Settings > Models) so only the general-purpose
  ones show up in the selector.
- **Task model = current model** (Settings > Interface). If it points to another
  model, every chat title triggers a model switch.
- **Disable secondary tasks** (same screen): follow-up suggestions, tags and
  autocomplete. With reasoning enabled, each one thinks before answering and uses
  the GPU on every message.

### start-open-webui.sh

| Variable | Value |
|---|---|
| `DATA_DIR` | `C:/open-webui/data` (users, chats and settings) |
| `OPENAI_API_BASE_URL` | `http://localhost:10001/v1` |
| `OPENAI_API_KEY` | `apikey` |
| `ENABLE_WEB_SEARCH` / `WEB_SEARCH_ENGINE` | `true` / `duckduckgo` |
| `ENABLE_TAGS / AUTOCOMPLETE / FOLLOW_UP_GENERATION` | `false` |

Most of them only apply to a fresh install: they are stored in the database when
it is created, and from then on the Admin Panel settings win.

## Files

```
../router.sh                    llama-server in router mode (:10001)
../models.ini                   one section per model with its parameters   [local]
../models.ini.example           template
../LocalLLM-Launcher.exe        Open WebUI launcher (double-click)          [compiled]
LocalLLM-Launcher.ps1           launcher source
start-open-webui.sh             starts Open WebUI (uvx, no Docker) against :10001
logs/router.log                 router output when started with "llama start"
logs/launcher-llama.log         router output when started by the launcher
logs/launcher-webui.log         Open WebUI output
```

## Changing a model's parameters

Edit its section in `models.ini` (keys are llama-server flags without the leading
dashes) and restart the router (`llama stop` + `llama start`). There is no need to
recompile the `.exe`.

## Compiling the .exe

The `.exe` is not committed. Download it from the [releases](https://github.com/robmab/llama-corral/releases)
and put it in `Router/`, or compile it yourself (again after changing the `.ps1`):

```powershell
cd D:\LLM\Router
Import-Module ps2exe      # first time: Install-Module ps2exe -Scope CurrentUser
Invoke-ps2exe .\webui\LocalLLM-Launcher.ps1 .\LocalLLM-Launcher.exe -title "Local LLM"
```

The launcher works out the `Router` folder from its own location, so it does not
depend on where the repo is cloned.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Open WebUI "starts" instantly but talks to another model | Another Open WebUI was still running on `:3000` | Close its window first; use one launcher at a time |
| Environment variables have no effect | They are only read when the database is created | Change them in Admin Panel > Settings |
| A `.webui_secret_key` file appears in `Router/` | Open WebUI stores its session key in the folder it starts from | Normal; if deleted, you have to log in again |
| Slow answers on every message | Secondary tasks (titles, tags, follow-ups) using another model or reasoning | Recommended settings above |
| The launcher waits and gives up on llama-server | Missing local file, wrong build or a model error | Check `logs/launcher-llama.log` |
