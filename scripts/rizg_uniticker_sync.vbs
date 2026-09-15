Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
root = fso.GetParentFolderName(fso.GetParentFolderName(WScript.ScriptFullName))
pythonw = root & "\.venv\Scripts\pythonw.exe"
script = root & "\scripts\sync_uniticker_to_rizg.py"
If fso.FileExists(pythonw) And fso.FileExists(script) Then
  sh.CurrentDirectory = root
  sh.Run """" & pythonw & """ """ & script & """ --interval 15", 0, False
End If
