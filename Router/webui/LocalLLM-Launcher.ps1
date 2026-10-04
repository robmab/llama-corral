# ============================================================================
# Local LLM Launcher
# Starts llama-server in router mode (the model is picked in the Open WebUI model
# selector) + Open WebUI, opens a dedicated browser app window and, when that
# window is closed, shuts both services down.
#
# This .ps1 is the source. It is compiled to an .exe with PS2EXE (see README.md
# in this folder). Edit it here, not the .exe.
# ============================================================================

# --------------------------- CONFIGURE THIS --------------------------------
# Router folder (router.sh, models.ini, webui/). Worked out from where this file
# lives: the compiled .exe sits in Router\ and this .ps1 in Router\webui\.
$here = if ($PSScriptRoot) { $PSScriptRoot } else { [System.AppDomain]::CurrentDomain.BaseDirectory.TrimEnd('\') }
$ProjectDir = if ((Split-Path $here -Leaf) -eq 'webui') { Split-Path $here -Parent } else { $here }

# Script that starts llama-server (inside $ProjectDir)
$LlamaScriptName = "router.sh"

# llama-server port (--port in router.sh)
$LlamaPort    = 10001

# Open WebUI port (--port in start-open-webui.sh)
$WebUIPort    = 3000

# Path to Git Bash's bash.exe. Change it if Git for Windows lives somewhere else.
# Auto-detected if left empty and bash.exe is on the PATH.
$BashPath     = "C:\Program Files\Git\bin\bash.exe"

# Maximum wait times (seconds). Raise WebUITimeout if the first run takes long
# downloading dependencies.
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
    # GetConsoleWindow() is reliable for the calling process itself.
    try {
        $hwnd = [Native.Win32Window]::GetConsoleWindow()
        if ($hwnd -ne [IntPtr]::Zero) {
            [Native.Win32Window]::ShowWindowAsync($hwnd, 0) | Out-Null
        }
    } catch {}
}

function Wait-Port($port, $timeoutSec, $label, $logPath = $null) {
    # With $logPath, instead of progress dots it prints the new lines written by
    # the process (which starts with a hidden window), so the real progress shows
    # without having to display any window.
    $deadline = (Get-Date).AddSeconds($timeoutSec)
    Write-Host "    Waiting for $label (port $port)..."
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
                Write-Host "    $label ready." -ForegroundColor Green
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
    throw "bash.exe not found. Edit `$BashPath at the top of the script."
}

function Get-AppCapableBrowser {
    # Browsers that support --app + --user-data-dir (dedicated window mode)
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

    # Fallback: Edge, always installed on Windows 10/11
    $edgeCandidates = @(
        "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
        "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
        "$env:LOCALAPPDATA\Microsoft\Edge\Application\msedge.exe"
    )
    foreach ($c in $edgeCandidates) {
        if (Test-Path $c) {
            Write-Host "    (Your default browser does not support isolated app windows; using Edge for this window)" -ForegroundColor DarkYellow
            return $c
        }
    }
    throw "No Chromium browser (nor Edge) found to open the window."
}

# ============================================================================
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host "  Local LLM - llama.cpp router + Open WebUI" -ForegroundColor Cyan
Write-Host "=================================================" -ForegroundColor Cyan

$bash = Resolve-Bash
Set-Location $ProjectDir

$LogDir = Join-Path $ProjectDir "webui\logs"
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$LlamaLog = Join-Path $LogDir "launcher-llama.log"
$WebUILog = Join-Path $LogDir "launcher-webui.log"

function New-BashScript($path, [string[]]$lines) {
    # Plain LF, no BOM: a .sh written by PowerShell with a regular Set-Content
    # gets CRLF and sometimes a BOM, and bash can choke on that.
    $content = ($lines -join "`n") + "`n"
    [System.IO.File]::WriteAllText($path, $content, (New-Object System.Text.UTF8Encoding($false)))
}

Write-Host "    (Logs for this run: $LlamaLog / $WebUILog)" -ForegroundColor DarkGray

# Stops any previous llama-server (another launcher, one started by hand, or an
# orphaned router model): in router mode every model is a child process with its
# own port, so checking port 10001 is not enough.
function Stop-AllLlama {
    Get-Process llama-server -ErrorAction SilentlyContinue | ForEach-Object {
        try { Stop-Process -Id $_.Id -Force -ErrorAction Stop } catch {}
    }
}
# A router that is already running (started with "llama start" for VS Code) is
# reused and NOT stopped when the window closes. It is recognized because its
# /models includes the status of each model; a single-model llama-server does not.
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
    Write-Step "Router already running (llama start): reusing it; it will not be stopped on exit."
} else {
    if (Get-Process llama-server -ErrorAction SilentlyContinue) {
        Write-Host "    llama-server is running; stopping it before starting the router." -ForegroundColor DarkYellow
        Stop-AllLlama
        Start-Sleep -Seconds 3
    }

    # --- 1) llama-server -------------------------------------------------------
    # Starts with a hidden window from the beginning (WindowStyle Hidden), so no
    # window has to be force-hidden later (that is what failed: with Windows
    # Terminal as the default terminal, it sometimes only minimizes when asked
    # afterwards). Progress is still shown by tailing the log in this window.
    Write-Step "Starting the llama-server router (models load when selected)..."
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
        Write-Host "llama-server did not respond in time. Check the log: $LlamaLog" -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }
}

