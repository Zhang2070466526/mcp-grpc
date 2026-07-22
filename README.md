# EDA MCP 服务

每台安装 EDI 的电脑运行一个本地 MCP 服务，将 EDA-PMDS/EDI 的 gRPC 接口和命令行工具封装为 14 个 MCP 工具，
支持 **Streamable HTTP** 和 **stdio** 两种传输方式，使 AI 客户端能通过自然语言操作 EDA 工程。

---

## 快速开始

### 1. 安装

```powershell
uv sync
```

### 2. 配置 `.env`

```ini
EDA_GRPC_SERVER=127.0.0.1:50055
EDI_PATH=C:\Program Files (x86)\EDI\EDI.exe
TURBOCHARTS_PATH=C:\Program Files (x86)\EDI\turbocharts_app.exe
MCP_TRANSPORT=sse
MCP_HOST=127.0.0.1
MCP_PORT=8026

# 以下可选，用于聊天客户端 AI 对话
LLM_API_KEY=sk-xxx
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat
```

### 3. 前置条件

- EDA gRPC 服务可用：`netstat -ano | findstr 50055`
- `.epp` 工程文件存在
- Turbocharts 功能需要 `turbocharts_app.exe`

### 4. 启动

**HTTP 模式（推荐）** — 多个本地客户端共享一个进程：

```powershell
cd D:\GitLabCode\mcp-grpc
uv run python start_servers.py
```

输出示例：
```
MCP 服务启动 [transport=sse, port=8026]
已加载 14 个工具: list_epp_projects, open_eda_project, ...
地址: http://127.0.0.1:8026/sse
INFO:     Uvicorn running on http://127.0.0.1:8026
```

启动后自动监听 `127.0.0.1:8026`：
- 所有本机客户端通过 `http://127.0.0.1:8026/sse` 连接
- EDI gRPC 操作由全局锁保证串行
- Turbocharts 由信号量保证同一时间一个进程
- `/health` 健康检查 — 返回 EDA gRPC 和 Turbocharts 状态
- `/ui` 聊天客户端 — 自然语言驱动 14 个工具，带工具面板和系统主题
- `/chat` 聊天 API — POST `{"message":"..."}` 返回 LLM + 工具执行结果
- 聊天客户端文件：`scripts/chat_client.html`（独立 HTML，可单独分发）

**stdio 模式** — 由 MCP 客户端管理进程生命周期，适合单客户端调试：

```powershell
uv run python start_servers.py --transport stdio
```

> stdio 模式下不能向 stdout 输出任何内容（MCP 协议通道），进程由客户端自动启停。

**自定义端口**：
```powershell
uv run python start_servers.py --port 9000
```

---

## 客户端配置

每台电脑的 `127.0.0.1` 都指向自己，服务和文件都在本机。

| 客户端 | 配置 |
|---|---|
| Claude Code | `.mcp.json` 已配置，`/sse` 重载 |
| OpenClaw / Web | 名称 `eda`，Streamable HTTP，`http://127.0.0.1:8026/sse` |
| 其他 stdio 客户端 | `uv --directory D:/GitLabCode/sse-grpc run python start_servers.py --transport stdio` |

其他 MCP 客户端通用配置：

```json
{
  "mcpServers": {
    "eda": {
      "command": "uv",
      "args": ["--directory", "D:/GitLabCode/sse-grpc", "run", "python", "start_servers.py", "--transport", "stdio"],
      "env": { "EDA_GRPC_SERVER": "127.0.0.1:50055" }
    }
  }
}
```

---

## 工具参考（14 个）

### 工程管理

| 工具 | 说明 | 参数 |
|---|---|---|
| `list_epp_projects` | 扫描文件夹中的 .epp 工程 | `folder_path` |
| `open_eda_project` | 打开 .epp 工程 | `project_path`, `timeout_seconds`（默认 60） |
| `close_eda_project` | 关闭工程 | `project_path`, `need_save`（默认 false） |
| `list_project_components` | 列出工程中所有元件 | `project_path`, `schematic_name`, `component_type`, `name_contains` |
| `get_component_parameters` | 查询单个元件的全部参数 | `project_path`, `component_id`, `schematic_name`, `include_hidden` |
| `get_project_summary` | 工程概览（元数据/原理图/仿真） | `project_path`, `include_component_types`, `include_latest_result` |

### 仿真

| 工具 | 说明 | 参数 |
|---|---|---|
| `simulate_project` | 执行工程仿真 | `project_path`, `log_source`, `timeout_seconds`（默认 600，无上限） |
| `simulate_netlist_with_ads` | 调用 ADS 仿真控制器 | `netlist_path`, `ads_path`, `timeout_seconds`（默认 120） |
| `compare_simulation_results` | 多 RAW 同曲线对比叠图 | `result_paths`, `curve`, `img_path`, `chart_type`, `labels`, `dependency` |

### 导出与分析

| 工具 | 说明 | 参数 |
|---|---|---|
| `export_project_netlist` | 查看/导出工程网表 | `project_path`, `timeout_seconds`（默认 60） |
| `capture_schematic` | 截取原理图为图片 | `project_path`, `img_path`, `timeout_seconds`（默认 60） |

### 模型与启动

| 工具 | 说明 | 参数 |
|---|---|---|
| `replace_models_from_csv` | 按 CSV 批量替换模型 | `project_path`, `csv_path`, `timeout_seconds`（默认 60） |
| `launch_edi` | 启动 EDI 客户端，等待 gRPC 就绪 | `edi_path`, `wait_for_grpc`（默认 true）, `wait_timeout` |

