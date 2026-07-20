# EDA MCP 使用说明

## 工具总览（5 个）

### EDA gRPC 工具

| 工具 | 说明 | 必填参数 | 可选参数 |
|---|---|---|---|
| `open_eda_project` | 打开 .epp 工程 | `project_path` | `timeout_seconds`（1-600，默认 60） |
| `view_project_netlist` | 查看工程网表 | `project_path` | `timeout_seconds`（1-600，默认 60） |
| `simulate_project` | 执行工程仿真 | `project_path` | `log_source`、`timeout_seconds`（默认 120） |
| `launch_edi` | 启动 EDI 客户端 | 无 | `edi_path`、`wait_for_grpc`、`wait_timeout` |

### RawConverter 工具

| 工具 | 说明 | 必填参数 | 可选参数 |
|---|---|---|---|
| `turbocharts_convert` | RAW 转曲线图+CSV | `raw_path`、`img_path`、`chart_type` | `csv_path`、`linename`、`dependency`、`ac_config` |

---

## 1. 安装与配置

### 安装

```powershell
uv sync
```

### 配置（.env）

```ini
EDA_GRPC_SERVER=127.0.0.1:50055
EDI_PATH=C:\Program Files (x86)\EDI\EDI.exe
TURBOCHARTS_PATH=C:\Program Files (x86)\EDI\turbocharts_app.exe
MCP_TRANSPORT=streamable-http
MCP_HOST=127.0.0.1
MCP_PORT=8000
```

### 前置条件

- EDA gRPC 服务可用（`netstat -ano | findstr 50055`）
- `.epp` 工程文件存在
- turbocharts 需要 `turbocharts_app.exe` 或 `RawConverter`

---

## 2. 启动服务

### 一键启动

```powershell
cd D:\GitLabCode\mcp-grpc
uv run python start_servers.py
```

### Claude Code

`.mcp.json` 已配置，`/mcp` 重载即生效。

---

## 3. 客户端配置

### Claude Code

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
      "env": { "EDA_GRPC_SERVER": "127.0.0.1:50055" }
    }
  }
}
```

### OpenClaw

| 字段 | 值 |
|---|---|
| 名称 | `eda` |
| 传输方式 | Streamable HTTP |
| URL | `http://127.0.0.1:8000/mcp` |

---

## 4. 工具详细说明

### open_eda_project — 打开工程

```json
{
  "project_path": "C:/Users/JGL/EDI-Workspace/EDI_TEST/EDI_TEST.epp",
  "timeout_seconds": 60
}
```

自然语言：`帮我打开 EDA 工程 C:\...\EDI_TEST.epp`

### view_project_netlist — 查看网表

```json
{
  "project_path": "C:/Users/JGL/EDI-Workspace/EDI_TEST/EDI_TEST.epp"
}
```

返回 `details.netlist_path` 包含网表文件路径。

### simulate_project — 执行仿真

```json
{
  "project_path": "C:/Users/JGL/EDI-Workspace/EDI_TEST/EDI_TEST.epp",
  "log_source": "mcp_client",
  "timeout_seconds": 120
}
```

### launch_edi — 启动 EDI 客户端

自动检查 gRPC 是否已在运行，避免重复启动。

```json
{
  "edi_path": "",
  "wait_for_grpc": true,
  "wait_timeout": 30
}
```

### turbocharts_convert — RAW 转图像

**chart_type**：`SP`（S参数）、`HB`（谐波平衡）、`XDB`

**linename 格式**：`单位_曲线名[端口]`，多条用 `&` 分隔

| 曲线 | 说明 |
|---|---|
| `DB_S[2,1]` | S参数输出增益 |
| `DB_S[1,2]` | S参数反向增益 |
| `real_nf(1)` | 噪声系数 |
| `VSWR_S[1,1]` | 输入驻波 |
| `real_delayS[2,1]` | 群时延 |
| `APS_S[2,1]` | 数控衰减器附加相移 |
| `MAS_S[2,1]` | 数控移相器衰减态 |
| `MV_S[2,1]` | 数控移相器幅度波动 |
| `PSS_S[2,1]` | 数控移相器移相态 |

**ac_config 格式**：`ac_type#bit#data#nv_type#nv_value`

```
ac_type: phase（相位精度）或 att（衰减精度）
bit:     精度位数
data:    曲线名称
nv_type: fv（固定间隔）或 cl（完整列表）
nv_value: 间隔值或逗号分隔的值列表
```

示例：
```json
{
  "raw_path": "D:/results/result_tr.raw",
  "img_path": "D:/results/gain.png",
  "chart_type": "SP",
  "linename": "DB_S[2,1]",
  "dependency": "freq"
}
```

---

## 5. 注意事项

- `project_path` 必须是存在的 `.epp` 文件
- `timeout_seconds` 范围 1-600
- stdio 模式下不要向 stdout 输出调试信息
- `.env` 配置在服务启动时自动加载
- 详细架构和扩展开发见 [交接文档](./HANDOVER.md)
