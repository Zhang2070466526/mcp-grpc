# EDA MCP 打包脚本
$ErrorActionPreference = "Stop"
Write-Host "=== EDA MCP Build ===" -ForegroundColor Cyan
Write-Host "[1/4] Cleaning..." -ForegroundColor Yellow
Remove-Item -Recurse -Force dist, build -ErrorAction SilentlyContinue
Write-Host "[2/4] Running tests..." -ForegroundColor Yellow
uv run python -c "from tests.test_project_reader import *; from tests.test_component_tools import *; from tests.test_turbocharts_runner import *; from tests.test_health import *; from tests.test_tool_registry import *; print('All passed')"
Write-Host "[3/4] Building with PyInstaller..." -ForegroundColor Yellow
uv run pyinstaller --clean --noconfirm scripts/eda_mcp.spec
Write-Host "[4/4] Verifying..." -ForegroundColor Yellow
if (Test-Path "dist/EDA MCP/eda-mcp.exe") {
    $size = (Get-Item "dist/EDA MCP/eda-mcp.exe").Length / 1MB
    Write-Host "OK: dist/EDA MCP/eda-mcp.exe ($([math]::Round($size,1)) MB)" -ForegroundColor Green
} else { Write-Host "FAIL" -ForegroundColor Red; exit 1 }
Write-Host "[5/5] Copying config + cleaning..." -ForegroundColor Yellow
Copy-Item -Force .env "dist/EDA MCP/"
Remove-Item -Recurse -Force build -ErrorAction SilentlyContinue
Remove-Item -Force dist/eda-mcp.exe -ErrorAction SilentlyContinue
Write-Host "Done. Output: dist/EDA MCP/" -ForegroundColor Green
