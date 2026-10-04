[English](README.md) | **Español**

# llama-corral

[![CI](https://github.com/robmab/llama-corral/actions/workflows/ci.yml/badge.svg)](https://github.com/robmab/llama-corral/actions/workflows/ci.yml)

**Un corral para tus LLM locales.** Ten varios modelos preparados y saca el que
necesites: un único servidor de [llama.cpp](https://github.com/ggml-org/llama.cpp)
en **modo router** en `localhost:10001`, con un perfil por modelo. Cada petición
lleva el id de un modelo y el router carga ese perfil, descargando el anterior,
así que solo hay un modelo en VRAM a la vez. VS Code Copilot (agente de código) y
Open WebUI (chat con visión y búsqueda web) cambian de modelo solos al elegir uno
en su selector. Windows + Git Bash.

> Basado en llama.cpp; sin relación con los modelos Llama de Meta ni con el
> proyecto llama.cpp.

Este README explica la instalación paso a paso. Las mediciones en las que se basa
la configuración (denso frente a MoE, VRAM en Windows, MTP, Vulkan frente a ROCm,
una tarea real de agente) están en [FINDINGS.es.md](FINDINGS.es.md).

## Por qué llama-corral

Herramientas como Ollama o LM Studio ya cargan modelos bajo demanda, y las
aplicaciones de escritorio ya abren un chat con doble clic. Lo que aporta
llama-corral es cómo encajan las piezas en un mismo equipo:

- **Un servidor para el editor y el chat.** VS Code Copilot y Open WebUI hablan con
  el mismo router y los mismos perfiles. Eliges un modelo en cualquiera de los dos
  selectores y el router lo cambia; los dos pueden usarse a la vez.
- **Un chat que recoge al cerrar.** El lanzador abre Open WebUI en una ventana
  propia, reutiliza el router si ya está en marcha y, al cerrar la ventana, apaga
  Open WebUI y, si los arrancó él, el router y el modelo, así que la VRAM queda
  libre. Sin Docker.
- **Control total de cada modelo.** Los perfiles son flags de llama.cpp: capas de
  expertos en RAM (`n-cpu-moe`), decodificación especulativa con MTP, tipo de caché
  KV, límite de razonamiento y proyector de visión por perfil. Pueden convivir
  varias builds de llama.cpp.
- **Pruebas para ajustar, no adivinar.** Velocidad a 2k / 32k / 64k, visión,
  barrido de contexto, muestreo, razonamiento y pruebas agénticas, además de
  `llama vram`, que detecta cuándo Windows ha mandado el modelo a memoria compartida.
- **Pensado para Windows, Git Bash y Vulkan**, probado en una tarjeta AMD, cuando
  la mayoría de herramientas asumen Linux o NVIDIA.
- **Cada decisión está medida.** [FINDINGS.es.md](FINDINGS.es.md) recoge los datos
  en los que se basa la configuración.

Si buscas lo más sencillo, Ollama o LM Studio son más fáciles. Si solo necesitas
cambiar de modelo delante de llama.cpp, [llama-swap](https://github.com/mostlygeek/llama-swap)
hace eso. llama-corral es para exprimir una GPU, con un editor y un chat
compartiéndola.

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
  (`winget install astral-sh.uv`) y, solo para compilar tú el lanzador de Open WebUI,
  el módulo PS2EXE de PowerShell (`Install-Module ps2exe -Scope CurrentUser`).

## 2. Obtener el repositorio

```bash
git clone https://github.com/robmab/llama-corral.git /d/LLM
cd /d/LLM
```

Sirve cualquier ubicación (sin carpeta de destino, git crea `llama-corral`). Los ejemplos suponen `D:\LLM` (`/d/LLM` en Git Bash).

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
   [Tests/README.es.md](Tests/README.es.md).
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

Open WebUI se arranca con `Router\LocalLLM-Launcher.exe`. El `.exe` no está en
el repositorio, así que hay dos formas de conseguirlo:

- **Descargarlo (lo más fácil):** baja `LocalLLM-Launcher.exe` de la última
  [release](https://github.com/robmab/llama-corral/releases) y ponlo en
  `Router\`. Tiene que estar ahí: localiza el resto del proyecto a partir de su
  propia ubicación. GitHub Actions lo compila a partir del `.ps1` en cada release
  y publica su SHA256 al lado. No está firmado, así que Windows SmartScreen puede avisar la
  primera vez ("Más información" > "Ejecutar de todas formas").
- **Compilarlo tú:** el lanzador es un script de PowerShell
  (`Router\webui\LocalLLM-Launcher.ps1`). [PS2EXE](https://github.com/MScholtes/PS2EXE)
  lo empaqueta en un `.exe` para abrirlo con doble clic, sin escribir comandos.
  El resultado es el mismo que el descargado, pero generado en tu equipo. En PowerShell:

  ```powershell
  Install-Module ps2exe -Scope CurrentUser    # solo la primera vez
  cd D:\LLM\Router
  Invoke-ps2exe .\webui\LocalLLM-Launcher.ps1 .\LocalLLM-Launcher.exe -title "Local LLM"
  ```

  Solo hay que recompilar si cambias el `.ps1`.

Ábrelo con doble clic: arranca Open WebUI con `uvx` (sin Docker) en
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

- Mediciones y lecciones del ajuste en una Radeon RX 9070 XT (16 GB):
  [FINDINGS.es.md](FINDINGS.es.md).
- Más detalle: [Router/webui/README.es.md](Router/webui/README.es.md) (router y
  Open WebUI) y [Tests/README.es.md](Tests/README.es.md) (pruebas y ajuste).

## Licencia

[MIT](LICENSE). llama.cpp, Open WebUI y los modelos mantienen sus propias licencias.
