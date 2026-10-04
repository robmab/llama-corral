[English](README.md) | **Español**

# Pruebas

Todas se conectan al router (`llama start`) y aceptan `--model` con el id de una
sección de `Router/models.ini`. Solo usan la librería estándar de Python.

Se lanzan con `llama test <prueba> [opciones]` o directamente con `python` desde
esta carpeta. Las que guardan transcripción la dejan en `Tests/logs/`.

| `llama test` | Script               | Qué mide                                                          | Cuándo usarla                                   |
|--------------|----------------------|-------------------------------------------------------------------|-------------------------------------------------|
| `speed`      | `speed.py`           | lectura del prompt, generación y MTP a 2k / 32k / 64k             | tras cambiar parámetros o si algo va lento      |
| `vision`     | `vision.py`          | que la visión funciona y cuánto tarda una imagen de 1024 px       | tras cambiar `n-cpu-moe` o el mmproj            |
| `benchmark`  | `quick-benchmark.py` | velocidad + aciertos en unas pocas preguntas, en un minuto        | comprobación rápida antes y después de un cambio |
| `context`    | `context-sweep.py`   | contexto práctico máximo: agranda el prompt hasta que cae la velocidad | al cambiar `ctx-size` o el tipo de KV       |
| `sampling`   | `sampling-quality.py`| % de código Python que pasa tests según temp / top-p / top-k      | para elegir el muestreo de un modelo            |
| `reasoning`  | `reasoning-test.py`  | 5 tareas de código con tests ocultos y detección de bucles        | calidad de razonamiento de un modelo nuevo      |
| `agentic`    | `agentic-test.py`    | 4 mini-proyectos con herramientas y tests ocultos                 | calidad como agente de un modelo nuevo          |

Ejemplos:

```bash
llama test speed --model <id-modelo>
llama test vision --model <id-modelo-con-vision>
llama test benchmark --label antes-del-cambio
llama test context --max 131072 --step 16384
llama test sampling --repeats 2
llama test reasoning --runs 1 --tag mio
llama test agentic --runs 1 --tag mio
llama test agentic --selftest          # valida las tareas, sin servidor
```

Notas:
- `reasoning` tiene prompts en inglés (por defecto) y en español (`--lang es`).
  Los modelos que mezclan español en los identificadores (nombres de función que
  no coinciden con los tests) fallan la versión en español aunque razonen bien.
- `reasoning` y `agentic` dejan `results-*-<tag>.json` en esta carpeta, y
  `agentic` copia los proyectos fallidos en `agentic-failures-<tag>/`.
- `agentic` tiende a saturarse (varios modelos sacaron 8/8); lo que de verdad
  distinguió a los modelos fue una tarea real en el IDE.
- `common.py` contiene utilidades compartidas por `context`, `sampling` y `benchmark`.
- Los límites de tokens son holgados porque el razonamiento cuenta como salida:
  con límites justos, un modelo que razona puede agotarlos antes de responder
  (respuesta vacía = FALLO).

## Ajustar las capas de expertos en RAM (n-cpu-moe)

1. Reinicia (la VRAM degradada falsea las medidas) y deja abiertas solo las aplicaciones habituales.
2. Cambia el `n-cpu-moe` del modelo en `Router/models.ini`.
3. `llama stop` y `llama start <id-modelo>`.
4. `llama test vision --model <id-modelo>` (si tiene visión) y `llama vram`.
5. `llama test speed --model <id-modelo>` y otra vez `llama vram`.

Buscas el valor **más bajo** con el que `llama vram` sigue diciendo OK (memoria
compartida por debajo de ~1,2 GB) tras la prueba de 64k. Por debajo de ese valor
el modelo se desborda a memoria compartida y va más lento, no más rápido. Deja
una capa de margen si vas a tener el navegador abierto.

Medido en una RX 9070 XT de 16 GB (oct. 2026): Qwen3.6-35B-A3B IQ4_XS, perfil de
código 22 (con MTP); el mismo modelo con visión, 23 (con 22 va al límite).
