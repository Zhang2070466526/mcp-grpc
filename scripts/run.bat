@echo off
cd /d "%~dp0"
title EDI MCP
echo =================================================
echo   EDI MCP v0.1.4
echo   UI:  http://127.0.0.1:50026/ui
echo   MCP: http://127.0.0.1:50026/sse
echo   Close this window or press Ctrl+C to stop
echo =================================================
echo.
start "" http://127.0.0.1:50026/ui
edi_mcp_server.exe
