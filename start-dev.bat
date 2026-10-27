@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ======================================================
echo   Desk Racer · 曙光云立体密算版 - 本地开发启动器
echo ======================================================
if not exist "node_modules" (
  echo [1/2] 首次运行，正在安装依赖...
  call pnpm install
)
echo [启动] 正在启动本地服务并打开浏览器 http://127.0.0.1:5173/ ...
start "" "http://127.0.0.1:5173/"
call pnpm dev
pause
