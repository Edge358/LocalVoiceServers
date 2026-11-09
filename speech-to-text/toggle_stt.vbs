' toggle_stt.vbs: double-click to start or stop the Whisper speech-to-text server.
' Checks whether port 8008 is listening and offers the only valid action.
Option Explicit

Dim shell, fso, baseDir, exec, output, isRunning, msg, cmd
Set shell = CreateObject("WScript.Shell")
Set fso   = CreateObject("Scripting.FileSystemObject")

baseDir = fso.GetParentFolderName(WScript.ScriptFullName)

' --- Determine status (port 8008 listening?) ---
Set exec = shell.Exec("cmd /c netstat -ano -p tcp | findstr /R /C:"":8008 .*LISTENING""")
output = exec.StdOut.ReadAll

isRunning = (Len(output) > 0)

If isRunning Then
    msg = "Speech-to-text server is RUNNING." & vbCrLf & vbCrLf & _
          "Press OK to STOP the server." & vbCrLf & _
          "Press Cancel to exit."
Else
    msg = "Speech-to-text server is NOT running." & vbCrLf & vbCrLf & _
          "Press OK to START the server." & vbCrLf & _
          "Press Cancel to exit."
End If

' --- OK / Cancel dialog ---
If shell.Popup(msg, 0, "Local Voice Servers", 1 + 32) <> 1 Then
    WScript.Quit
End If

' --- Perform action ---
If isRunning Then
    cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & _
          baseDir & "\stop_stt.ps1"""
Else
    cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & _
          baseDir & "\start_stt.ps1"""
End If
shell.Run cmd, 0, False
