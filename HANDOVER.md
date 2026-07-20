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
│   ├── eda/
│   │   ├── __init__.py
│   │   ├── server.py               # EDA gRPC 工具定义（4 个工具）
│   │   └── grpc_client.py          # gRPC 通信层封装
│   └── turbocharts/
│       ├── __init__.py
│       └── server.py               # RawConverter 工具定义（1 个工具）
│
├── start_servers.py                # 一键启动入口（合并所有工具）
├── .mcp.json                       # Claude Code MCP 配置
├── .env                            # 环境变量配置（唯一配置来源）
├── pyproject.toml                  # uv 项目配置
│
├── README_MCP.md                   # 项目主文档
├── MCP使用说明.md                   # 中文快速参考
├── HANDOVER.md                     # 本文档（交接文档）
├── EDI系统接口与外部调用汇总.md      # EDI 接口全量文档（不动）
├── grpc接口调用.md                  # gRPC 调用说明
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

## MCP 工具清单（5 个）

| 工具 | 所属模块 | 底层协议 | 功能 |
|---|---|---|---|
| `open_eda_project` | servers/eda | gRPC OPEN_PROJECT | 打开 .epp 工程 |
| `view_project_netlist` | servers/eda | gRPC VIEW_PROJECT_NETLIST | 导出网表文件 |
| `simulate_project` | servers/eda | gRPC SIMULATE_PROJECT | 执行仿真 |
| `launch_edi` | servers/eda | 本地 subprocess | 启动 EDI 客户端 |
| `turbocharts_convert` | servers/turbocharts | 本地 subprocess | RAW 转曲线图+CSV |

## 配置说明

所有配置集中在 `.env`：

```
EDA_GRPC_SERVER=127.0.0.1:50055       # gRPC 地址
EDI_PATH=C:\Program Files (x86)\EDI\EDI.exe
TURBOCHARTS_PATH=C:\Program Files (x86)\EDI\turbocharts_app.exe
MCP_TRANSPORT=streamable-http         # stdio | streamable-http
MCP_HOST=127.0.0.1                    # HTTP 监听地址
MCP_PORT=8000                         # HTTP 监听端口
```

## 启动方式

### 生产环境：一键启动

```powershell
cd D:\GitLabCode\mcp-grpc
uv run python start_servers.py
```

### Claude Code：自动管理

`.mcp.json` 已配置，客户端自动拉起。

### 单独启动某个服务

```powershell
uv run python servers/eda/server.py
uv run python servers/turbocharts/server.py
```

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

1. 在 `servers/eda/server.py` 中复制现有工具模板
2. 将 `ecserver_pb2.XXX` 替换为新的事件类型
3. 构造对应的 `payload_json`
4. 在 `start_servers.py` 中 import 并注册

### 添加新的本地工具

1. 在 `servers/` 下新建子包
2. 创建 `server.py`，参考 `turbocharts/server.py`
3. 在 `start_servers.py` 中 import 并注册

### 重新生成 proto

```powershell
python -m grpc_tools.protoc -I proto --python_out=proto --grpc_python_out=proto proto/ecserver.proto
# 然后编辑 proto/ecserver_pb2_grpc.py 第 5 行：
# import ecserver_pb2 → from proto import ecserver_pb2
```

## 待封装接口

| EventType | 值 | 功能 | 状态 |
|---|---|---|---|
| MODEL_REPLACE | 6 | CSV 模型替换 | 待封装 |
| CAPTURE_SCHEMATIC | 7 | 原理图截图 | 待封装 |
| CLOSE_PROJECT | 8 | 关闭工程 | 待封装 |
| CALL_SIMULATION_CONTROLLER | 9 | 调用仿真控制器 | 待封装 |

## 已知问题与注意事项

1. 本地 proto 目录名为 `proto`，避免与 grpcio 包名冲突
2. stdio 模式下不能向 stdout 输出任何内容（会破坏 MCP 协议）
3. `.env` 通过 `python-dotenv` 加载，只在首次 import 时生效
4. Windows 路径中的反斜杠在 `.env` 中不需要转义
5. gRPC 服务地址格式必须为 `host:port`（launch_edi 依赖 rsplit(":", 1)）

## 维护人

- 负责人：—
- 更新时间：2026-07-17