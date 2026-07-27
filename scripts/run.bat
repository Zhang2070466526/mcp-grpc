@echo off
title EDI MCP
echo =================================================
echo   EDI MCP v0.1.2
echo   UI:  http://127.0.0.1:50026/ui
echo   MCP: http://127.0.0.1:50026/sse
echo   Close this window to stop the service
echo =================================================
echo.
start http://127.0.0.1:50026/ui
start /b edi_mcp_server.exe
echo Press any key to stop the service...
pause >nul
taskkill -f -im edi_mcp_server.exe >nul 2>&1
