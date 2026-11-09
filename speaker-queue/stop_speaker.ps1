# Stop this project's speaker queue server, after verifying its identity.
param([int]$Port = 8011)
$ErrorActionPreference = "Stop"
. (Join-Path (Split-Path $PSScriptRoot -Parent) "server_process.ps1")
$state = Join-Path $env:LOCALAPPDATA "WisperLocal\tts"
New-Item -ItemType Directory -Force -Path $state | Out-Null
$stopLog = Join-Path $state "stop_speaker_last.log"
try {
    $result = Stop-LocalVoiceServer -Module "speaker_queue" -AppDirectory $PSScriptRoot -Port $Port -PidFile (Join-Path $state "speaker_queue.pid") -BeforeStop {
        Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$Port/flush" -TimeoutSec 5 | Out-Null
    }
    $result | Out-File $stopLog -Encoding utf8
    Write-Host $result
} catch {
    $_.Exception.Message | Out-File $stopLog -Encoding utf8
    throw
}
