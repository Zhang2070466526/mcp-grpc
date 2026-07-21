@echo off
title EDA MCP
echo =================================================
echo   EDA MCP v0.1.0
echo   UI:  http://127.0.0.1:8026/ui
echo   MCP: http://127.0.0.1:8026/sse
echo   Close this window to stop the service
echo =================================================
echo.
start http://127.0.0.1:8026/ui
start /b eda-mcp.exe
echo Press any key to stop the service...
pause >nul
taskkill -f -im eda-mcp.exe >nul 2>&1
