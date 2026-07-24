# EDA MCP 项目交接文档

## 项目概述

将 EDA-PMDS/EDI 的 gRPC 接口和本地命令行工具封装为 MCP 服务，使 AI 客户端能通过自然语言操作 EDA 工程。

当前版本为**本地 MCP 模式**：每台电脑独立运行，服务、文件、EDI 均在本机，无需公共服务或远程 Agent。

## 代码仓库

D:\GitLabCode\mcp-grpc

## 目录结构

```
proto/                  # protobuf 协议文件
servers/
  registry_server.py    # 工具注册中心 + /health
  eda/                  # EDA 工具（13 个）
    __init__.py          # 公共 API + 工具清单
    config.py            # 配置 + validate_file + ProjectReader + S-expression
    grpc_client.py       # gRPC 通信层（带 EDA 全局锁）
    project_manage.py    # 工程管理（6 工具）
    simulation.py        # 仿真（2 工具）
    design_export.py     # 网表/截图（2 工具）
    model_replace.py     # 模型替换（1 工具）
    edi_launcher.py      # 启动 EDI（1 工具）
    compare_results.py   # 仿真对比（1 工具）
  turbocharts/
    config.py            # 公共函数（run_turbocharts）
    convert_raw.py       # RAW 转图（1 工具）
  web_routes.py          # Web 路由（/health, /chat, /ui）
start_servers.py         # 一键启动入口
tests/                   # 测试套件（5 个文件）
scripts/                 # 打包脚本 + PyInstaller 配置
.mcp.json                # Claude Code 配置
.env                     # 环境变量（不提交 Git）
pyproject.toml           # uv 项目配置
README.md                # 项目主文档
HANDOVER.md              # 本文档
```

## 技术栈

Python 3.12+ / uv 包管理 / FastMCP (mcp >= 1.0.0) / grpcio >= 1.81.0 / protobuf >= 6.33.5 / python-dotenv

## MCP 工具清单（23 个）

**工程管理**：list_epp_projects, open_eda_project, close_eda_project, list_project_components, get_component_parameters, get_project_summary

**仿真**：simulate_project, start_simulation_async, get_simulation_async_status, get_simulation_async_result, simulate_netlist_with_ads, compare_simulation_results

**ANSYS**：open_hfss_project（GetActiveObject附着/单启动）, close_hfss_project（COM优先+PID记录）, launch_aedt, get_hfss_project_info（纯查询不启动）

**导出分析**：export_project_netlist, capture_schematic

**模型启动**：replace_models_from_csv, launch_edi

**图表**：turbocharts_convert

## 配置说明

每台电脑独立配置 `.env`，所有服务均为本机调用：

```
EDA_GRPC_SERVER=127.0.0.1:50055
EDI_PATH=C:\Program Files (x86)\EDI\EDI.exe
TURBOCHARTS_PATH=C:\Program Files (x86)\EDI\turbocharts_app.exe
MCP_TRANSPORT=sse
MCP_HOST=127.0.0.1
MCP_PORT=8026
```

## 启动方式

```powershell
cd D:\GitLabCode\mcp-grpc
uv run python start_servers.py                        # HTTP 模式（推荐）
uv run python start_servers.py --transport stdio       # stdio 模式
```

## 通信流程

gRPC 工具：AI 客户端 -> MCP 工具 -> grpc_client.call_grpc() -> PerformAction + FetchEvent -> 返回结果

本地工具：AI 客户端 -> MCP 工具 -> subprocess -> 返回结果

## 并发控制

- EDA gRPC 操作：全局 RLock，最大并发 1
- 文件读取：允许并发（最多 4）
- Turbocharts：BoundedSemaphore(1)
- 单实例控制：启动时检查端口

## 测试

```powershell
uv run python tests/test_project_reader.py
uv run python tests/test_component_tools.py
uv run python tests/test_turbocharts_runner.py
uv run python tests/test_health.py
uv run python tests/test_tool_registry.py
```

