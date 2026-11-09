# Stop this project's speech-to-text server and show the result.
param([int]$Port = 8008)
$ErrorActionPreference = 'Stop'
. (Join-Path (Split-Path $PSScriptRoot -Parent) 'server_process.ps1')
$state = Join-Path $env:LOCALAPPDATA 'WisperLocal\stt'
New-Item -ItemType Directory -Force -Path $state | Out-Null
$log = Join-Path $state 'stop_last.log'
try {
    $message = Stop-LocalVoiceServer -Module 'stt_server' -AppDirectory $PSScriptRoot -Port $Port -PidFile (Join-Path $state 'stt_server.pid')
} catch {
    $message = $_.Exception.Message
}
$message | Out-File $log -Encoding utf8
Write-Host $message
try {
    $shell = New-Object -ComObject WScript.Shell
    $shell.Popup($message, 0, 'Local Voice Servers', 0x40) | Out-Null
} catch {}
