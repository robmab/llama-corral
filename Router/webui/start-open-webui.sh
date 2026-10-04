#!/usr/bin/env bash
# Starts Open WebUI (no Docker) against the llama-server router.
# Requirements: uv installed (winget install astral-sh.uv) and the router running.
# Then open http://localhost:3000

LLAMA_PORT=10001
LLAMA_API_KEY="apikey"   # same as --api-key in router.sh

# Data directory (users, chats, settings): shared by every launcher.
export DATA_DIR="C:/open-webui/data"

# Model connection. Only read the FIRST time: afterwards the values saved in
# Admin Panel > Settings > Connections take over.
export ENABLE_OLLAMA_API="false"
export OPENAI_API_BASE_URL="http://localhost:${LLAMA_PORT}/v1"
export OPENAI_API_KEY="${LLAMA_API_KEY}"

# Web search with DuckDuckGo.
export ENABLE_WEB_SEARCH="true"
export WEB_SEARCH_ENGINE="duckduckgo"

# Secondary tasks that use the GPU on every message (with reasoning enabled, each
# one thinks before answering). Like the ones above, they only apply to a fresh
# install: with existing data, change them in Admin Panel > Settings > Interface.
export ENABLE_TAGS_GENERATION="false"
export ENABLE_AUTOCOMPLETE_GENERATION="false"
export ENABLE_FOLLOW_UP_GENERATION="false"

exec uvx --python 3.11 open-webui@latest serve --port 3000