## 打包

```powershell
powershell -File scripts/build.ps1
# 输出: dist/eda-mcp/（含 eda_mcp_server.exe + start_server.bat + .env，约 137 MB）
```

## 工具注册机制

所有工具函数为纯函数（无 MCP 装饰器），定义在 `servers/eda/*.py` 中，由 `servers/registry_server.py` 统一导入并注册到 FastMCP 实例。`servers/eda/__init__.py` 作为公共 API 入口 re-export 所有工具函数。

```
project_manage.py  ->  __init__.py  ->  registry_server.py  ->  start_servers.py
  (定义纯函数)          (re-export)      (mcp.tool() 注册)      (解析参数, 启动)
```

## 扩展开发

添加 gRPC 工具：在 servers/eda/ 对应文件中添加 @mcp.tool() 装饰器 -> registry_server.py import 模块

重新生成 proto：
```powershell
python -m grpc_tools.protoc -I proto --python_out=proto --grpc_python_out=proto proto/ecserver.proto
# 编辑 proto/ecserver_pb2_grpc.py：import ecserver_pb2 -> from proto import ecserver_pb2
```

## 已知问题与注意事项

1. 本地 proto 目录名为 `proto`，避免与 grpcio 包名冲突
2. stdio 模式下不能向 stdout 输出任何内容（会破坏 MCP 协议）
3. `.env` 通过 `python-dotenv` 加载，在所有 service 模块首次 import 时生效
4. Windows 路径反斜杠在 `.env` 中不需要转义
5. gRPC 服务地址格式必须为 `host:port`
6. 超时上限：open/close 300s, simulate 3600s, turbocharts 600s
7. 端口占用：`netstat -ano | findstr <端口>` -> `taskkill -f -pid <PID>`
8. `launch_edi` 返回 success/process_started/grpc_ready 三个字段
9. `grpc_client.py` 从 `config.py` 统一导入 EDA_GRPC_SERVER
10. `.gitignore` 已排除 .idea/、.claude/、.env、dist/、build/、logs/
11. `start_servers.py` 使用私有属性 _tool_manager，MCP 版本升级后需验证
12. Windows HTTP 使用 SelectorEventLoop 避免 WinError 64
13. `/health` 端点可区分 MCP 故障与 EDI 离线
14. `compare_simulation_results` 使用 Matplotlib + numpy 做叠图插值
15. 打包为目录型，复制 dist/eda-mcp/ 到目标电脑后创建 .env 即可运行
16. 使用 SSE 传输模式（支持 /ui /health /chat /tools/list 自定义路由）
17. 控制台启动时显示 gRPC 50055 端口状态
18. 打包时自动过滤 LLM_API_KEY 等敏感配置，强制 MCP_TRANSPORT=sse
19. ANSYS COM 支持多 ProgID 回退（AnsoftHfss.HfssScriptInterface / Ansoft.ElectronicsDesktop）
20. AEDT 工程锁文件管理：打开前检查/清理失效锁，关闭后安全删除，PID 活跃时绝不删除
21. `/tools/list` 端点返回工具列表，`chat_client.html` 动态加载 23 个工具面板
22. EXE 使用 `exclude_binaries=True`，DLL/Pyd 统一放 `_internal/`，不再重复打包（预计减 45~50 MB）
23. `matplotlib.use("Agg")` 必须在 `import matplotlib.pyplot` 之前调用，否则 GUI 后端被意外加载
24. UPX 压缩已关闭（某些原生 DLL 压缩后兼容性问题），目录模式依赖 `_internal/` 不可单独分发 EXE
25. 构建脚本增加体积阈值检查：目录 > 105 MB 或 ZIP > 80 MB 视为失败，EXE > 15 MB 告警重复打包
26. Pillow AVIF/WebP 编码器已排除（节省约 7~8 MB），需通过 .spec excludes 控制，不可手动删除文件

## 维护人

- 负责人：--
- 更新时间：2026-07-24
