# EDA MCP 使用说明

## 当前工具（5 个）

| 工具 | 说明 | 必填参数 | 可选参数 |
|---|---|---|---|
| `open_eda_project` | 打开 .epp 工程 | `project_path` | `timeout_seconds`（1-600，默认 60） |
| `view_project_netlist` | 查看工程网表 | `project_path` | `timeout_seconds`（1-600，默认 60） |
| `simulate_project` | 执行工程仿真 | `project_path` | `log_source`, `timeout_seconds`（默认 120） |
| `launch_edi` | 启动 EDI 客户端 | 无 | `edi_path`, `wait_for_grpc`, `wait_timeout` |
| `turbocharts_convert` | RAW 转曲线图 | `raw_path`, `img_path`, `chart_type` | `csv_path`, `linename`, `dependency`, `ac_config` |

## 1. 安装依赖

```powershell
uv sync
```

## 2. 前置条件

- EDA-PMDS/EDI 的 `ExternalCall` gRPC 服务可用
- 默认地址 `127.0.0.1:50055`，可修改 `.env` 中的 `EDA_GRPC_SERVER`

## 3. 配置（.env）

```
EDA_GRPC_SERVER    = "127.0.0.1:50055"
EDI_PATH           = "C:\\Program Files (x86)\\EDI\\EDI.exe"
TURBOCHARTS_PATH   = "C:\\Program Files (x86)\\EDI\\turbocharts_app.exe"
MCP_TRANSPORT      = "streamable-http"
```

## 4. 启动服务

### 一键启动（推荐）

```powershell
cd D:\GitLabCode\mcp-grpc
uv run python start_servers.py
```

服务在 `http://127.0.0.1:8000` 启动，MCP 端点 `/mcp`。

### Claude Code

`.mcp.json` 已配置，`/mcp` 重载即生效。

## 5. 客户端配置

### Claude Code

项目根目录 `.mcp.json` 已配置，自动生效。

### OpenClaw

| 名称 | 传输方式 | URL |
|---|---|---|
| `eda` | Streamable HTTP | `http://127.0.0.1:8000/mcp` |

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

## 6. 工具使用示例

### open_eda_project / view_project_netlist / simulate_project

```
帮我打开 EDA 工程 C:\Users\JGL\EDI-Workspace\EDI_TEST\EDI_TEST.epp
帮我查看这个工程的网表
帮我仿真这个工程
```

### launch_edi

```
帮我启动 EDI
```

### turbocharts_convert

```
帮我把 D:\results\result.raw 转成 S 参数增益曲线图，
输出到 D:\results\gain.png，曲线选 DB_S[2,1]，依赖轴 freq
```

## 7. 注意事项

- `project_path` 必须是存在的 `.epp` 文件
- `timeout_seconds` 范围 1-600
- stdio 模式下不要向 stdout 输出调试信息
- `.env` 中的配置在服务启动时自动加载
