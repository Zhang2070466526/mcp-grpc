# EDA MCP 项目交接文档

## 项目概述

将 EDA-PMDS/EDI 的 gRPC 接口和本地命令行工具封装为 MCP 服务，
使 AI 客户端（Claude Code、OpenClaw 等）能通过自然语言操作 EDA 工程。

## 代码仓库

```
D:\GitLabCode\mcp-grpc
```

## 目录结构

```
├── proto/                          # protobuf 协议文件
│   ├── ecserver.proto              # gRPC 服务定义（原始协议）
│   ├── ecserver_pb2.py             # protoc 生成的 Python 消息类
│   └── ecserver_pb2_grpc.py        # protoc 生成的 Python gRPC 客户端
│
├── servers/                        # MCP 服务模块
│   ├── __init__.py
│   ├── registry_server.py          # 工具注册中心（加工具只改这个）
│   ├── eda/
│   │   ├── __init__.py              # 公共 API + 工具清单文档
│   │   ├── config.py                # 配置 + ProjectReader + S-expression 解析器
│   │   ├── grpc_client.py           # gRPC 通信层
│   │   ├── project_manage.py        # 工程管理（6 个工具）
│   │   ├── simulation.py             # 仿真（2 个工具）
│   │   ├── design_export.py          # 网表/截图（2 个工具）
│   │   ├── model_replace.py          # 模型替换（1 个工具）
│   │   ├── edi_launcher.py          # 启动 EDI（1 个工具）
│   │   └── project_inspection.py    # 仿真对比（1 个工具）
│   └── turbocharts/
│       ├── __init__.py
│       ├── runner.py                # 串行执行器（BoundedSemaphore）
│       └── server.py                # RawConverter 工具定义（1 个工具）
│
├── start_servers.py                # 一键启动入口
├── tests/                          # 测试套件
├── scripts/                        # 打包脚本 + PyInstaller 配置
├── .mcp.json                       # Claude Code 配置
├── .env                            # 环境变量（不提交 Git）
├── pyproject.toml                  # uv 项目配置
│
├── README.md                       # 项目主文档（含工具参数和曲线参考）
├── HANDOVER.md                     # 本文档（交接文档）
├── EDI系统接口与外部调用汇总.md      # EDI 接口全量文档（不动）
│
└── servers/turbocharts/
    └── RAW 转图像工具使用说明.txt    # RawConverter 参考文档
```

## 技术栈

| 层级 | 技术 | 用途 |
|---|---|---|
| 语言 | Python 3.12+ | — |
| 包管理 | uv | 依赖安装、虚拟环境 |
| MCP 框架 | mcp >= 1.0.0 (FastMCP) | MCP 服务定义与通信 |
| gRPC | grpcio >= 1.81.0 | EDA 服务通信 |
| 序列化 | protobuf >= 6.33.5 | gRPC 消息序列化 |
| 环境管理 | python-dotenv | .env 文件加载 |

## MCP 工具清单（14 个）

| 工具 | 所属模块 | 底层协议 | 功能 |
|---|---|---|---|
| `list_epp_projects` | servers/eda | 本地 filesystem | 扫描文件夹中的 .epp 工程 |
| `open_eda_project` | servers/eda | gRPC OPEN_PROJECT | 打开 .epp 工程 |
| `close_eda_project` | servers/eda | gRPC CLOSE_PROJECT | 关闭工程 |
| `list_project_components` | servers/eda | 本地 project_reader | 列出工程中的元件 |
| `get_component_parameters` | servers/eda | 本地 project_reader | 查询元件的完整参数 |
| `get_project_summary` | servers/eda | 本地 project_reader | 工程概览 |
| `simulate_project` | servers/eda | gRPC SIMULATE_PROJECT | 执行仿真 |
| `simulate_netlist_with_ads` | servers/eda | gRPC CALL_SIMULATION_CONTROLLER | 调用 ADS 仿真控制器 |
| `compare_simulation_results` | servers/eda | 本地 turbocharts | 多 RAW 结果对比叠图 |
| `export_project_netlist` | servers/eda | gRPC VIEW_PROJECT_NETLIST | 导出网表文件 |
| `capture_schematic` | servers/eda | gRPC CAPTURE_SCHEMATIC | 截取原理图 |
| `replace_models_from_csv` | servers/eda | gRPC MODEL_REPLACE | 按 CSV 批量替换模型 |
| `launch_edi` | servers/eda | 本地 subprocess | 启动 EDI 客户端 |
| `turbocharts_convert` | servers/turbocharts | 本地 subprocess | RAW 转曲线图+CSV |

## 配置说明

每台电脑独立配置 `.env`，所有服务均为本机调用：

```
EDA_GRPC_SERVER=127.0.0.1:50055       # 本机 EDI gRPC（始终本机）
EDI_PATH=C:\Program Files (x86)\EDI\EDI.exe
TURBOCHARTS_PATH=C:\Program Files (x86)\EDI\turbocharts_app.exe
MCP_TRANSPORT=streamable-http         # HTTP 模式（多客户端共享）
MCP_HOST=127.0.0.1                    # 仅本机监听
MCP_PORT=8000
```

当前版本为 **本地 MCP 模式**：服务、文件、EDI 均在同一台电脑，
不同电脑互不影响，无需公共服务或远程 Agent。

