# Pruebas

Todas se conectan al router (`llama start`) y aceptan `--model` con el id de una
seccion de `Router/modelos.ini`: `Qwen3.6-35B-A3B` (por defecto),
`Qwen3.6-35B-A3B-General` u `Ornith-1.5-9B`. Solo usan la libreria estandar de Python.

Se lanzan con `llama test <prueba> [opciones]` o directamente con `python` desde
esta carpeta. Las que guardan transcripcion la dejan en `tests/logs/`.

| `llama test`   | Script                 | Que mide                                                      | Cuando usarlo                                  |
|----------------|------------------------|---------------------------------------------------------------|------------------------------------------------|
| `velocidad`    | `velocidad.py`         | lectura de prompt, generacion y MTP a 2k / 32k / 64k          | tras cambiar parametros o si algo va lento     |
| `vision`       | `vision.py`            | que la vision funciona y cuanto tarda una imagen 1024 px      | tras cambiar `n-cpu-moe` o el mmproj           |
| `benchmark`    | `benchmark-rapido.py`  | velocidad + aciertos en unas pocas preguntas, en un minuto    | comprobacion rapida antes y despues de un cambio |
| `contexto`     | `contexto.py`          | contexto practico maximo: sube el prompt hasta que la velocidad cae | al cambiar `ctx-size` o el tipo de KV     |
| `muestreo`     | `muestreo.py`          | % de codigo Python que pasa tests segun temp / top-p / top-k  | para decidir el muestreo de un modelo          |
| `razonamiento` | `razonamiento-test.py` | 5 tareas de codigo con tests ocultos, deteccion de bucles     | calidad de razonamiento de un modelo nuevo     |
| `agentico`     | `agentico-test.py`     | 4 mini-proyectos con herramientas y tests ocultos             | calidad como agente de un modelo nuevo         |

Ejemplos:

```bash
llama test velocidad --model Ornith-1.5-9B
llama test vision --model Qwen3.6-35B-A3B-General
llama test benchmark --label antes-del-cambio
llama test contexto --max 131072 --step 16384
llama test muestreo --repeats 2
llama test razonamiento --lang en --runs 1 --tag qwen36
llama test agentico --runs 1 --tag qwen36
llama test agentico --selftest          # valida las tareas, sin servidor
```

Notas:
- `razonamiento` en espanol penaliza a los modelos que mezclan espanol en el codigo
  (nombres de funcion que no coinciden con los tests); `--lang en` mide el
  razonamiento sin ese efecto.
- `razonamiento` y `agentico` dejan `resultados-*-<tag>.json` en esta carpeta, y
  `agentico` copia los proyectos fallidos en `agentico-fallos-<tag>/`.
- En la sesion de pruebas, `agentico` saturo (varios modelos sacaron 8/8); lo que
  de verdad separo a los modelos fue una tarea real en Copilot.
- `common.py` son utilidades compartidas por `contexto`, `muestreo` y `benchmark`.

Origen: `contexto`, `muestreo`, `benchmark-rapido` y `common` vienen del repo
`Ornith-1.5-35B-A3B-MTP-IQ3_S` (01_context_sweep, 03_sampling_quality,
benchmark_quick), adaptados para pedir el modelo por id al router. Las pruebas que
arrancaban su propio servidor (02 parametros MTP, 04 fragmentacion de KV, 05 hilos
y load-mode) no estan aqui: chocan con el router y sus conclusiones ya estan
aplicadas (MTP n-max 2 / p-min 0.05, sin mlock).

## Ajustar las capas de expertos en RAM (n-cpu-moe)

1. Reinicia el PC (la VRAM degradada falsea las medidas) y deja abierto solo lo habitual.
2. Cambia `n-cpu-moe` del modelo en `Router/modelos.ini`.
3. `llama stop` y `llama start <modelo>`.
4. `llama test vision --model <modelo>` (si tiene vision) y `llama vram`.
5. `llama test velocidad --model <modelo>` y otra vez `llama vram`.

Buscas el numero mas bajo con el que `llama vram` sigue diciendo OK (compartida
por debajo de ~1.2 GB) tras la prueba de 64k. Por debajo de ese numero el modelo
se desborda a memoria compartida y va mas lento, no mas rapido. Deja una capa de
margen si vas a tener el navegador abierto.

Valores medidos el 4 oct 2026: Qwen codigo 22 (con MTP), Qwen general con
vision 23 (22 va al limite).
