#!/usr/bin/env bash
# Lanza Open WebUI (sin Docker) apuntando al router de llama-server (Qwen 3.6 y Ornith 9B).
# Requisitos: uv instalado (winget install astral-sh.uv) y llama-server en marcha.
# Abre despues http://localhost:3000

LLAMA_PORT=10001
LLAMA_API_KEY="apikey"   # la misma que --api-key en router.sh

# Datos compartidos con los demas lanzadores: mismos usuarios, chats y ajustes.
export DATA_DIR="C:/open-webui/data"

# Conexion al modelo. Solo se leen la PRIMERA vez: despues manda lo guardado
# en Admin Panel > Ajustes > Conexiones.
export ENABLE_OLLAMA_API="false"
export OPENAI_API_BASE_URL="http://localhost:${LLAMA_PORT}/v1"
export OPENAI_API_KEY="${LLAMA_API_KEY}"

# Busqueda web con DuckDuckGo.
export ENABLE_WEB_SEARCH="true"
export WEB_SEARCH_ENGINE="duckduckgo"

# Tareas secundarias que gastan GPU en cada mensaje (con razonamiento activo, cada
# una piensa antes de responder). Igual que las de arriba, solo cuentan en una
# instalacion nueva: con datos ya creados se cambian en Admin Panel > Ajustes > Interfaz.
export ENABLE_TAGS_GENERATION="false"
export ENABLE_AUTOCOMPLETE_GENERATION="false"
export ENABLE_FOLLOW_UP_GENERATION="false"

exec uvx --python 3.11 open-webui@latest serve --port 3000
