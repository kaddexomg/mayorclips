@echo off
chcp 65001 >nul
title MayorClips — Plataforma de Clipping Inteligente
cls

echo ======================================================================
echo                MAYORCLIPS — INICIANDO SISTEMA
echo    Clipping con IA, Motion Graphics por Codigo y Publicador Multi-Red
echo ======================================================================
echo.

:: 1. Verificar Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python no encontrado en el sistema.
    pause
    exit /b 1
)

:: 2. Verificar Node.js
where node >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js no encontrado en el sistema.
    pause
    exit /b 1
)

echo [1/3] Iniciando Backend FastAPI (El Pulpo IA + Engine FFmpeg)...
start "MayorClips Backend" cmd /k "cd /d %~dp0 && python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000"

:: Esperar 2 segundos para inicializar backend
timeout /t 2 /nobreak >nul

echo [2/3] Iniciando Frontend Quanty Clips (Vite)...
start "MayorClips Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

timeout /t 2 /nobreak >nul

echo [3/3] Abriendo navegador en la aplicacion...
start http://127.0.0.1:5173

echo.
echo ======================================================================
echo    MayorClips esta activo y corriendo en:
echo    - Frontend Web: http://127.0.0.1:5173
echo    - API Backend:  http://127.0.0.1:8000/docs
echo.
echo    Para detener la aplicacion, cierra las ventanas minimizadas.
echo ======================================================================
echo.
pause
