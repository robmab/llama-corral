# IA Local: router de llama-server para VS Code y Open WebUI

Un solo servidor en `:10001` con tres perfiles. Cada peticion lleva el nombre del
modelo y el router carga el que toque, descargando el anterior (nunca hay dos en
VRAM). Copilot y Open WebUI cambian de modelo solos al elegirlo en su selector.

| Modelo (id)                | Para que                        | Configuracion                                                      |
|----------------------------|---------------------------------|--------------------------------------------------------------------|
| `Qwen3.6-35B-A3B`          | codigo, agente (VS Code)        | IQ4_XS, MTP, sin vision, 22 capas en RAM, temp 0.6, ~45 t/s         |
| `Qwen3.6-35B-A3B-General`  | uso general, imagenes, calidad  | IQ4_XS, vision F16, MTP, 23 capas en RAM, temp 1.0, ~43 t/s         |
| `Ornith-1.5-9B`            | uso general, imagenes, rapidez  | Q8_0, vision, MTP, KV q4_0, temp 1.0, 70-85 t/s                     |

Todos con 131k de contexto. Cambiar de modelo tarda ~5 s (9B) u 8-15 s (Qwen).

## Como se usa

**VS Code (Copilot):** arranca el router desde Git Bash y elige el modelo en Copilot.

```bash
llama start                      # router + Qwen de codigo precargado (~20 s)
llama start Ornith-1.5-9B        # o precarga otro
llama status                     # que modelo esta cargado
llama stop                       # apaga todo
```

**Open WebUI:** doble clic en `IALocal-Launcher.exe`.
- Si ya hiciste `llama start`, reutiliza ese router y al cerrar la ventana solo
  apaga Open WebUI (VS Code sigue funcionando).
- Si no hay router, lo arranca el y lo apaga al cerrar.
- Si hay otro llama-server que no es el router, lo para y arranca el router.

Se pueden usar los dos a la vez. Si piden modelos distintos al mismo tiempo, el
router ira cambiando de uno a otro en cada peticion (cada cambio cuesta segundos).

## Ficheros

Estructura de `D:\LLM`:

```
Models\     un .gguf (y su mmproj) por modelo, sin scripts
Router\     esto: router.sh, modelos.ini, lanzador de Open WebUI
Servers\    builds de llama.cpp (la activa: SERVER_BUILD en D:\LLM\llm.conf, o 'llama server')
llm.conf    configuracion general de D:\LLM (build activa)
Tests\      pruebas (llama test)
```

Dentro de `Router\llm-search\`:

```
../router.sh                    llama-server en modo router (:10001)
../modelos.ini                  un bloque por modelo con sus parametros
../IALocal-Launcher.exe         lanzador de Open WebUI (doble clic)
IALocal-Launcher.ps1            fuente del lanzador
start-open-webui.sh             arranca Open WebUI (uvx, sin Docker) contra :10001
logs/router.log                 salida del router arrancado con "llama start"
logs/launcher-llama.log         salida del router arrancado por el lanzador
logs/launcher-webui.log         salida de Open WebUI
```

## Ajustes recomendados en Open WebUI (una vez)

- **Ocultar el perfil de codigo:** Admin Panel > Ajustes > Modelos, desactivar
  `Qwen3.6-35B-A3B`. Asi en el selector solo salen los de uso general.
- **Modelo de tareas** (titulos, etc.) = modelo actual (Admin Panel > Ajustes >
  Interfaz). Si apunta a otro modelo, cada titulo provocaria un cambio de modelo.
- **Desactivar tareas secundarias** que gastan GPU en cada mensaje (misma
  pantalla): sugerencias de seguimiento, etiquetas y autocompletado.

## Cambiar parametros de un modelo

Edita su seccion en `modelos.ini` (las claves son los flags de llama-server sin
guiones) y reinicia el router (`llama stop` + `llama start`). No hace falta
recompilar el `.exe`.

## Compilar el .exe

Solo hace falta si cambias el `.ps1`:

```powershell
cd D:\LLM\Router
Import-Module ps2exe
Invoke-ps2exe .\llm-search\IALocal-Launcher.ps1 .\IALocal-Launcher.exe -title "IA Local"
```

## A tener en cuenta

- Cada cambio de modelo es una carga nueva en VRAM. Tras muchos cambios, Windows
  puede degradar la VRAM: si todo va lento, `llama vram` lo confirma y se arregla
  reiniciando el PC.
- Los modelos solo se usan a traves del router: sus carpetas contienen unicamente
  el `.gguf` y el `mmproj`. Toda la configuracion esta en `modelos.ini`.
- Pruebas para comprobar o ajustar un modelo: `llama test` (ver `D:\LLM\Tests\README.md`).
