#!/bin/bash

# llama-server en modo router: un solo servidor en :10001 que ofrece los modelos de
# modelos.ini y carga el que pida cada peticion (campo "model"). Con --models-max 1
# descarga el anterior antes de cargar el nuevo: nunca hay dos modelos en VRAM.
#
# Modelos (id = nombre de la seccion en modelos.ini):
#   Qwen3.6-35B-A3B           codigo (VS Code Copilot); lo precarga "llama start"
#   Qwen3.6-35B-A3B-General   uso general con vision
#   Ornith-1.5-9B             uso general con vision, mas rapido
#
# Uso:
#   bash router.sh                       # ningun modelo cargado hasta la primera peticion
#   PRELOAD=Ornith-1.5-9B bash router.sh # carga ese modelo nada mas arrancar
#
# Cambiar de modelo tarda lo que tarda su carga (9B: ~5 s; Qwen 3.6: ~8-10 s).
# Ojo: cada cambio es una carga nueva en VRAM. Tras muchos cambios, Windows puede
# degradar la VRAM (ver "llama vram"); si todo va lento, reinicia el PC.

PRELOAD="${PRELOAD:-}"

# Estructura de D:/LLM: Models/ (gguf), Router/ (esto), Servers/ (builds de llama.cpp),
# Tests/. La build activa se define en D:/LLM/llm.conf (SERVER_BUILD); una variable
# de entorno SERVER_BUILD tiene prioridad, para probar otra build sin cambiarla.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_BUILD="${SERVER_BUILD:-}"
CONF="$SCRIPT_DIR/../llm.conf"
if [ -f "$CONF" ]; then
    . "$CONF"
elif [ -z "$ENV_BUILD" ]; then
    echo "Falta $CONF. Crealo a partir del ejemplo:  cp llm.conf.example llm.conf  (y pon tu build en SERVER_BUILD)"
    exit 1
fi
SERVER_BUILD="${ENV_BUILD:-$SERVER_BUILD}"
[ -n "$SERVER_BUILD" ] || { echo "Falta SERVER_BUILD en $CONF"; exit 1; }

SERVER_DIR="$(cd "$SCRIPT_DIR/../Servers/$SERVER_BUILD" && pwd)" || { echo "No encuentro la build: $SCRIPT_DIR/../Servers/$SERVER_BUILD"; exit 1; }
cd "$SERVER_DIR"
echo "Router: $SERVER_DIR  ->  presets $SCRIPT_DIR/modelos.ini"

./llama-server.exe \
    --models-preset "$SCRIPT_DIR/modelos.ini" \
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
    echo "Precargando $PRELOAD..."
    curl -s -H "Authorization: Bearer apikey" -H "Content-Type: application/json" \
        -d "{\"model\":\"$PRELOAD\"}" http://localhost:10001/models/load > /dev/null
fi

wait $SERVER_PID
