#!/bin/bash

# llama-server in router mode: a single server on :10001 that offers the models in
# models.ini and loads the one each request asks for ("model" field). With
# --models-max 1 it unloads the current model before loading the new one, so two
# models are never in VRAM at the same time.
#
# Models: one per section of models.ini (the section name is the model id).
#
# Usage:
#   bash router.sh                           # no model loaded until the first request
#   PRELOAD=<model-id> bash router.sh        # loads that model right after starting
#
# Switching models takes as long as loading the new one (seconds).
# Note: every switch is a new load into VRAM. After many switches Windows can
# degrade the VRAM (see "llama vram"); if everything gets slow, reboot.

PRELOAD="${PRELOAD:-}"

# Repo layout: Models/ (gguf), Router/ (this), Servers/ (llama.cpp builds), Tests/.
# The active build is set in llm.conf (SERVER_BUILD) at the repo root; a
# SERVER_BUILD environment variable takes precedence, to try another build
# without switching.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_BUILD="${SERVER_BUILD:-}"
CONF="$SCRIPT_DIR/../llm.conf"
if [ -f "$CONF" ]; then
    # shellcheck source=/dev/null
    . "$CONF"
elif [ -z "$ENV_BUILD" ]; then
    echo "Missing $CONF. Create it from the example:  cp llm.conf.example llm.conf  (and set SERVER_BUILD)"
    exit 1
fi
SERVER_BUILD="${ENV_BUILD:-$SERVER_BUILD}"
[ -n "$SERVER_BUILD" ] || { echo "SERVER_BUILD is not set in $CONF"; exit 1; }

PRESETS="$SCRIPT_DIR/models.ini"
[ -f "$PRESETS" ] || { echo "Missing $PRESETS. Create it from the example:  cp models.ini.example models.ini  (and set your models)"; exit 1; }

SERVER_DIR="$(cd "$SCRIPT_DIR/../Servers/$SERVER_BUILD" && pwd)" || { echo "Build not found: $SCRIPT_DIR/../Servers/$SERVER_BUILD"; exit 1; }
cd "$SERVER_DIR" || exit 1
echo "Router: $SERVER_DIR  ->  presets $PRESETS"

./llama-server.exe \
    --models-preset "$PRESETS" \
    --models-max 1 \
    --host 0.0.0.0 \
    --port 10001 \
    --api-key apikey &
SERVER_PID=$!

if [ -n "$PRELOAD" ]; then
    for _ in $(seq 1 60); do
        curl -s -o /dev/null --max-time 2 http://localhost:10001/health && break
        sleep 1
    done
    echo "Preloading $PRELOAD..."
    curl -s -H "Authorization: Bearer apikey" -H "Content-Type: application/json" \
        -d "{\"model\":\"$PRELOAD\"}" http://localhost:10001/models/load > /dev/null
fi

wait $SERVER_PID
