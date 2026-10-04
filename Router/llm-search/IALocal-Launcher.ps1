# ============================================================================
# IA Local Launcher (router: Qwen 3.6 + Ornith 9B)
# Arranca llama-server en modo router (Qwen 3.6 general y Ornith 9B, se elige en el
# selector de modelo de Open WebUI) + Open WebUI,
# abre una ventana de app dedicada con el navegador y, cuando esa ventana se
# cierra, apaga los dos servicios solo.
#
# Este .ps1 es la fuente. Se compila a .exe con PS2EXE (ver README.md de esta
# carpeta). Editalo aqui, no en el .exe.
# ============================================================================

# --------------------------- CONFIGURA ESTO --------------------------------
# Carpeta donde viven router.sh, modelos.ini y la carpeta llm-search/
$ProjectDir   = "D:\LLM\Router"

# Script que arranca llama-server (dentro de $ProjectDir)
$LlamaScriptName = "router.sh"

# Puerto de llama-server (--port en router.sh)
$LlamaPort    = 10001

# Puerto de Open WebUI (el que usa --port en start-open-webui.sh)
$WebUIPort    = 3000

# Ruta a bash.exe de Git Bash. Si tienes Git for Windows en otra carpeta,
# cambia esto. Se autodetecta si lo dejas vacio y esta en el PATH.
$BashPath     = "C:\Program Files\Git\bin\bash.exe"

# Tiempos maximos de espera (segundos). Sube WebUITimeout si la primera vez
# tarda mucho descargando dependencias.
$LlamaTimeout = 180
$WebUITimeout = 420
# -----------------------------------------------------------------------------

