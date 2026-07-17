# EDA MCP 服务

通过 EDA-PMDS/EDI 的 gRPC 接口和本地工具操作 EDA 工程，
支持 **stdio** 和 **Streamable HTTP** 两种传输方式。

## 可用工具（5 个）

| 工具 | 功能 | 关键参数 |
|---|---|---|
| `open_eda_project` | 打开 .epp 工程 | `project_path`, `timeout_seconds` |
| `view_project_netlist` | 查看工程网表 | `project_path`, `timeout_seconds` |
| `simulate_project` | 执行工程仿真 | `project_path`, `log_source`, `timeout_seconds` |
| `launch_edi` | 启动 EDI 客户端（等待 gRPC 就绪） | `edi_path`（可选）, `wait_for_grpc` |
| `turbocharts_convert` | ADS RAW → 曲线图 + CSV | `raw_path`, `img_path`, `chart_type`, … |

## 项目结构

```
├── proto/                     # protobuf 生成文件
│   ├── ecserver.proto
│   ├── ecserver_pb2.py
│   └── ecserver_pb2_grpc.py
├── servers/                   # MCP 服务模块
│   ├── shared/config.py       # 统一配置（.env 加载）
│   ├── eda/
│   │   ├── server.py          # EDA gRPC 工具
│   │   └── grpc_client.py     # gRPC 通信层
│   └── turbocharts/
│       └── server.py          # turbocharts 工具
├── start_servers.py           # 一键启动（统一入口）
├── .mcp.json                  # Claude Code 配置
├── .env                       # 环境变量
└── pyproject.toml
```

## 安装

```powershell
uv sync
```

## 前置条件

1. EDA gRPC 服务运行中（默认 `127.0.0.1:50055`）
2. `.epp` 工程文件存在
3. turbocharts 功能需要 `turbocharts_app.exe`

验证 gRPC 端口：

```powershell
netstat -ano | findstr 50055
```

## 配置（.env）

```
EDA_GRPC_SERVER    = "127.0.0.1:50055"                           # gRPC 地址
EDI_PATH           = "C:\\Program Files (x86)\\EDI\\EDI.exe"     # EDI 客户端
TURBOCHARTS_PATH   = "C:\\Program Files (x86)\\EDI\\turbocharts_app.exe"
MCP_TRANSPORT      = "streamable-http"                           # stdio / streamable-http
```

## 启动

### 一键启动（推荐）

```powershell
# Streamable HTTP 模式（OpenClaw / Web 客户端）
uv run python start_servers.py

# stdio 模式（Claude Code / VS Code）
uv run python start_servers.py --transport stdio

# 自定义端口
uv run python start_servers.py --port 9000
```

### Claude Code

`.mcp.json` 已配置，`/mcp` 重载即生效，无需手动启动。

### OpenClaw

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
帮我把 result.raw 转成 S 参数增益曲线图，输出到 gain.png
```

## 开发

### 重新生成 proto

```powershell
python -m grpc_tools.protoc -I proto --python_out=proto --grpc_python_out=proto proto/ecserver.proto
```

生成后编辑 `proto/ecserver_pb2_grpc.py`，将第 5 行的 `import ecserver_pb2` 改为 `from proto import ecserver_pb2`，避免与 grpcio 包名冲突。
