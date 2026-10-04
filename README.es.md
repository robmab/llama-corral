[English](README.md) | **Español**

# Local LLM

Modelos de lenguaje locales en un PC con Windows, servidos por un único servidor
de [llama.cpp](https://github.com/ggml-org/llama.cpp) en **modo router**: un
servidor en `localhost:10001` con un perfil por modelo. Cada petición lleva el id
de un modelo y el router carga ese perfil, descargando el anterior. VS Code
Copilot (agente de código) y Open WebUI (chat con visión y búsqueda web) cambian
de modelo solos al elegir uno en su selector.

Este README explica la instalación paso a paso.

## Contenido

1. [Requisitos](#1-requisitos)
2. [Obtener el repositorio](#2-obtener-el-repositorio)
3. [Configurar los ficheros de ejemplo](#3-configurar-los-ficheros-de-ejemplo)
4. [Instalar el comando `llama`](#4-instalar-el-comando-llama)
5. [Añadir una build de llama.cpp (Servers)](#5-añadir-una-build-de-llamacpp-servers)
6. [Añadir modelos (Models + models.ini)](#6-añadir-modelos-models--modelsini)
7. [Arrancar y comprobar](#7-arrancar-y-comprobar)
8. [Conectar los clientes](#8-conectar-los-clientes)
9. [Uso diario](#9-uso-diario)
10. [Problemas frecuentes](#10-problemas-frecuentes)

## Estructura

```
Models/          una carpeta por modelo: .gguf (+ mmproj para visión)   [no se sube]
Servers/         builds de llama.cpp, una carpeta cada una              [no se sube]
Router/
  router.sh            arranca llama-server en modo router
  models.ini           perfiles de los modelos                           [local]
  models.ini.example   plantilla
  webui/               lanzador de Open WebUI (ver Router/webui/README.es.md)
Tests/           pruebas de velocidad, visión, contexto, muestreo, razonamiento y agente
llm.conf         configuración general (build de llama.cpp activa)      [local]
aliases.sh       alias de Git Bash: el comando "llama"                  [local]
*.example        plantillas de los ficheros locales
```

Los ficheros *locales* guardan tu configuración y git los ignora. Se crean una
sola vez a partir de su plantilla `*.example`.

## 1. Requisitos

- Windows 10/11 con [Git for Windows](https://git-scm.com/download/win). Todos
  los scripts se ejecutan en **Git Bash**.
- Una GPU compatible con alguna build de llama.cpp (Vulkan funciona en AMD,
  NVIDIA e Intel).
- Python 3 para las pruebas (solo la librería estándar).
- Opcional: [uv](https://docs.astral.sh/uv/) para Open WebUI
  (`winget install astral-sh.uv`) y el módulo PS2EXE de PowerShell para compilar el
  lanzador de Open WebUI (`Install-Module ps2exe -Scope CurrentUser`).

## 2. Obtener el repositorio

```bash
git clone <url-del-repo> /d/LLM
cd /d/LLM
```

Sirve cualquier ubicación. Los ejemplos suponen `D:\LLM` (`/d/LLM` en Git Bash).

## 3. Configurar los ficheros de ejemplo

Crea los tres ficheros locales a partir de sus plantillas:

```bash
cp llm.conf.example llm.conf
cp aliases.sh.example aliases.sh
cp Router/models.ini.example Router/models.ini
```

| Fichero | Qué ajustar | Ejemplo |
|---|---|---|
| `llm.conf` | `SERVER_BUILD`: nombre de la carpeta de llama.cpp dentro de `Servers/` (paso 5) | `SERVER_BUILD="llama-b11146-bin-win-vulkan-x64"` |
| `aliases.sh` | `LLM`: ruta del repositorio en formato Git Bash | `LLM="/d/LLM"` |
|  | `DEFAULT_MODEL`: perfil que precarga `llama start` (una sección de `models.ini`) | `DEFAULT_MODEL="My-Coder-Model"` |
| `Router/models.ini` | una sección por modelo (paso 6) | ver `models.ini.example` |

`llm.conf` y `models.ini` pueden esperar a los pasos 5 y 6.

## 4. Instalar el comando `llama`

Git Bash carga al arrancar todos los scripts de
`C:\Program Files\Git\etc\profile.d\`. Haz que su `aliases.sh` cargue el del
repositorio (edítalo como administrador, o créalo si no existe):

```bash
# C:\Program Files\Git\etc\profile.d\aliases.sh
[ -f /d/LLM/aliases.sh ] && . /d/LLM/aliases.sh
```

Abre una terminal **nueva** de Git Bash y ejecuta `llama`: muestra los comandos disponibles.

## 5. Añadir una build de llama.cpp (Servers)

1. Descarga una build para Windows de las
   [releases de llama.cpp](https://github.com/ggml-org/llama.cpp/releases), por
   ejemplo `llama-bXXXXX-bin-win-vulkan-x64.zip`. El modo router
   (`--models-preset`) necesita una build reciente.
2. Descomprímela en su propia carpeta dentro de `Servers/`, con su nombre original:

   ```
   Servers/
     llama-b11146-bin-win-vulkan-x64/
       llama-server.exe
       ggml-*.dll ...
   ```

3. Déjala como build activa. Pon `SERVER_BUILD` en `llm.conf`, o ejecuta:

   ```bash
   llama server                                    # lista las builds; * marca la activa
   llama server llama-b11146-bin-win-vulkan-x64    # la cambia (comprueba que existe llama-server.exe)
   ```

4. Comprueba que ve tu GPU y apunta el nombre del dispositivo (lo habitual es `Vulkan0`):

   ```bash
   /d/LLM/Servers/llama-b11146-bin-win-vulkan-x64/llama-server.exe --list-devices
   ```

Pueden convivir varias builds. Para probar una nueva sin cambiar la activa:
`SERVER_BUILD=<carpeta> llama start`.

## 6. Añadir modelos (Models + models.ini)

1. **Copia los ficheros en `Models/`**, una carpeta por modelo, con el `.gguf` y,
   en los modelos con visión, su proyector (`mmproj-*.gguf`) al lado:

   ```
   Models/
     Qwen3.6-35B-A3B-UD-IQ4_XS/
       Qwen3.6-35B-A3B-UD-IQ4_XS.gguf
       mmproj-F16.gguf
   ```

   Los modelos partidos (`-00001-of-0000N.gguf`) van en la misma carpeta; se indica la primera parte.

2. **Añade un perfil a `Router/models.ini`**: una sección cuyo nombre es el id del
   modelo y cuyas claves son flags de llama-server sin los guiones.

   ```ini
   [My-Coder-Model]
   model = D:/LLM/Models/Qwen3.6-35B-A3B-UD-IQ4_XS/Qwen3.6-35B-A3B-UD-IQ4_XS.gguf
   n-cpu-moe = 22
   ctx-size = 131072
   temp = 0.6
   ```

   - Rutas absolutas con barras normales, y los comentarios en su propia línea (`;`).
   - Lo común va en `[*]`; una clave en la sección del modelo lo sobrescribe.
   - Visión: añade `mmproj = <ruta>`. Sin visión: `no-mmproj = true`.
   - Muestreo: usa los valores de la ficha del modelo (cambian entre código y uso general).
   - `n-cpu-moe` (solo modelos MoE) deja en RAM los expertos de las primeras N
     capas cuando el modelo no cabe en VRAM. En el paso 7 se explica cómo ajustarlo.
   - MTP (`spec-type = draft-mtp`) solo funciona con modelos que traen cabeza MTP
     (repos que acaban en `-MTP-GGUF`).

   Un mismo `.gguf` puede tener varios perfiles (por ejemplo, código sin visión y
   uso general con visión): son secciones distintas que apuntan al mismo fichero.

## 7. Arrancar y comprobar

```bash
llama start My-Coder-Model     # arranca el router y carga ese perfil
llama status                   # build activa, perfiles y cuál está cargado (*)
llama vram                     # "OK" = el modelo cabe entero en VRAM
llama test speed --model My-Coder-Model
llama stop
```

**Lista de comprobación para un modelo nuevo**

1. `llama start <id>` carga sin errores (log: `Router/webui/logs/router.log`).
2. `llama vram` dice OK. Si avisa, parte del modelo está en memoria compartida:
   sube `n-cpu-moe`, baja `ctx-size` o usa caché KV q4_0.
3. `llama test speed` da cifras razonables a 2k / 32k / 64k.
4. Con visión: `llama test vision --model <id>`.
5. En modelos MoE, busca el `n-cpu-moe` **más bajo** que siga diciendo OK tras la
   prueba de velocidad: con menos se desborda y va más lento. Procedimiento en
   [Tests/README.md](Tests/README.md).
6. Opcional: compara la calidad con `llama test reasoning` y `llama test agentic`.

## 8. Conectar los clientes

### VS Code Copilot

Añade los perfiles como modelos personalizados en
`%APPDATA%\Code\User\chatLanguageModels.json`. El `id` tiene que coincidir
**exactamente** con una sección de `models.ini`: Copilot lo envía en cada petición
y el router lo usa para elegir el perfil. Cuando VS Code pida la clave de API, usa
`apikey` (el `--api-key` de `router.sh`).

```json
[
  {
    "name": "Local",
    "vendor": "customendpoint",
    "apiType": "chat-completions",
    "models": [
      {
        "id": "My-Coder-Model",
        "name": "Mi modelo de código",
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

- `maxInputTokens + maxOutputTokens` no debe superar el `ctx-size` del perfil.
- `"vision": true` solo en perfiles que cargan un `mmproj`.
- Copilot no puede arrancar procesos: ejecuta `llama start` antes de usarlo.

### Open WebUI

Compila el lanzador una vez y después ábrelo con doble clic:

```powershell
cd D:\LLM\Router
Import-Module ps2exe
Invoke-ps2exe .\webui\LocalLLM-Launcher.ps1 .\LocalLLM-Launcher.exe -title "Local LLM"
```

`Router\LocalLLM-Launcher.exe` arranca Open WebUI con `uvx` (sin Docker) en
`http://localhost:3000`, lo abre en una ventana de navegador dedicada y lo apaga
al cerrarla. Si `llama start` ya está en marcha, reutiliza ese router, así que VS
Code y Open WebUI pueden funcionar a la vez. Ajustes recomendados y detalles:
[Router/webui/README.es.md](Router/webui/README.es.md).

## 9. Uso diario

```bash
llama start [id-modelo]      # router en segundo plano (+ DEFAULT_MODEL precargado)
llama status                 # qué está cargado
llama stop                   # apaga todo
llama server [carpeta]       # lista / cambia la build de llama.cpp
llama vram                   # salud de la VRAM
llama test <prueba>          # speed | vision | benchmark | context | sampling | reasoning | agentic
```

Para cambiar los parámetros de un modelo: edita su sección en
`Router/models.ini` y luego `llama stop` + `llama start`.

## 10. Problemas frecuentes

| Síntoma | Causa | Solución |
|---|---|---|
| `Missing .../llm.conf` o `.../models.ini` | Falta el fichero local | Crearlo con `cp` desde su `.example` (paso 3) |
| `Build not found: .../Servers/...` | `SERVER_BUILD` no coincide con ninguna carpeta | `llama server` para ver las builds y elegir una |
| `llama: command not found` | Los alias no se cargan | Paso 4, y abrir una terminal nueva de Git Bash |
| El cliente dice que el modelo no existe | Su `id` no coincide con el nombre de la sección | Hacerlos idénticos (mayúsculas incluidas) |
| Todo va 2-3 veces más lento de lo normal | Windows degradó la VRAM tras muchos arranques, o el modelo se desborda | `llama vram`; si avisa, reiniciar o subir `n-cpu-moe` |
| Copilot: error 500 "image input is not supported" | `"vision": true` en un perfil sin `mmproj` | Poner `"vision": false`, recargar VS Code y abrir un chat nuevo |
| Copilot: "Cannot have more than 128 tools" | Límite de Copilot, no del servidor | Desactivar herramientas o servidores MCP en el selector de herramientas de Copilot |
| Las respuestas salen vacías | El razonamiento agotó los tokens de salida | Subir el máximo de salida del cliente o poner `reasoning-budget` |

## Notas

- Lecciones del ajuste en una Radeon RX 9070 XT (16 GB): Windows puede degradar la
  VRAM tras muchos arranques (se arregla reiniciando); un MoE en Q4 con algunas
  capas de expertos en RAM supera a un denso en Q3; desbordar la VRAM es más lento
  que mandar capas a RAM a propósito; MTP aporta un 15-50% cuando cabe; el
  razonamiento largo es el principal coste de un agente local; las pruebas
  sintéticas se saturan y lo que distingue a los modelos es una tarea real.
- Más detalle: [Router/webui/README.es.md](Router/webui/README.es.md) (router y
  Open WebUI) y [Tests/README.md](Tests/README.md) (pruebas y ajuste).
