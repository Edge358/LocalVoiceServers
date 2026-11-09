# Shared process checks. Never adopt or stop a process based only on its port or PID.
function Get-LocalVoiceProcess {
    param([int]$ProcessId, [string]$Module, [string]$AppDirectory, [int]$Port)
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction Stop
    if (-not $process) { return $null }
    $directory = [IO.Path]::GetFullPath($AppDirectory).TrimEnd('\')
    $command = [string]$process.CommandLine
    $modulePattern = '\s-m\s+uvicorn\s+' + [regex]::Escape($Module + ':app') + '(?=\s|$)'
    $portPattern = '\s--port\s+' + $Port + '(?=\s|$)'
    $directoryPattern = '\s--app-dir\s+(?:"' + [regex]::Escape($directory) + '"|' +
        [regex]::Escape($directory) + ')(?=\s|$)'
    if ($process.Name -notin @('python.exe', 'pythonw.exe') -or
        $command -notmatch $modulePattern -or $command -notmatch $portPattern -or
        $command -notmatch $directoryPattern) {
        throw "Refusing to manage PID ${ProcessId}: it is not $Module from $directory on port $Port."
    }
    return $process
}

function Stop-LocalVoiceServer {
    param([string]$Module, [string]$AppDirectory, [int]$Port, [string]$PidFile,
          [scriptblock]$BeforeStop)
    $connections = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    $processIds = @($connections | Select-Object -ExpandProperty OwningProcess -Unique)
    if ($processIds.Count -gt 1) {
        throw "More than one process listens on port $Port. No process was stopped."
    }
    $serverId = 0
    if ($processIds.Count -eq 1) {
        $serverId = [int]$processIds[0]
    } elseif (Test-Path -LiteralPath $PidFile) {
        [int]::TryParse(([IO.File]::ReadAllText($PidFile)).Trim(), [ref]$serverId) | Out-Null
    }
    if ($serverId -le 0) { return 'Server is not running.' }
    # Open and retain the process handle before checking its command line, so a
    # subsequently recycled PID cannot redirect Kill to a different process.
    $target = Get-Process -Id $serverId -ErrorAction SilentlyContinue
    if (-not $target) {
        Remove-Item -LiteralPath $PidFile -ErrorAction SilentlyContinue
        return 'Server is not running (removed stale PID file).'
    }
    try {
        $null = $target.Handle
        $verified = Get-LocalVoiceProcess -ProcessId $serverId -Module $Module -AppDirectory $AppDirectory -Port $Port
        if (-not $verified -or $target.HasExited) { return 'Server has already stopped.' }
        if ($BeforeStop -and $connections.Count) { & $BeforeStop }
        if (-not $target.HasExited) {
            $target.Kill()
            if (-not $target.WaitForExit(5000)) { throw "PID $serverId did not stop within five seconds." }
        }
        if (Test-Path -LiteralPath $PidFile) {
            $saved = ([IO.File]::ReadAllText($PidFile)).Trim()
            if ($saved -eq $serverId.ToString()) { Remove-Item -LiteralPath $PidFile }
        }
        return "Server stopped (PID $serverId)."
    } finally {
        $target.Dispose()
    }
}