### 图表

| 工具 | 说明 | 参数 |
|---|---|---|
| `turbocharts_convert` | ADS RAW → 曲线图 + CSV | `raw_path`, `img_path`, `chart_type`, `csv_path`, `linename`, `dependency`, `ac_config` |

自然语言调用示例：

```
帮我看看 C:/.../EDI-Workspace 下面有哪些 .epp 工程
帮我打开 EDA 工程 C:/.../EDI_TEST.epp
帮我查看这个工程的网表
帮我看看这个工程有哪些元件
帮我对这个工程执行仿真
帮我把 result_tr.raw 转成 S 参数增益曲线图，输出 gain.png，曲线 DB_S[2,1]，依赖轴 freq
```

### turbocharts_convert 参数详解

**linename** — `单位_曲线名[端口]`，多条用 `&` 分隔：

| DB_S[2,1]（增益） | DB_S[1,2]（反向增益） | real_nf(1)（噪声） | VSWR_S[1,1]（驻波） | real_delayS[2,1]（时延） |
|---|---|---|---|---|
| APS_S[2,1]（附加相移） | MAS_S[2,1]（衰减态） | MV_S[2,1]（幅度波动） | PSS_S[2,1]（移相态） | |

**chart_type**：`SP` / `HB` / `XDB`

**ac_config** — `ac_type#bit#data#nv_type#nv_value`：

| 段 | 含义 | 例 |
|---|---|---|
| ac_type | `phase`（相位）或 `att`（衰减） | `phase` |
| bit | 精度位数 | `3` |
| data | 曲线名 | `S[2,1]` |
| nv_type | `fv`（固定间隔）或 `cl`（完整列表） | `fv` |
| nv_value | 间隔值或逗号分隔的值列表 | `0.1` |

---

## 项目结构

```
├── proto/                       # protobuf
│   ├── ecserver.proto
│   ├── ecserver_pb2.py
│   └── ecserver_pb2_grpc.py
├── servers/
│   ├── registry_server.py       # 工具注册中心
│   ├── eda/
│   │   ├── config.py            # 配置 + ProjectReader + S-expression 解析器
│   │   ├── grpc_client.py       # gRPC 通信（带 EDA 全局锁）
│   │   ├── project_manage.py    # 工程管理（6 工具）
│   │   ├── simulation.py        # 仿真（2 工具）
│   │   ├── design_export.py     # 网表/截图（2 工具）
│   │   ├── model_replace.py     # 模型替换（1 工具）
│   │   ├── edi_launcher.py      # 启动 EDI（1 工具）
│   │   └── project_inspection.py # 仿真对比（1 工具）
│   └── turbocharts/
│       ├── runner.py            # 串行执行器
│       └── server.py            # RAW 转图（1 工具）
├── start_servers.py             # 入口
├── tests/                       # 测试套件
├── scripts/
│   ├── build.ps1                 # 打包脚本
│   └── eda_mcp.spec              # PyInstaller 配置
├── .mcp.json                    # Claude Code 配置
├── .env                         # 配置文件（不提交 Git）
└── pyproject.toml
```

---

## 常见问题

**端口被占用**
```powershell
netstat -ano | findstr 8026          # 查看占用
taskkill -f -pid <PID>               # 关闭进程
```

**检查 EDA 状态**
```powershell
netstat -ano | findstr 50055         # gRPC：有 LISTENING = 运行中
tasklist | findstr EDI.exe           # EDI 进程
```

**启动失败**
- 确认 `.env` 中 `EDA_GRPC_SERVER`、`EDI_PATH`、`TURBOCHARTS_PATH` 配置正确
- `uv sync` 确认依赖已安装
- 确认 EDA gRPC 服务已启动

**健康检查**
```
curl http://127.0.0.1:8026/health
# → {"status":"ok", "mcp_ready":true, "eda_grpc_ready":true}
```

---

## 注意事项

- `project_path` 必须是存在的 `.epp` 文件
- `timeout_seconds` 必须 > 0，超出操作上限会报错（open/close 300s, simulate 3600s, turbocharts 600s）
- stdio 模式下不要向 stdout 输出调试信息
- `.env` 配置在服务启动时自动加载

---

## 开发

### 运行测试

```powershell
uv run python tests/test_project_reader.py
uv run python tests/test_component_tools.py
uv run python tests/test_turbocharts_runner.py
uv run python tests/test_health.py
uv run python tests/test_tool_registry.py
```

### 打包

```powershell
powershell -File scripts/build.ps1
# 输出: dist/eda-mcp/（含 eda_mcp_server.exe + start.bat 启动器 + .env，约 137 MB）
```

### 添加新工具

1. 在 `servers/eda/` 对应分类文件中添加工具函数（纯函数，无 MCP 装饰器）
2. 在 `servers/eda/__init__.py` 中 re-export
3. 在 `servers/registry_server.py` 中 `mcp.tool()(func)` 注册

### 重新生成 proto

```powershell
python -m grpc_tools.protoc -I proto --python_out=proto --grpc_python_out=proto proto/ecserver.proto
# 编辑 proto/ecserver_pb2_grpc.py 第 5 行：import ecserver_pb2 → from proto import ecserver_pb2
```

### 相关文档

- [交接文档](./HANDOVER.md) — 架构、技术栈、通信流程
- [接口汇总](./EDI系统接口与外部调用汇总.md) — EDI 全量接口文档
