# Verify generated task commands without registering tasks or starting servers.
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$fixture = Join-Path $env:TEMP ('Local Voice Task Test ' + [guid]::NewGuid().ToString('N'))
$fixture = [IO.Path]::GetFullPath($fixture)
if (-not $fixture.StartsWith(([IO.Path]::GetFullPath($env:TEMP)).TrimEnd('\') + '\')) {
    throw 'Fixture must be inside TEMP.'
}
$reviewActions = New-Object 'System.Collections.Generic.List[object]'
function Get-ScheduledTask {}
function New-ScheduledTaskAction { param($Execute, $Argument) [pscustomobject]@{ Execute=$Execute; Arguments=$Argument } }
function New-ScheduledTaskTrigger {}
function New-ScheduledTaskPrincipal {}
function New-ScheduledTaskSettingsSet {}
function Register-ScheduledTask { param($TaskName, $Action) $reviewActions.Add($Action) }
try {
    New-Item -ItemType Directory -Path $fixture | Out-Null
    Copy-Item -LiteralPath (Join-Path $root 'register_logon_tasks.ps1') -Destination $fixture
    $stub = 'param($BindHost, $CondaEnv, $PythonExe, $CudaBin)' + "`r`n" + '$PSBoundParameters | ConvertTo-Json -Compress' + "`r`n"
    foreach ($relative in @('speech-to-text\start_stt.ps1', 'text-to-speech\start_tts.ps1', 'speaker-queue\start_speaker.ps1')) {
        $file = Join-Path $fixture $relative
        New-Item -ItemType Directory -Path (Split-Path $file -Parent) | Out-Null
        [IO.File]::WriteAllText($file, $stub)
    }
    foreach ($allowNetwork in @($false, $true)) {
        $reviewActions.Clear()
        & (Join-Path $fixture 'register_logon_tasks.ps1') -AllowNetwork:$allowNetwork -CondaEnv 'custom env' -PythonExe 'D:\My Python\python.exe' -CudaBin 'D:\My CUDA\bin\'
        if ($reviewActions.Count -ne 3) { throw 'Expected three task commands.' }
        $index = 0
        foreach ($action in $reviewActions) {
            $info = New-Object System.Diagnostics.ProcessStartInfo
            $info.FileName = $action.Execute
            $info.Arguments = $action.Arguments
            $info.UseShellExecute = $false
            $info.CreateNoWindow = $true
            $info.RedirectStandardOutput = $true
            $process = [Diagnostics.Process]::Start($info)
            if (-not $process.WaitForExit(10000)) { $process.Kill(); throw 'Task command timed out.' }
            $parameters = $process.StandardOutput.ReadToEnd() | ConvertFrom-Json
            $process.Dispose()
            if ($parameters.PythonExe -ne 'D:\My Python\python.exe' -or $parameters.CondaEnv -ne 'custom env') { throw 'Python settings were lost.' }
            if ($index -eq 0 -and $parameters.CudaBin -ne 'D:\My CUDA\bin') { throw 'CUDA path was lost.' }
            if ($index -lt 2) {
                $expected = if ($allowNetwork) { '0.0.0.0' } else { '127.0.0.1' }
                if ($parameters.BindHost -ne $expected) { throw 'Wrong network binding.' }
            }
            $index++
        }
    }
    Write-Host 'PASS: all task commands preserve paths with spaces, environment and network settings.'
} finally {
    # Delete only the known fixture files, then empty directories.
    foreach ($relative in @('speech-to-text\start_stt.ps1', 'text-to-speech\start_tts.ps1', 'speaker-queue\start_speaker.ps1', 'register_logon_tasks.ps1')) {
        Remove-Item -LiteralPath (Join-Path $fixture $relative) -ErrorAction SilentlyContinue
    }
    foreach ($relative in @('speech-to-text', 'text-to-speech', 'speaker-queue')) {
        Remove-Item -LiteralPath (Join-Path $fixture $relative) -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $fixture -ErrorAction SilentlyContinue
}