# --- 2) Open WebUI -----------------------------------------------------------
Write-Step "Starting Open WebUI (in the background; progress below)..."
$WebUIScript = Join-Path $LogDir "run-webui.sh"
New-BashScript $WebUIScript @(
    "cd `"$ProjectDir`" || exit 1"
    "./webui/start-open-webui.sh > `"$WebUILog`" 2>&1"
)
$webuiProc = Start-Process -FilePath $bash `
    -ArgumentList $WebUIScript `
    -WorkingDirectory $ProjectDir `
    -WindowStyle Hidden -PassThru

if (-not (Wait-Port -port $WebUIPort -timeoutSec $WebUITimeout -label "Open WebUI" -logPath $WebUILog)) {
    Write-Host "Open WebUI did not respond in time. Check the log: $WebUILog" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# --- 3) Browser in a dedicated window ----------------------------------------
Write-Step "Opening the browser..."
$browserExe = Get-AppCapableBrowser
$profileDir = Join-Path $env:TEMP "localllm-webui-profile"

$browserProc = Start-Process -FilePath $browserExe `
    -ArgumentList "--app=http://localhost:$WebUIPort", "--user-data-dir=$profileDir", "--new-window" `
    -PassThru

Write-Step "All running. Hiding this window; it keeps watching in the background."
Write-Host "    (Close the browser window to shut down llama-server and Open WebUI)" -ForegroundColor DarkGray
Start-Sleep -Seconds 2

Hide-OwnConsole

# --- 4) Wait for the browser window to close ---------------------------------
try {
    Wait-Process -Id $browserProc.Id -ErrorAction Stop
} catch {
    # If the process no longer exists when calling Wait-Process, carry on anyway
}

# --- 5) Shut the services down ------------------------------------------------
if ($OwnsLlama) {
    Write-Step "Browser closed. Shutting down llama-server and Open WebUI..."
} else {
    Write-Step "Browser closed. Shutting down Open WebUI (the router keeps running for VS Code)..."
}
Stop-ProcessOnPort -port $WebUIPort
try { Stop-Process -Id $webuiProc.Id -Force -ErrorAction SilentlyContinue } catch {}
if ($OwnsLlama) {
    Stop-ProcessOnPort -port $LlamaPort
    Stop-AllLlama
    if ($llamaProc) { try { Stop-Process -Id $llamaProc.Id -Force -ErrorAction SilentlyContinue } catch {} }
}

Write-Host "Done." -ForegroundColor Green
Start-Sleep -Seconds 2
