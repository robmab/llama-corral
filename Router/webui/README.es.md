[English](README.md) | **Español**

# Router y Open WebUI

Cómo funciona el router de llama.cpp y cómo usarlo desde VS Code y Open WebUI.
Para la instalación inicial (ficheros de ejemplo, builds y modelos), ver el
[README principal](../../README.es.md).

## Cómo funciona el router

`Router/router.sh` arranca `llama-server` sin modelo propio y con
`--models-preset Router/models.ini`, lo que lo convierte en un router en `:10001`:

1. Un cliente (Copilot, Open WebUI) envía una petición con `"model": "<id>"`.
2. El router busca la sección `[<id>]` en `models.ini`.
3. Si ese perfil no está cargado, descarga el actual (`--models-max 1`) y arranca
   un `llama-server` hijo con los flags de esa sección en un puerto interno.
4. Le reenvía la petición a ese hijo.

Consecuencias:

- El `id` del modelo en el cliente y el nombre de la sección tienen que ser **idénticos**.
- Cada modelo es un proceso aparte: para apagarlo todo hay que parar todos los
  `llama-server`, no solo el que escucha en `:10001` (`llama stop` lo hace).
- Cambiar de modelo tarda lo que tarde en cargar el nuevo (segundos).
- Cada cambio es una carga nueva en VRAM. Tras muchos cambios, Windows puede
  degradar la VRAM: si todo va lento, `llama vram` lo confirma y se arregla reiniciando.
- `router.sh` lee la build activa de `llm.conf` (`SERVER_BUILD`). Una variable de
  entorno `SERVER_BUILD` tiene prioridad, para probar una build una vez.

## VS Code (Copilot)

Copilot no puede arrancar procesos, así que primero se arranca el router y después
se elige el modelo en Copilot:

```bash
llama start                      # router + DEFAULT_MODEL precargado
llama start <id-modelo>          # o precarga otro perfil
llama status                     # qué modelo está cargado
llama stop                       # apaga todo
```

## Open WebUI

Doble clic en `Router\LocalLLM-Launcher.exe`. El lanzador:

1. Reutiliza el router si `llama start` ya está en marcha. Si hay otro
   llama-server que no es el router, lo para y arranca el router con la ventana oculta.
2. Arranca Open WebUI en segundo plano (`start-open-webui.sh`, con `uvx`, sin
   Docker) y muestra su progreso hasta que responde en `:3000`.
3. Abre una ventana de navegador dedicada (`--app` con un perfil propio de
   Chromium/Edge/Brave), sin pestañas ni barra de direcciones.
4. Oculta su consola y espera a que se cierre esa ventana.
5. Al cerrarla apaga Open WebUI y, solo si lo arrancó él, el router.

VS Code y Open WebUI pueden usarse a la vez. Si piden modelos distintos al mismo
tiempo, el router irá cambiando de uno a otro en cada petición.

### Ajustes recomendados de Open WebUI (una vez, en Admin Panel)

- **Ocultar los perfiles solo de código** (Ajustes > Modelos), para que en el
  selector solo salgan los de uso general.
- **Modelo de tareas = modelo actual** (Ajustes > Interfaz). Si apunta a otro
  modelo, cada título de chat provoca un cambio de modelo.
- **Desactivar las tareas secundarias** (misma pantalla): sugerencias de
  seguimiento, etiquetas y autocompletado. Con el razonamiento activo, cada una
  piensa antes de responder y gasta GPU en cada mensaje.

### start-open-webui.sh

| Variable | Valor |
|---|---|
| `DATA_DIR` | `C:/open-webui/data` (usuarios, chats y ajustes) |
| `OPENAI_API_BASE_URL` | `http://localhost:10001/v1` |
| `OPENAI_API_KEY` | `apikey` |
| `ENABLE_WEB_SEARCH` / `WEB_SEARCH_ENGINE` | `true` / `duckduckgo` |
| `ENABLE_TAGS / AUTOCOMPLETE / FOLLOW_UP_GENERATION` | `false` |

Casi todas solo cuentan en una instalación nueva: se guardan en la base de datos
al crearla y, a partir de ahí, mandan los ajustes del Admin Panel.

## Ficheros

```
../router.sh                    llama-server en modo router (:10001)
../models.ini                   una sección por modelo con sus parámetros   [local]
../models.ini.example           plantilla
../LocalLLM-Launcher.exe        lanzador de Open WebUI (doble clic)         [compilado]
LocalLLM-Launcher.ps1           fuente del lanzador
start-open-webui.sh             arranca Open WebUI (uvx, sin Docker) contra :10001
logs/router.log                 salida del router arrancado con "llama start"
logs/launcher-llama.log         salida del router arrancado por el lanzador
logs/launcher-webui.log         salida de Open WebUI
```

## Cambiar los parámetros de un modelo

Edita su sección en `models.ini` (las claves son flags de llama-server sin los
guiones) y reinicia el router (`llama stop` + `llama start`). No hace falta
recompilar el `.exe`.

## Compilar el .exe

El `.exe` no se sube al repositorio. Descárgalo de las [releases](https://github.com/robmab/llama-corral/releases)
y ponlo en `Router/`, o compílalo tú (de nuevo si cambias el `.ps1`):

```powershell
cd D:\LLM\Router
Import-Module ps2exe      # la primera vez: Install-Module ps2exe -Scope CurrentUser
Invoke-ps2exe .\webui\LocalLLM-Launcher.ps1 .\LocalLLM-Launcher.exe -title "Local LLM"
```

El lanzador calcula la carpeta `Router` a partir de su propia ubicación, así que no
depende de dónde se clone el repositorio.

## Problemas frecuentes

| Síntoma | Causa | Solución |
|---|---|---|
| Open WebUI "arranca" al instante pero habla con otro modelo | Seguía abierto otro Open WebUI en `:3000` | Cerrar antes su ventana; usar un solo lanzador a la vez |
| Las variables de entorno no tienen efecto | Solo se leen al crear la base de datos | Cambiarlas en Admin Panel > Ajustes |
| Aparece un fichero `.webui_secret_key` en `Router/` | Open WebUI guarda su clave de sesión en la carpeta desde la que arranca | Es normal; si se borra, hay que volver a iniciar sesión |
| Respuestas lentas en cada mensaje | Tareas secundarias (títulos, etiquetas, seguimiento) usando otro modelo o razonando | Ajustes recomendados de arriba |
| El lanzador espera y se rinde con llama-server | Falta un fichero local, la build es incorrecta o un modelo da error | Revisar `logs/launcher-llama.log` |
