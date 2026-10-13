@echo off
REM Atalho de execucao da Calculadora de Atualizacao Judicial.
REM Sobe a interface web em http://localhost:8000 e abre o navegador.
REM Feche esta janela (ou Ctrl+C) para encerrar o servidor.

setlocal
cd /d "%~dp0"
set "PORT=8000"

set "PY="
where python >nul 2>&1 && set "PY=python"
if not defined PY where py >nul 2>&1 && set "PY=py -3"
if not defined PY (
  echo [erro] Python nao encontrado no PATH.
  pause
  exit /b 1
)

if not exist "data\indices.db" (
  echo Banco ausente - inicializando data\indices.db ...
  %PY% main.py init
  if errorlevel 1 (
    echo [erro] init falhou.
    pause
    exit /b 1
  )
)

echo Servidor em http://localhost:%PORT% ^(Ctrl+C para parar^)
start "" powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process 'http://localhost:%PORT%'"
%PY% main.py serve --port %PORT%

echo.
echo Servidor encerrado.
pause
