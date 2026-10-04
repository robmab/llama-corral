---
name: Bug report
about: Something does not start, crashes or behaves differently than documented
title: ""
labels: bug
assignees: ""
---

## What happened

<!-- A clear description of the problem. -->

## Steps to reproduce

1. 
2. 
3. 

## What you expected

## Environment

- llama-corral version or commit: <!-- e.g. v0.1.0, or `git log --oneline -1` -->
- Windows version: <!-- e.g. Windows 11 24H2 -->
- GPU and VRAM: <!-- e.g. RX 9070 XT 16 GB -->
- llama.cpp build: <!-- SERVER_BUILD in llm.conf, e.g. llama-b11146-bin-win-vulkan-x64 -->
- Client: <!-- VS Code Copilot / Open WebUI / tests / other -->

## Diagnostics

<details>
<summary><code>llama status</code></summary>

```
paste here
```
</details>

<details>
<summary><code>llama vram</code></summary>

```
paste here
```
</details>

<details>
<summary>Last lines of the log</summary>

<!-- Router/webui/logs/router.log (llama start) or logs/launcher-llama.log / launcher-webui.log (launcher).
     In Git Bash: tail -n 50 /d/LLM/Router/webui/logs/router.log -->

```
paste here
```
</details>

<details>
<summary>Model profile in <code>Router/models.ini</code></summary>

<!-- The section of the model involved. Remove anything private, such as personal paths. -->

```ini
paste here
```
</details>

## Anything else

<!-- Screenshots, what you already tried, whether a reboot changes anything (Windows can degrade VRAM after many restarts). -->
