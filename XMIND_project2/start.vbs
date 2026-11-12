Option Explicit
Dim shell, files, script, command, argument
Set shell = CreateObject("WScript.Shell")
Set files = CreateObject("Scripting.FileSystemObject")
script = files.BuildPath(files.GetParentFolderName(WScript.ScriptFullName), "start.ps1")
command = "powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File """ & script & """"
For Each argument In WScript.Arguments
    If InStr(argument, Chr(34)) > 0 Then
        MsgBox "Invalid argument.", vbCritical, "GNN"
        WScript.Quit 1
    End If
    command = command & " """ & argument & """"
Next
shell.Run command, 0, False
