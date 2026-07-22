# eda_mcp_server 打包脚本
$ErrorActionPreference = "Stop"
Write-Host "=== EDA MCP Build ===" -ForegroundColor Cyan
Write-Host "[1/4] Cleaning..." -ForegroundColor Yellow
Remove-Item -Recurse -Force dist, build -ErrorAction SilentlyContinue
Write-Host "[2/5] Running tests..." -ForegroundColor Yellow
uv run pytest -q
if ($LASTEXITCODE -ne 0) { Write-Host "TESTS FAILED" -ForegroundColor Red; exit $LASTEXITCODE }
Write-Host "[3/5] Building with PyInstaller..." -ForegroundColor Yellow
uv run pyinstaller --clean --noconfirm scripts/eda_mcp_server.spec
Write-Host "[4/5] Verifying..." -ForegroundColor Yellow
if (Test-Path "dist/eda-mcp/eda_mcp_server.exe") {
    $size = (Get-Item "dist/eda-mcp/eda_mcp_server.exe").Length / 1MB
    Write-Host "OK: dist/eda-mcp/eda_mcp_server.exe ($([math]::Round($size,1)) MB)" -ForegroundColor Green
} else { Write-Host "FAIL" -ForegroundColor Red; exit 1 }
Write-Host "[5/5] Generating config + launcher + cleaning..." -ForegroundColor Yellow
@"
# EDA MCP 配置文件 - 按实际环境修改
EDA_GRPC_SERVER=127.0.0.1:50055
EDI_PATH=C:\Program Files (x86)\EDI\EDI.exe
TURBOCHARTS_PATH=C:\Program Files (x86)\EDI\turbocharts_app.exe
MCP_TRANSPORT=sse
MCP_HOST=127.0.0.1
MCP_PORT=8026
"@ | Set-Content "dist/eda-mcp/.env" -Encoding UTF8
Copy-Item -Force scripts/run.bat "dist/eda-mcp/start_server.bat"
Remove-Item -Recurse -Force build -ErrorAction SilentlyContinue
Remove-Item -Force dist/eda_mcp_server.exe -ErrorAction SilentlyContinue
Write-Host "[6/6] Creating archive..." -ForegroundColor Yellow
Compress-Archive -Path "dist/eda-mcp/*" -DestinationPath "dist/eda-mcp.zip" -Force
Write-Host "Done. Output: dist/eda-mcp/ + dist/eda-mcp.zip" -ForegroundColor Green