## 启动方式

### 生产环境：一键启动

```powershell
cd D:\GitLabCode\mcp-grpc
uv run python start_servers.py
```

### Claude Code：自动管理

`.mcp.json` 已配置，客户端自动拉起。

### 单独启动某个服务模块（开发调试用）

```powershell
cd D:\GitLabCode\mcp-grpc
uv run python servers/turbocharts/server.py
```
> 注：EDA gRPC 工具已移除独立入口，统一通过 `start_servers.py` 启动。

## 通信流程

### gRPC 工具（open_eda_project 等）

```
AI 客户端 → MCP 工具 → grpc_client.call_grpc()
                      → PerformAction (提交任务)
                      → FetchEvent (轮询事件流)
                      → 返回结果
```

### 本地工具（launch_edi、turbocharts_convert）

```
AI 客户端 → MCP 工具 → subprocess.Popen/run()
                      → 返回执行结果
```

## 扩展开发

### 添加新的 gRPC 工具

1. 在 `servers/eda/` 对应的 service 文件中添加工具函数（纯函数，不加装饰器）
2. 在 `servers/eda/__init__.py` 中 re-export
3. 在 `servers/registry_server.py` 中 import 并调用 `mcp.tool()(func)` 注册

### 添加新的本地工具

1. 在 `servers/` 下新建子包（参考 turbocharts 结构）
2. 在 `servers/registry_server.py` 中 import 并注册

### 重新生成 proto

```powershell
python -m grpc_tools.protoc -I proto --python_out=proto --grpc_python_out=proto proto/ecserver.proto
# 然后编辑 proto/ecserver_pb2_grpc.py 第 5 行：
# import ecserver_pb2 → from proto import ecserver_pb2
```

## 测试

Windows PowerShell
°æȨËùÓУ¨C£© Microsoft Corporation¡£±£ÁôËùÓÐȨÀû¡£

°²װ×îÐµÄ PowerShell£¬Á˽âÐ¹¦Äܺ͸Ľø£¡https://aka.ms/PSWindows

PS D:\GitLabCode\mcp-grpc> test_project_reader.py: all passed
test_component_tools.py: all passed
test_turbocharts_runner.py: all passed
test_health.py: all passed
test_tool_registry.py: all passed

## 打包

Windows PowerShell
°æȨËùÓУ¨C£© Microsoft Corporation¡£±£ÁôËùÓÐȨÀû¡£

°²װ×îÐµÄ PowerShell£¬Á˽âÐ¹¦Äܺ͸Ľø£¡https://aka.ms/PSWindows

PS D:\GitLabCode\mcp-grpc> === EDA MCP Build ===
[1/4] Cleaning...
[2/4] Running tests...
All passed
[3/4] Building with PyInstaller...
[4/4] Verifying...
OK: dist/EDA MCP/eda-mcp.exe (48.9 MB)

## 工具注册机制## 工具注册机制

所有工具函数为纯函数（无 MCP 装饰器），定义在 `servers/eda/*.py` 中，
由 `servers/registry_server.py` 统一导入并注册到 FastMCP 实例。
`servers/eda/__init__.py` 作为公共 API 入口，re-export 所有工具函数。

```
servers/eda/project_manage.py   定义工具函数（纯函数）
       │
       ▼
servers/eda/__init__.py         re-export 到包级别
       │
       ▼
servers/registry_server.py       mcp.tool()(func) 注册 + 创建 FastMCP
       │
       ▼
start_servers.py                 解析参数、启动服务
```

## 待封装接口

所有 proto EventType 已全部封装完毕。

## 已知问题与注意事项

1. 本地 proto 目录名为 `proto`，避免与 grpcio 包名冲突
2. stdio 模式下不能向 stdout 输出任何内容（会破坏 MCP 协议）
3. `.env` 通过 `python-dotenv` 加载，在所有 service 模块首次 import 时生效
4. Windows 路径中的反斜杠在 `.env` 中不需要转义
5. gRPC 服务地址格式必须为 `host:port`（launch_edi 依赖 rsplit(":", 1)）
6. gRPC 超时无上限限制（仅校验 > 0），仿真等长任务可传任意大值
7. 端口占用时使用 `netstat -ano | findstr <端口>` 定位后 `taskkill -f -pid <PID>` 关闭
8. `launch_edi` 返回 `success`（gRPC 就绪时才为 True）、`process_started`、`grpc_ready` 三个字段，调用方应检查 `success` 而非仅看 `process_started`
9. `grpc_client.py` 从 `config.py` 统一导入 `EDA_GRPC_SERVER`，不再独立读取环境变量
10. `.gitignore` 已排除 `.idea/`、`.claude/`，不要提交个人 IDE 配置
11. `start_servers.py` 使用 `mcp._tool_manager._tools` 读取工具列表（私有属性），MCP 版本升级后需验证兼容性
12. `servers/agent/` 为实验性分布式原型，不纳入当前正式版本
13. Windows HTTP 模式使用 SelectorEventLoop 避免 Proactor AcceptEx 异常（WinError 64）
14. `/health` 端点可检测 MCP 服务与 EDI gRPC 的连接状态
15. `compare_simulation_results` 使用 Matplotlib 生成叠图，依赖 numpy 做插值对齐

## 维护人

- 负责人：—
- 更新时间：2026-07-20