$ErrorActionPreference = "Stop"
Add-Type -Name Win32Window -Namespace Native -MemberDefinition @"
    [DllImport("user32.dll")] public static extern bool ShowWindowAsync(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll", CharSet = CharSet.Auto)] public static extern IntPtr FindWindow(string lpClassName, string lpWindowName);
    [DllImport("kernel32.dll")] public static extern IntPtr GetConsoleWindow();
"@

function Write-Step($msg) {
    Write-Host ""
    Write-Host "==> $msg" -ForegroundColor Cyan
}

function Hide-OwnConsole {
    # GetConsoleWindow() si es fiable para el propio proceso llamante.
    try {
        $hwnd = [Native.Win32Window]::GetConsoleWindow()
        if ($hwnd -ne [IntPtr]::Zero) {
            [Native.Win32Window]::ShowWindowAsync($hwnd, 0) | Out-Null
        }
    } catch {}
}

function Wait-Port($port, $timeoutSec, $label, $logPath = $null) {
    # Si se da $logPath, en vez de puntos de progreso se muestran las lineas
    # nuevas que va escribiendo el proceso (que arranca con ventana oculta),
    # asi se ve el avance real sin necesidad de mostrar ninguna ventana.
    $deadline = (Get-Date).AddSeconds($timeoutSec)
    Write-Host "    Esperando a $label (puerto $port)..."
    $lastLineCount = 0
    while ((Get-Date) -lt $deadline) {
        if ($logPath -and (Test-Path $logPath)) {
            $lines = @(Get-Content -Path $logPath -ErrorAction SilentlyContinue)
            if ($lines.Count -gt $lastLineCount) {
                $lines[$lastLineCount..($lines.Count - 1)] | ForEach-Object { Write-Host "      $_" -ForegroundColor DarkGray }
                $lastLineCount = $lines.Count
            }
        }
        $tcp = New-Object System.Net.Sockets.TcpClient
        try {
            $tcp.Connect("127.0.0.1", $port)
            if ($tcp.Connected) {
                $tcp.Close()
                Write-Host "    $label listo." -ForegroundColor Green
                return $true
            }
        } catch {} finally { $tcp.Dispose() }
        Start-Sleep -Seconds 1
    }
    return $false
}

function Stop-ProcessOnPort($port) {
    try {
        Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique |
            ForEach-Object {
                try { Stop-Process -Id $_ -Force -ErrorAction Stop } catch {}
            }
    } catch {}
}

function Resolve-Bash {
    if ($BashPath -and (Test-Path $BashPath)) { return $BashPath }
    $cmd = Get-Command bash.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    throw "No encuentro bash.exe. Edita `$BashPath al principio del script."
}

function Get-AppCapableBrowser {
    # Navegadores que soportan --app + --user-data-dir (modo ventana dedicada)
    $chromiumNames = @('chrome.exe','msedge.exe','brave.exe','vivaldi.exe','opera.exe','chromium.exe')

    try {
        $progId = (Get-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.html\UserChoice" -ErrorAction Stop).ProgId
        $cmdLine = (Get-ItemProperty "Registry::HKEY_CLASSES_ROOT\$progId\shell\open\command" -ErrorAction Stop).'(default)'
        if ($cmdLine -match '"([^"]+\.exe)"') {
            $exePath = $Matches[1]
            $exeName = Split-Path $exePath -Leaf
            if ($chromiumNames -contains $exeName.ToLower() -and (Test-Path $exePath)) {
                return $exePath
            }
        }
    } catch {}

    # Fallback: Edge, que viene siempre instalado en Windows 10/11
    $edgeCandidates = @(
        "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
        "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
        "$env:LOCALAPPDATA\Microsoft\Edge\Application\msedge.exe"
    )
    foreach ($c in $edgeCandidates) {
        if (Test-Path $c) {
            Write-Host "    (Tu navegador predeterminado no admite ventana de app aislada; uso Edge para esta ventana)" -ForegroundColor DarkYellow
            return $c
        }
    }
    throw "No encuentro un navegador Chromium (ni Edge) para abrir la ventana."
}

# ============================================================================
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host "  IA Local - Qwen 3.6 / Ornith 9B + busqueda web" -ForegroundColor Cyan
Write-Host "=================================================" -ForegroundColor Cyan

$bash = Resolve-Bash
Set-Location $ProjectDir

$LogDir = Join-Path $ProjectDir "llm-search\logs"
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$LlamaLog = Join-Path $LogDir "launcher-llama.log"
$WebUILog = Join-Path $LogDir "launcher-webui.log"

function New-BashScript($path, [string[]]$lines) {
    # LF puro, sin BOM: un .sh escrito por PowerShell con Set-Content normal
    # lleva CRLF y a veces BOM, y bash puede atragantarse con eso.
    $content = ($lines -join "`n") + "`n"
    [System.IO.File]::WriteAllText($path, $content, (New-Object System.Text.UTF8Encoding($false)))
}

Write-Host "    (Log de esta corrida en: $LlamaLog / $WebUILog)" -ForegroundColor DarkGray

# Para cualquier llama-server previo (otro lanzador, uno arrancado a mano o un
# modelo huerfano del router): en modo router cada modelo es un proceso hijo con
# su propio puerto, asi que no basta con mirar el 10001.
function Stop-AllLlama {
    Get-Process llama-server -ErrorAction SilentlyContinue | ForEach-Object {
        try { Stop-Process -Id $_.Id -Force -ErrorAction Stop } catch {}
    }
}
# Un router ya en marcha (arrancado con "llama start" para VS Code) se reutiliza y
# NO se apaga al cerrar la ventana. Se reconoce porque su /models incluye el
# estado de cada modelo; un llama-server de un solo modelo no lo trae.
function Test-RouterRunning {
    try {
        $r = Invoke-RestMethod -Uri "http://127.0.0.1:$LlamaPort/models" -Headers @{ Authorization = "Bearer apikey" } -TimeoutSec 3
        return [bool]($r.data | Where-Object { $_.status })
    } catch { return $false }
}

$OwnsLlama = $true
$llamaProc = $null
if (Test-RouterRunning) {
    $OwnsLlama = $false
    Write-Step "Router ya en marcha (llama start): lo reutilizo y no lo apagare al cerrar."
} else {
    if (Get-Process llama-server -ErrorAction SilentlyContinue) {
        Write-Host "    Hay llama-server en marcha; los paro antes de arrancar el router." -ForegroundColor DarkYellow
        Stop-AllLlama
        Start-Sleep -Seconds 3
    }

    # --- 1) llama-server -------------------------------------------------------
    # Arranca con la ventana oculta desde YA (WindowStyle Hidden). Asi no hay
    # ninguna ventana que luego haya que ocultar a la fuerza (eso es lo que
    # fallaba: si tienes Windows Terminal como terminal por defecto, a veces
    # solo minimiza en vez de ocultar cuando se lo pides despues). El progreso
    # se ve igual, tail del log en esta misma ventana.
    Write-Step "Arrancando el router de llama-server (los modelos se cargan al elegirlos)..."
    $LlamaScript = Join-Path $LogDir "run-llama.sh"
    New-BashScript $LlamaScript @(
        "cd `"$ProjectDir`" || exit 1"
        "./$LlamaScriptName > `"$LlamaLog`" 2>&1"
    )
    $llamaProc = Start-Process -FilePath $bash `
        -ArgumentList $LlamaScript `
        -WorkingDirectory $ProjectDir `
        -WindowStyle Hidden -PassThru

    if (-not (Wait-Port -port $LlamaPort -timeoutSec $LlamaTimeout -label "llama-server" -logPath $LlamaLog)) {
        Write-Host "llama-server no respondio a tiempo. Revisa el log: $LlamaLog" -ForegroundColor Red
        Read-Host "Pulsa Enter para salir"
        exit 1
    }
}

# --- 2) Open WebUI -----------------------------------------------------------
Write-Step "Arrancando Open WebUI (en segundo plano; progreso abajo)..."
$WebUIScript = Join-Path $LogDir "run-webui.sh"
New-BashScript $WebUIScript @(
    "cd `"$ProjectDir`" || exit 1"
    "./llm-search/start-open-webui.sh > `"$WebUILog`" 2>&1"
)
$webuiProc = Start-Process -FilePath $bash `
    -ArgumentList $WebUIScript `
    -WorkingDirectory $ProjectDir `
    -WindowStyle Hidden -PassThru

if (-not (Wait-Port -port $WebUIPort -timeoutSec $WebUITimeout -label "Open WebUI" -logPath $WebUILog)) {
    Write-Host "Open WebUI no respondio a tiempo. Revisa el log: $WebUILog" -ForegroundColor Red
    Read-Host "Pulsa Enter para salir"
    exit 1
}

# --- 3) Navegador en ventana dedicada ---------------------------------------
Write-Step "Abriendo el navegador..."
$browserExe = Get-AppCapableBrowser
$profileDir = Join-Path $env:TEMP "ialocal-webui-profile"

$browserProc = Start-Process -FilePath $browserExe `
    -ArgumentList "--app=http://localhost:$WebUIPort", "--user-data-dir=$profileDir", "--new-window" `
    -PassThru

Write-Step "Todo en marcha. Ocultando esta ventana; sigue vigilando en segundo plano."
Write-Host "    (Cierra la ventana del navegador para apagar llama-server y Open WebUI)" -ForegroundColor DarkGray
Start-Sleep -Seconds 2

Hide-OwnConsole

# --- 4) Esperar a que se cierre la ventana del navegador --------------------
try {
    Wait-Process -Id $browserProc.Id -ErrorAction Stop
} catch {
    # Si el proceso ya no existe al llamar Wait-Process, seguimos igualmente
}

# --- 5) Apagar los servicios -------------------------------------------------
if ($OwnsLlama) {
    Write-Step "Navegador cerrado. Apagando llama-server y Open WebUI..."
} else {
    Write-Step "Navegador cerrado. Apagando Open WebUI (el router sigue en marcha para VS Code)..."
}
Stop-ProcessOnPort -port $WebUIPort
try { Stop-Process -Id $webuiProc.Id -Force -ErrorAction SilentlyContinue } catch {}
if ($OwnsLlama) {
    Stop-ProcessOnPort -port $LlamaPort
    Stop-AllLlama
    if ($llamaProc) { try { Stop-Process -Id $llamaProc.Id -Force -ErrorAction SilentlyContinue } catch {} }
}

Write-Host "Listo." -ForegroundColor Green
Start-Sleep -Seconds 2
