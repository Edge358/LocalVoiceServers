# Stop this project's text-to-speech server, after verifying its identity.
param([int]$Port = 8009)
$ErrorActionPreference = "Stop"
. (Join-Path (Split-Path $PSScriptRoot -Parent) "server_process.ps1")
$state = Join-Path $env:LOCALAPPDATA "WisperLocal\tts"
New-Item -ItemType Directory -Force -Path $state | Out-Null
$stopLog = Join-Path $state "stop_last.log"
try {
    $result = Stop-LocalVoiceServer -Module "tts_server" -AppDirectory $PSScriptRoot -Port $Port -PidFile (Join-Path $state "tts_server.pid")
    $result | Out-File $stopLog -Encoding utf8
    Write-Host $result
} catch {
    $_.Exception.Message | Out-File $stopLog -Encoding utf8
    throw
}
