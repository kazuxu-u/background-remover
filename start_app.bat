@echo off
setlocal
cd /d "%~dp0"

:: --- Settings ---
set COMFY_BASE_URL=http://127.0.0.1:8188
:: set REMBG_MODEL=isnet-general-use
set REMBG_PROVIDER=cpu
set REMBG_MAX_EDGE=1024
set REMBG_TIMEOUT=60
:: ----------------

echo [*] Starting Background Remover App...
echo [*] ComfyUI URL: %COMFY_BASE_URL%

"C:\Users\momop\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" server.py

pause
