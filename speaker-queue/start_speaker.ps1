# Start the speaker queue service (port 8011) hidden, if not already running.
# Code runs from this folder; logs and the PID file go to the state folder.
param(
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8011,
    [string]$CondaEnv = "localvoice",
    [string]$PythonExe = ""
)

$ErrorActionPreference = "Stop"
. (Join-Path (Split-Path $PSScriptRoot -Parent) "server_process.ps1")
$dir = $PSScriptRoot
$root = Join-Path $env:LOCALAPPDATA "WisperLocal"   # fixed path, shared with client apps
$state = Join-Path $root "tts"
New-Item -ItemType Directory -Force -Path $state | Out-Null
$startLog = Join-Path $state "start_speaker_last.log"
$stamp = Get-Date -Format s

function Find-CondaPython([string]$envName) {
    @(
        (Join-Path $env:USERPROFILE "miniconda3\envs\$envName\python.exe"),
        (Join-Path $env:USERPROFILE "anaconda3\envs\$envName\python.exe"),
        (Join-Path $env:USERPROFILE ".conda\envs\$envName\python.exe"),
        "C:\ProgramData\miniconda3\envs\$envName\python.exe",
        "C:\ProgramData\anaconda3\envs\$envName\python.exe"
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
}

$listening = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($listening) {
    foreach ($owner in @($listening.OwningProcess | Select-Object -Unique)) {
        $null = Get-LocalVoiceProcess -ProcessId $owner -Module "speaker_queue" -AppDirectory $dir -Port $Port
    }
    "Start skipped ${stamp}: already listening on $Port (PID $($listening[0].OwningProcess))." |
        Out-File $startLog -Encoding utf8
    exit 0
}

if (-not $PythonExe) { $PythonExe = Find-CondaPython $CondaEnv }
if (-not $PythonExe -or -not (Test-Path $PythonExe)) {
    "Start failed ${stamp}: python.exe for conda environment '$CondaEnv' not found." |
        Out-File $startLog -Encoding utf8
    exit 1
}

$p = Start-Process -FilePath $PythonExe `
    -ArgumentList "-m", "uvicorn", "speaker_queue:app", "--host", $BindHost, "--port", $Port.ToString(), "--app-dir", ('"' + $dir + '"') `
    -WorkingDirectory $dir -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $state "speaker_out.log") `
    -RedirectStandardError (Join-Path $state "speaker_err.log")

$p.Id | Out-File (Join-Path $state "speaker_queue.pid") -Encoding ascii
"Start started ${stamp}: PID $($p.Id), code in $dir, listening on ${BindHost}:$Port." |
    Out-File $startLog -Encoding utf8
