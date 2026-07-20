# EDA MCP 服务

将 EDA-PMDS/EDI 的 gRPC 接口和本地命令行工具封装为 MCP 服务，
支持 **stdio** 和 **Streamable HTTP** 两种传输方式，
使 AI 客户端能通过自然语言操作 EDA 工程。

## 可用工具（5 个）

| 工具 | 功能 | 关键参数 |
|---|---|---|
| `open_eda_project` | 打开 .epp 工程 | `project_path`, `timeout_seconds` |
| `view_project_netlist` | 查看/导出工程网表 | `project_path`, `timeout_seconds` |
| `simulate_project` | 执行工程仿真 | `project_path`, `log_source`, `timeout_seconds` |
| `launch_edi` | 启动 EDI 客户端（等待 gRPC 就绪） | `edi_path`（可选）, `wait_for_grpc` |
| `turbocharts_convert` | ADS RAW → 曲线图 + CSV | `raw_path`, `img_path`, `chart_type` |

## 项目结构

```
├── proto/                         # protobuf 协议文件
│   ├── ecserver.proto             # gRPC 服务定义
│   ├── ecserver_pb2.py            # 生成的 Python 消息类
│   └── ecserver_pb2_grpc.py       # 生成的 Python gRPC 客户端
├── servers/                       # MCP 服务模块
│   ├── registry_server.py         # 工具注册中心（加工具只改这个）
│   ├── eda/
│   │   ├── server.py              # EDA gRPC 工具（4 个）
│   │   └── grpc_client.py         # gRPC 通信层
│   └── turbocharts/
│       └── server.py              # RawConverter 工具（1 个）
├── start_servers.py               # 一键启动入口
├── .mcp.json                      # Claude Code 配置
├── .env                           # 环境变量（唯一配置来源）
├── pyproject.toml                 # uv 项目配置
│
├── README.md                      # 本文档
├── HANDOVER.md                    # 交接文档（架构、扩展）
├── MCP使用说明.md                  # 中文快速参考
└── EDI系统接口与外部调用汇总.md     # EDI 接口全量文档
```

## 安装

```powershell
uv sync
```

## 前置条件

1. EDA-PMDS/EDI 的 `ExternalCall` gRPC 服务可用（默认 `127.0.0.1:50055`）
2. `.epp` 工程文件存在
3. turbocharts 功能需要 `turbocharts_app.exe`

验证 gRPC 端口：

```powershell
netstat -ano | findstr 50055
```

## 配置

所有配置集中在 `.env` 文件：

```ini
EDA_GRPC_SERVER=127.0.0.1:50055
EDI_PATH=C:\Program Files (x86)\EDI\EDI.exe
TURBOCHARTS_PATH=C:\Program Files (x86)\EDI\turbocharts_app.exe
MCP_TRANSPORT=streamable-http
MCP_HOST=127.0.0.1
MCP_PORT=8000
```

## 启动

### 一键启动（推荐）

```powershell
cd D:\GitLabCode\mcp-grpc

# Streamable HTTP 模式（OpenClaw / Web 客户端）
uv run python start_servers.py

# stdio 模式（Claude Code / VS Code）
uv run python start_servers.py --transport stdio

# 自定义端口
uv run python start_servers.py --port 9000
```

### Claude Code

`.mcp.json` 已配置，`/mcp` 重载即生效。

### OpenClaw / Web 客户端

启动后配置：

| 字段 | 值 |
|---|---|
| 名称 | `eda` |
| 传输方式 | Streamable HTTP |
| URL | `http://127.0.0.1:8000/mcp` |

### 其他 MCP 客户端

```json
{
  "mcpServers": {
    "eda": {
      "command": "uv",
      "args": [
        "--directory", "D:/GitLabCode/mcp-grpc",
        "run", "python", "start_servers.py",
        "--transport", "stdio"
      ],
      "env": {
        "EDA_GRPC_SERVER": "127.0.0.1:50055"
      }
    }
  }
}
```

## 使用示例

```
帮我启动 EDI
帮我打开 EDA 工程 C:\Users\JGL\EDI-Workspace\EDI_TEST\EDI_TEST.epp
帮我查看这个工程的网表
帮我对这个工程执行仿真
帮我把 result_tr.raw 转成 S 参数增益曲线图，输出 gain.png，曲线 DB_S[2,1]，依赖轴 freq
```

## 开发

### 添加新工具

EDA gRPC 工具：在 `servers/eda/server.py` 中按模板添加 `@mcp.tool()` 函数，调用 `call_grpc()`。<br>
本地工具：在 `servers/` 下新建子包，创建 `server.py`。<br>
最后在 `servers/registry_server.py` 中 import 并注册。

### 重新生成 proto

```powershell
python -m grpc_tools.protoc -I proto --python_out=proto --grpc_python_out=proto proto/ecserver.proto
# 编辑 proto/ecserver_pb2_grpc.py 第 5 行：
# import ecserver_pb2 → from proto import ecserver_pb2
```

### 详细文档

- [交接文档](./HANDOVER.md) — 架构、技术栈、通信流程、已知问题
- [使用说明](./MCP使用说明.md) — 工具参数表、客户端配置模板
- [接口汇总](proto/EDI系统接口与外部调用汇总.md) — EDI 全量接口文档