# Local LLM: llama.cpp router for VS Code and Open WebUI

A single server on `:10001` with one profile per model. Each request carries the
model name and the router loads that profile, unloading the previous one (two
models are never in VRAM at once). Copilot and Open WebUI switch models on their
own when a model is picked in their selector.

Profiles live in `Router/models.ini` (local, not committed). Start from
`Router/models.ini.example`. Each section name is a model id, and it must match
the id configured in each client (`"model"` field).

## Setup after cloning

```bash
cp llm.conf.example llm.conf                        # set SERVER_BUILD
cp Router/models.ini.example Router/models.ini      # set your models
cp aliases.sh.example aliases.sh                    # set LLM and DEFAULT_MODEL
```

1. Put a llama.cpp build in `Servers/` and the `.gguf` files in `Models/`.
2. Load the aliases from `C:\Program Files\Git\etc\profile.d\aliases.sh`:
   `[ -f /d/LLM/aliases.sh ] && . /d/LLM/aliases.sh` (with your path).
3. Compile the launcher (see below) if you want the Open WebUI double-click.

## Usage

**VS Code (Copilot):** start the router from Git Bash and pick the model in Copilot.

```bash
llama start                      # router + DEFAULT_MODEL preloaded
llama start <model-id>           # or preload another profile
llama status                     # which model is loaded
llama stop                       # stop everything
```

**Open WebUI:** double-click `Router\LocalLLM-Launcher.exe`.
- If `llama start` is already running, it reuses that router and, when its
  window is closed, only shuts down Open WebUI (VS Code keeps working).
- If there is no router, it starts one and stops it on exit.
- If another llama-server that is not the router is running, it stops it and
  starts the router.

Both can be used at the same time. If they ask for different models at once, the
router switches back and forth on every request (each switch takes seconds).

## Files

Repo layout:

```
Models\     one .gguf (and its mmproj) per model, no scripts
Router\     router.sh, models.ini, Open WebUI launcher
Servers\    llama.cpp builds (active one: SERVER_BUILD in llm.conf, or "llama server")
Tests\      tests ("llama test")
llm.conf    general configuration (active build)
aliases.sh  Git Bash aliases ("llama" command)
```

Inside `Router\webui\`:

```
../router.sh                    llama-server in router mode (:10001)
../models.ini                   one section per model with its parameters
../LocalLLM-Launcher.exe        Open WebUI launcher (double-click)
LocalLLM-Launcher.ps1           launcher source
start-open-webui.sh             starts Open WebUI (uvx, no Docker) against :10001
logs/router.log                 router output when started with "llama start"
logs/launcher-llama.log         router output when started by the launcher
logs/launcher-webui.log         Open WebUI output
```

## Recommended Open WebUI settings (once)

- **Hide coding-only profiles:** Admin Panel > Settings > Models, disable them so
  only the general-purpose profiles show up in the selector.
- **Task model** (titles, etc.) = current model (Admin Panel > Settings >
  Interface). If it points to another model, every title triggers a model switch.
- **Disable secondary tasks** that use the GPU on every message (same screen):
  follow-up suggestions, tags and autocomplete.

## Changing a model's parameters

Edit its section in `models.ini` (keys are llama-server flags without the leading
dashes) and restart the router (`llama stop` + `llama start`). There is no need
to recompile the `.exe`.

## Compiling the .exe

Only needed after changing the `.ps1` (or after cloning, since the `.exe` is not
committed):

```powershell
cd D:\LLM\Router
Import-Module ps2exe      # first time: Install-Module ps2exe -Scope CurrentUser
Invoke-ps2exe .\webui\LocalLLM-Launcher.ps1 .\LocalLLM-Launcher.exe -title "Local LLM"
```

## Notes

- Every model switch is a new load into VRAM. After many switches Windows can
  degrade the VRAM: if everything gets slow, `llama vram` confirms it and a
  reboot fixes it.
- Models are only used through the router: their folders contain only the
  `.gguf` and the `mmproj`. All the configuration is in `models.ini`.
- Tests to check or tune a model: `llama test` (see `Tests/README.md`).
