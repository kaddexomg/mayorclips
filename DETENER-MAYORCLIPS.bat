@echo off
chcp 65001 >nul
echo Deteniendo procesos de MayorClips (puertos 8000 y 5173)...
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8000,5173 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }"
echo MayorClips detenido correctamente.
timeout /t 2 >nul
