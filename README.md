**English** | [Español](README.es.md)

# Local LLM

Local language models on a Windows PC, served by a single
[llama.cpp](https://github.com/ggml-org/llama.cpp) server in **router mode**: one
server on `localhost:10001` with one profile per model. Each request carries a
model id and the router loads that profile, unloading the previous one. VS Code
Copilot (coding agent) and Open WebUI (chat with vision and web search) switch
models on their own when you pick one in their selector.

This README walks through the setup step by step.

## Contents

1. [Requirements](#1-requirements)
2. [Get the repo](#2-get-the-repo)
3. [Configure the example files](#3-configure-the-example-files)
4. [Install the `llama` command](#4-install-the-llama-command)
5. [Add a llama.cpp build (Servers)](#5-add-a-llamacpp-build-servers)
6. [Add models (Models + models.ini)](#6-add-models-models--modelsini)
7. [Start and check](#7-start-and-check)
8. [Connect the clients](#8-connect-the-clients)
9. [Daily use](#9-daily-use)
10. [Troubleshooting](#10-troubleshooting)

## Layout

```
Models/          one folder per model: .gguf (+ mmproj for vision)      [not committed]
Servers/         llama.cpp builds, one folder each                      [not committed]
Router/
  router.sh            starts llama-server in router mode
  models.ini           model profiles                                    [local]
  models.ini.example   template
  webui/               Open WebUI launcher (see Router/webui/README.md)
Tests/           speed, vision, context, sampling, reasoning and agentic tests
llm.conf         general configuration (active llama.cpp build)         [local]
aliases.sh       Git Bash aliases: the "llama" command                  [local]
*.example        templates for the local files
```

*Local* files hold your own setup and are ignored by git. You create them once
from their `*.example` template.

## 1. Requirements

- Windows 10/11 with [Git for Windows](https://git-scm.com/download/win). All
  scripts run in **Git Bash**.
- A GPU supported by a llama.cpp build (Vulkan works on AMD, NVIDIA and Intel).
- Python 3 for the tests (standard library only).
- Optional: [uv](https://docs.astral.sh/uv/) for Open WebUI
  (`winget install astral-sh.uv`) and the PS2EXE PowerShell module to compile the
  Open WebUI launcher (`Install-Module ps2exe -Scope CurrentUser`).

## 2. Get the repo

```bash
git clone <repo-url> /d/LLM
cd /d/LLM
```

Any location works. The examples below assume `D:\LLM` (`/d/LLM` in Git Bash).

## 3. Configure the example files

Create the three local files from their templates:

```bash
cp llm.conf.example llm.conf
cp aliases.sh.example aliases.sh
cp Router/models.ini.example Router/models.ini
```

| File | What to set | Example |
|---|---|---|
| `llm.conf` | `SERVER_BUILD`: name of the llama.cpp folder inside `Servers/` (step 5) | `SERVER_BUILD="llama-b11146-bin-win-vulkan-x64"` |
| `aliases.sh` | `LLM`: repo path in Git Bash format | `LLM="/d/LLM"` |
|  | `DEFAULT_MODEL`: profile that `llama start` preloads (a section of `models.ini`) | `DEFAULT_MODEL="My-Coder-Model"` |
| `Router/models.ini` | one section per model (step 6) | see `models.ini.example` |

`llm.conf` and `models.ini` can wait until steps 5 and 6.

## 4. Install the `llama` command

Git Bash loads every script in `C:\Program Files\Git\etc\profile.d\` when it
starts. Make its `aliases.sh` load the repo's (edit it as administrator, or
create it if it does not exist):

```bash
# C:\Program Files\Git\etc\profile.d\aliases.sh
[ -f /d/LLM/aliases.sh ] && . /d/LLM/aliases.sh
```

Open a **new** Git Bash terminal and run `llama`: it prints the available commands.

## 5. Add a llama.cpp build (Servers)

1. Download a Windows build from the
   [llama.cpp releases](https://github.com/ggml-org/llama.cpp/releases), for
   example `llama-bXXXXX-bin-win-vulkan-x64.zip`. Router mode
   (`--models-preset`) needs a recent build.
2. Unzip it into its own folder inside `Servers/`, keeping the original name:

   ```
   Servers/
     llama-b11146-bin-win-vulkan-x64/
       llama-server.exe
       ggml-*.dll ...
   ```

3. Make it the active build. Either set `SERVER_BUILD` in `llm.conf`, or run:

   ```bash
   llama server                                    # lists builds, * marks the active one
   llama server llama-b11146-bin-win-vulkan-x64    # switches (checks llama-server.exe exists)
   ```

4. Check that it sees your GPU and note the device name (`Vulkan0` is usual):

   ```bash
   /d/LLM/Servers/llama-b11146-bin-win-vulkan-x64/llama-server.exe --list-devices
   ```

Several builds can live side by side. To try a new one without switching:
`SERVER_BUILD=<folder> llama start`.

## 6. Add models (Models + models.ini)

1. **Put the files in `Models/`**, one folder per model, with the `.gguf` and,
   for vision models, its projector (`mmproj-*.gguf`) next to it:

   ```
   Models/
     Qwen3.6-35B-A3B-UD-IQ4_XS/
       Qwen3.6-35B-A3B-UD-IQ4_XS.gguf
       mmproj-F16.gguf
   ```

   Split models (`-00001-of-0000N.gguf`) go in the same folder; point to the first part.

2. **Add a profile to `Router/models.ini`**: a section whose name is the model id
   and whose keys are llama-server flags without the leading dashes.

   ```ini
   [My-Coder-Model]
   model = D:/LLM/Models/Qwen3.6-35B-A3B-UD-IQ4_XS/Qwen3.6-35B-A3B-UD-IQ4_XS.gguf
   n-cpu-moe = 22
   ctx-size = 131072
   temp = 0.6
   ```

   - Use absolute paths with forward slashes, and put comments on their own lines (`;`).
   - Shared settings go in `[*]`; a key in a model section overrides it.
   - Vision: add `mmproj = <path>`. Without vision: `no-mmproj = true`.
   - Sampling: use the values from the model card (they differ for coding and general use).
   - `n-cpu-moe` (MoE models only) keeps the experts of the first N layers in RAM
     when the model does not fit in VRAM. See step 7 to tune it.
   - MTP (`spec-type = draft-mtp`) only works with models that ship an MTP head
     (repos ending in `-MTP-GGUF`).

   One `.gguf` can have several profiles (for example coding without vision and
   general use with vision): they are separate sections pointing to the same file.

## 7. Start and check

```bash
llama start My-Coder-Model     # starts the router and loads that profile
llama status                   # active build, profiles and which one is loaded (*)
llama vram                     # "OK" = the model fits entirely in VRAM
llama test speed --model My-Coder-Model
llama stop
```

**Checklist for a new model**

1. `llama start <id>` loads without errors (log: `Router/webui/logs/router.log`).
2. `llama vram` says OK. If it warns, part of the model is in shared memory: raise
   `n-cpu-moe`, lower `ctx-size` or use a q4_0 KV cache.
3. `llama test speed` gives sensible numbers at 2k / 32k / 64k.
4. With vision: `llama test vision --model <id>`.
5. For MoE models, look for the **lowest** `n-cpu-moe` that still says OK after the
   speed test: lower values overflow and run slower. Procedure in
   [Tests/README.md](Tests/README.md).
6. Optionally, compare quality with `llama test reasoning` and `llama test agentic`.

## 8. Connect the clients

### VS Code Copilot

Add the profiles as custom models in `%APPDATA%\Code\User\chatLanguageModels.json`.
The `id` must match a section of `models.ini` **exactly**: Copilot sends it in
every request and the router uses it to pick the profile. When VS Code asks for
the API key, use `apikey` (the `--api-key` in `router.sh`).

```json
[
  {
    "name": "Local",
    "vendor": "customendpoint",
    "apiType": "chat-completions",
    "models": [
      {
        "id": "My-Coder-Model",
        "name": "My coder model",
        "url": "http://localhost:10001/v1",
        "toolCalling": true,
        "vision": false,
        "thinking": true,
        "maxInputTokens": 114688,
        "maxOutputTokens": 16384
      }
    ]
  }
]
```

- `maxInputTokens + maxOutputTokens` must not exceed the profile's `ctx-size`.
- `"vision": true` only for profiles that load an `mmproj`.
- Copilot cannot start processes: run `llama start` before using it.

### Open WebUI

Compile the launcher once, then double-click it:

```powershell
cd D:\LLM\Router
Import-Module ps2exe
Invoke-ps2exe .\webui\LocalLLM-Launcher.ps1 .\LocalLLM-Launcher.exe -title "Local LLM"
```

`Router\LocalLLM-Launcher.exe` starts Open WebUI with `uvx` (no Docker) at
`http://localhost:3000`, opens it in a dedicated browser window and shuts it down
when that window closes. If `llama start` is already running it reuses that router,
so VS Code and Open WebUI can work at the same time. Recommended settings and
details: [Router/webui/README.md](Router/webui/README.md).

## 9. Daily use

```bash
llama start [model-id]       # router in the background (+ DEFAULT_MODEL preloaded)
llama status                 # what is loaded
llama stop                   # stop everything
llama server [folder]        # list / switch llama.cpp builds
llama vram                   # VRAM health
llama test <test>            # speed | vision | benchmark | context | sampling | reasoning | agentic
```

To change a model's parameters: edit its section in `Router/models.ini`, then
`llama stop` + `llama start`.

## 10. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Missing .../llm.conf` or `.../models.ini` | Local file not created | `cp` it from its `.example` (step 3) |
| `Build not found: .../Servers/...` | `SERVER_BUILD` does not match a folder | `llama server` to list builds and pick one |
| `llama: command not found` | Aliases not loaded | Step 4, then open a new Git Bash terminal |
| The client says the model is unknown | Its `id` differs from the section name | Make them identical (case included) |
| Everything is 2-3x slower than usual | Windows degraded the VRAM after many restarts, or the model overflows | `llama vram`; if it warns, reboot or raise `n-cpu-moe` |
| Copilot: error 500 "image input is not supported" | `"vision": true` on a profile without `mmproj` | Set `"vision": false`, reload VS Code, new chat |
| Copilot: "Cannot have more than 128 tools" | Copilot limit, not the server's | Disable tools or MCP servers in the Copilot tool picker |
| Answers come back empty | Reasoning used up the output tokens | Raise the client's max output tokens or set `reasoning-budget` |

## Notes

- Lessons from tuning on a Radeon RX 9070 XT (16 GB): Windows can degrade the
  VRAM after many restarts (reboot fixes it); a MoE in Q4 with some expert layers
  in RAM beats a dense model in Q3; overflowing VRAM is slower than putting layers
  in RAM on purpose; MTP adds 15-50% when it fits; long reasoning is the main cost
  of a local agent; synthetic tests saturate, a real task tells models apart.
- More detail: [Router/webui/README.md](Router/webui/README.md) (router and
  Open WebUI) and [Tests/README.md](Tests/README.md) (tests and tuning).
