# Show whether the Whisper speech-to-text server is running, and its addresses.
param([int]$Port = 8008)
$ErrorActionPreference = "SilentlyContinue"

$root = Join-Path $env:LOCALAPPDATA "WisperLocal"   # fixed path, shared with client apps
$PidFile = Join-Path (Join-Path $root "stt") "stt_server.pid"

function Get-LanIpv4Addresses {
    Get-NetIPAddress -AddressFamily IPv4 |
        Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } |
        Select-Object -ExpandProperty IPAddress -Unique
}

$listen = Get-NetTCPConnection -LocalPort $Port -State Listen | Select-Object -First 1

if ($listen) {
    Write-Host ("RUNNING: port {0} is listening (PID {1})." -f $Port, $listen.OwningProcess)
    Write-Host ("Bound on: {0}:{1}" -f $listen.LocalAddress, $Port)
    Write-Host ("Local URL: http://127.0.0.1:{0}/" -f $Port)
    if ($listen.LocalAddress -eq "0.0.0.0") {
        foreach ($address in (Get-LanIpv4Addresses)) {
            Write-Host ("Network URL: http://{0}:{1}/" -f $address, $Port)
        }
    }
} else {
    Write-Host ("NOT RUNNING: nothing listening on port {0}." -f $Port)
}

if (Test-Path $PidFile) {
    Write-Host ("PID file: {0} ({1})" -f $PidFile, (Get-Content $PidFile | Select-Object -First 1).Trim())
} else {
    Write-Host ("PID file missing: {0}" -f $PidFile)
}

Write-Host ""
Write-Host "Press any key to close..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
