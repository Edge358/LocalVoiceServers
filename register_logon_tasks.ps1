# Create (or remove) Windows scheduled tasks that start the three servers when you log on.
# Run in a normal PowerShell window; no administrator rights needed.
#
#   .\register_logon_tasks.ps1                 # create the tasks (servers listen to this computer only)
#   .\register_logon_tasks.ps1 -AllowNetwork   # speech to text and text to speech also accept other computers
#   .\register_logon_tasks.ps1 -Remove         # delete the tasks
#
# The tasks run the start scripts in this folder, hidden, as you. If you move this
# folder, run this script again from the new place.
param(
    [switch]$AllowNetwork,
    [switch]$Remove,
    [string]$Prefix = "LocalVoiceServers",
    [string]$CondaEnv = "localvoice",
    [string]$PythonExe = "",
    [string]$CudaBin = "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.6\bin"
)
$ErrorActionPreference = "Stop"

$here = $PSScriptRoot
$user = "$env:USERDOMAIN\$env:USERNAME"
# Quote values as literal command arguments, not PowerShell expressions.
function Quote-TaskArgument([string]$Value) {
    if ($Value.Contains('"') -or $Value.Contains("`r") -or $Value.Contains("`n")) {
        throw 'Task arguments cannot contain quotes or newlines.'
    }
    return '"' + $Value.TrimEnd('\') + '"'
}
$hostArg = if ($AllowNetwork) { " -BindHost 0.0.0.0" } else { " -BindHost 127.0.0.1" }
$pythonArgs = ' -CondaEnv ' + (Quote-TaskArgument $CondaEnv)
if ($PythonExe) { $pythonArgs += ' -PythonExe ' + (Quote-TaskArgument $PythonExe) }
$cudaArg = ' -CudaBin ' + (Quote-TaskArgument $CudaBin)

$tasks = @(
    @{ Name = "$Prefix Speech to Text"; Script = "speech-to-text\start_stt.ps1";  Extra = ($hostArg + $cudaArg) },
    @{ Name = "$Prefix Text to Speech"; Script = "text-to-speech\start_tts.ps1";  Extra = $hostArg },
    @{ Name = "$Prefix Speaker Queue";  Script = "speaker-queue\start_speaker.ps1"; Extra = "" }
)

foreach ($t in $tasks) {
    $existing = Get-ScheduledTask -TaskPath "\" -TaskName $t.Name -ErrorAction SilentlyContinue

    if ($Remove) {
        if ($existing) {
            Unregister-ScheduledTask -TaskPath "\" -TaskName $t.Name -Confirm:$false
            Write-Host "Removed: $($t.Name)"
        } else {
            Write-Host "Not found: $($t.Name)"
        }
        continue
    }

    $script = Join-Path $here $t.Script
    if (-not (Test-Path $script)) { throw "Missing script: $script" }

    $action = New-ScheduledTaskAction -Execute "powershell.exe" `
        -Argument ("-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`"" + $pythonArgs + $t.Extra)
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
    $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

    if ($existing) {
        Set-ScheduledTask -TaskPath "\" -TaskName $t.Name -Action $action -Trigger $trigger `
            -Principal $principal -Settings $settings | Out-Null
        Write-Host "Updated: $($t.Name)"
    } else {
        Register-ScheduledTask -TaskPath "\" -TaskName $t.Name -Action $action -Trigger $trigger `
            -Principal $principal -Settings $settings | Out-Null
        Write-Host "Created: $($t.Name)"
    }
}

if (-not $Remove) {
    Write-Host ""
    Write-Host "The servers start at your next logon. To start them now without logging off:"
    foreach ($t in $tasks) { Write-Host "  Start-ScheduledTask -TaskName '$($t.Name)'" }
}
