# Start the Whisper speech-to-text server (port 8008) hidden, if not already running.
# Silent on success; shows a message box only if startup fails.
# Code runs from this folder; logs and the PID file go to the state folder.
param(
    # 127.0.0.1 = this computer only. 0.0.0.0 lets other computers on your network connect.
    # Set the LOCALVOICE_STT_HOST environment variable to change the default.
    [string]$BindHost = $(if ($env:LOCALVOICE_STT_HOST) { $env:LOCALVOICE_STT_HOST } else { "127.0.0.1" }),
    [int]$Port = 8008,
    [string]$CondaEnv = "localvoice",
    [string]$PythonExe = "",
    [string]$CudaBin = "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.6\bin"
)
$ErrorActionPreference = "Stop"

. (Join-Path (Split-Path $PSScriptRoot -Parent) "server_process.ps1")
Add-Type -AssemblyName System.Windows.Forms

$WorkDir = $PSScriptRoot
$root = Join-Path $env:LOCALAPPDATA "WisperLocal"   # fixed path, shared with client apps
$StateDir = Join-Path $root "stt"
New-Item -ItemType Directory -Force -Path $StateDir | Out-Null
$PidFile = Join-Path $StateDir "stt_server.pid"

function Fail($msg) {
    [System.Windows.Forms.MessageBox]::Show(
        $msg,
        "Local Voice Servers",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Error
    ) | Out-Null
}

function Get-ListeningProcessId([int]$port) {
    $connection = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($connection -and $connection.OwningProcess -gt 0) {
        return [int]$connection.OwningProcess
    }

    return 0
}

function Find-CondaPython([string]$envName) {
    @(
        (Join-Path $env:USERPROFILE "miniconda3\envs\$envName\python.exe"),
        (Join-Path $env:USERPROFILE "anaconda3\envs\$envName\python.exe"),
        (Join-Path $env:USERPROFILE ".conda\envs\$envName\python.exe"),
        "C:\ProgramData\miniconda3\envs\$envName\python.exe",
        "C:\ProgramData\anaconda3\envs\$envName\python.exe"
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
}

if (-not $PythonExe) { $PythonExe = Find-CondaPython $CondaEnv }
if (-not $PythonExe -or -not (Test-Path $PythonExe)) {
    Fail("Start failed: python.exe for conda environment '$CondaEnv' not found.")
    return
}

# A listening port is only ours when its module, folder and port all match.
$listeningPid = Get-ListeningProcessId $Port
if ($listeningPid -gt 0) {
    try {
        $null = Get-LocalVoiceProcess -ProcessId $listeningPid -Module "stt_server" -AppDirectory $WorkDir -Port $Port
        Set-Content -Path $PidFile -Value ($listeningPid.ToString()) -Encoding ASCII
    } catch { Fail($_.Exception.Message) }
    return
}

# Launch uvicorn hidden from the target environment directly.
# The CUDA folder is added to PATH only if it exists on this computer.
$oldPath = $env:PATH
try {
    if ($CudaBin -and (Test-Path $CudaBin)) {
        $env:PATH = $CudaBin + ";" + $oldPath
    }
    $proc = Start-Process -FilePath $PythonExe `
        -WorkingDirectory $WorkDir `
        -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $StateDir "server_out.log") `
        -RedirectStandardError (Join-Path $StateDir "server_err.log") `
        -ArgumentList @("-m", "uvicorn", "stt_server:app", "--host", $BindHost, "--port", $Port.ToString(), "--app-dir", ('"' + $WorkDir + '"'))
}
finally {
    $env:PATH = $oldPath
}

# Wait for the port to listen and capture the real owning PID. A normal start takes
# seconds; the very first start downloads the model first, so allow up to 10 minutes.
$errLog = Join-Path $StateDir "server_err.log"
$owningPid = 0
for ($i = 0; $i -lt 2400; $i++) {
    Start-Sleep -Milliseconds 250
    $owningPid = Get-ListeningProcessId $Port
    if ($owningPid -gt 0) {
        try {
            $null = Get-LocalVoiceProcess -ProcessId $owningPid -Module "stt_server" -AppDirectory $WorkDir -Port $Port
        } catch { Fail($_.Exception.Message); return }
        break
    }
    if ($proc.HasExited) {
        Fail("Start failed: the server stopped while starting. See $errLog")
        return
    }
}

if ($owningPid -le 0) {
    Fail("Start failed: server did not begin listening on port $Port within 10 minutes. See $errLog")
    return
}

# Success path (silent)
Set-Content -Path $PidFile -Value ($owningPid.ToString()) -Encoding ASCII
