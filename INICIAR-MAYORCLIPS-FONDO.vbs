Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")
BaseDir = FSO.GetParentFolderName(WScript.ScriptFullName)
LogsDir = BaseDir & "\storage\logs"
If Not FSO.FolderExists(LogsDir) Then FSO.CreateFolder(LogsDir)

' Arrancar Backend FastAPI oculto (sin ventana CMD)
WshShell.Run "cmd /c cd /d """ & BaseDir & """ && python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 > """ & LogsDir & "\backend.log"" 2>&1", 0, False

' Arrancar Frontend Vite oculto
WshShell.Run "cmd /c cd /d """ & BaseDir & "\frontend"" && npm run dev > """ & LogsDir & "\frontend.log"" 2>&1", 0, False

WScript.Sleep 3500
WshShell.Run "http://127.0.0.1:5173", 1, False
