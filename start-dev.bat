@echo off
cd /d "%~dp0"
echo ============================================================
echo   Desk Racer - Sugon Cloud Stereo Compute Edition
echo   Local One-Click Launcher (http://127.0.0.1:5173/)
echo ============================================================

powershell -NoProfile -Command "try { $c = New-Object System.Net.Sockets.TcpClient('127.0.0.1', 5173); $c.Close(); exit 0 } catch { exit 1 }"
if %errorlevel% equ 0 (
  echo [READY] Local server is already running. Opening browser...
  start "" "http://127.0.0.1:5173/"
  exit /b 0
)

if not exist "node_modules" (
  echo [1/2] Installing dependencies via pnpm...
  call pnpm install
)

echo [STARTING] Launching Vite dev server and opening browser...
echo (Keep this window open while playing; close it to stop server)
call pnpm dev -- --open
pause
