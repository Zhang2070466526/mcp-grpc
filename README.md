# EDI MCP 服务

[![PyPI](https://img.shields.io/pypi/v/edi-mcp?label=PyPI)](https://pypi.org/project/edi-mcp/)

每台安装 EDI 的电脑运行一个本地 MCP 服务，将 EDA-PMDS/EDI 的 gRPC 接口、命令行工具和 ANSYS HFSS 封装为 25 个 MCP 工具，
支持 **SSE** 和 **stdio** 两种传输方式，使 AI 客户端能通过自然语言操作 EDA 工程。

---

## 快速开始

### 1. 安装

**方式 A：PyPI（推荐）**

```powershell
pip install edi-mcp
```

**方式 B：源码**

```powershell
git clone <repo-url>
cd mcp-grpc
uv sync
```

### 2. 配置 `.env`

在项目根目录（或运行目录）创建 `.env` 文件：

```ini
EDA_GRPC_SERVER=127.0.0.1:50055
# EDI/TurboCharts 路径：留空自动检测 ../ 目录下的 EDI.exe/EDA-PMDS.exe/CAIS.exe
EDI_PATH=C:\Program Files (x86)\EDI\EDI.exe
TURBOCHARTS_PATH=C:\Program Files (x86)\EDI\turbocharts_app.exe
MCP_TRANSPORT=sse
MCP_HOST=127.0.0.1
MCP_PORT=50026

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
# PyPI 安装
edi-mcp --transport sse

# 源码运行
cd D:\GitLabCode\mcp-grpc
uv run python start_servers.py
```

输出示例：
```
==================================================
  EDI MCP v0.1.0
  UI:   http://127.0.0.1:50026/ui
  MCP:  http://127.0.0.1:50026/sse
  Tools: 26 loaded
  gRPC: 127.0.0.1:50055 [ONLINE]
  Close window to stop
==================================================
```

启动后自动监听 `127.0.0.1:50026`：
- 所有本机客户端通过 `http://127.0.0.1:50026/sse` 连接
- EDI gRPC 操作由全局锁保证串行
- Turbocharts 由信号量保证同一时间一个进程
- `/health` 健康检查 — 返回 EDA gRPC 和 Turbocharts 状态
- `/ui` 聊天客户端 — 自然语言驱动 25 个工具，带工具面板和系统主题
- `/chat` 聊天 API — POST `{"message":"..."}` 返回 LLM + 工具执行结果
- 聊天客户端文件：`servers/chat/index.html`（与路由同目录）

**stdio 模式** — 由 MCP 客户端管理进程生命周期，适合单客户端调试：

```powershell
# PyPI 安装
edi-mcp --transport stdio

# 源码运行
uv run python start_servers.py --transport stdio
```

> stdio 模式下不能向 stdout 输出任何内容（MCP 协议通道），进程由客户端自动启停。

**自定义端口**：
```powershell
edi-mcp --port 9000
```

---

## 使用方式

### 方式一：命令行启动服务

```powershell
edi-mcp --transport sse --port 50026
```

启动后访问 `http://127.0.0.1:50026/ui` 使用聊天界面，或连接 MCP 客户端。

### 方式二：Python 调用工具函数

```python
from servers.eda.project_manage import list_epp_projects, create_blank_epp
from servers.eda.simulation import simulate_project, start_simulation_async

# 扫描工程
r1 = list_epp_projects("C:/Users/JGL/Desktop")
# r1: {"success": True, "count": 3, "projects": [...]}

# 创建空白工程
r2 = create_blank_epp("C:/Projects", "test")
# r2: {"success": True, "project_path": "C:/Projects/test/test.epp"}

# 启动异步仿真
r3 = start_simulation_async("C:/Projects/test/test.epp")
# r3: {"success": True, "task_id": "abc123...", "status": "QUEUED"}
```

### 方式三：MCP 客户端接入

Claude Code、OpenClaw 等 MCP 客户端接入后，用自然语言调用全部 25 个工具。无需写代码。

---

## 客户端配置

每台电脑的 `127.0.0.1` 都指向自己，服务和文件都在本机。

| 客户端 | 配置 |
|---|---|
| Claude Code | `.mcp.json` 已配置，`/mcp` 重载 |
| OpenClaw / Web | 名称 `eda`，Streamable HTTP，`http://127.0.0.1:50026/sse` |
| 其他 stdio 客户端 | `uv --directory D:/GitLabCode/mcp-grpc run python start_servers.py --transport stdio` |

其他 MCP 客户端通用配置：

```json
{
  "mcpServers": {
    "eda": {
      "command": "uv",
      "args": ["--directory", "D:/GitLabCode/mcp-grpc", "run", "python", "start_servers.py", "--transport", "stdio"],
      "env": { "EDA_GRPC_SERVER": "127.0.0.1:50055" }
    }
  }
}
```

---

## 工具参考（25 个）

### 工程管理

| 工具 | 说明 | 参数 |
|---|---|---|
| `list_epp_projects` | 扫描文件夹中的 .epp 工程 | `folder_path` |
| `open_edi_project` | 打开 .epp 工程 | `project_path`, `timeout_seconds`（默认 60） |
| `close_edi_project` | 关闭工程 | `project_path`, `need_save`（默认 false） |
| `list_project_components` | 列出工程中所有元件 | `project_path`, `schematic_name`, `component_type`, `name_contains` |
| `get_component_parameters` | 查询单个元件的全部参数 | `project_path`, `component_id`, `schematic_name`, `include_hidden` |
| `get_project_summary` | 工程概览（元数据/原理图/仿真） | `project_path`, `include_component_types`, `include_latest_result` |

### 仿真

| 工具 | 说明 | 参数 |
|---|---|---|
| `simulate_project` | 执行工程仿真（同步） | `project_path` | `log_source`、`timeout_seconds`（默认 600） |
| `start_simulation_async` | 启动异步仿真 | `project_path` | `log_source`、`timeout_seconds` |
| `get_simulation_async_status` | 查询异步仿真状态 | `task_id` | - |
| `get_simulation_async_result` | 获取异步仿真结果 | `task_id` | - |
| `simulate_netlist` | 仿真网表，返回 RAW 结果 | `netlist_path` | `timeout_seconds`（默认 600） |
| `simulate_netlist_with_ads` | 调用 ADS 仿真控制器 | `netlist_path` | `ads_path`、`timeout_seconds`（默认 120） |

### 导出与分析

| 工具 | 说明 | 参数 |
|---|---|---|
| `export_project_netlist` | 查看/导出工程网表 | `project_path`, `timeout_seconds`（默认 60） |
| `capture_schematic` | 截取原理图为图片 | `project_path`, `img_path`, `timeout_seconds`（默认 60） |

### 模型与启动

| 工具 | 说明 | 参数 |
|---|---|---|
| `replace_models_from_csv` | 按 CSV 批量替换模型 | `project_path`, `csv_path`, `timeout_seconds`（默认 60） |
| `launch_edi` | 启动 EDI 客户端 | `edi_path`, `wait_for_grpc`（默认 true）, `wait_timeout` |

### ANSYS HFSS

| 工具 | 说明 | 参数 |
|---|---|---|
| `open_hfss_project` | 启动 AEDT 并打开 .aedt 项目（COM 优先/验证） | `project_path`, `aedt_path`, `wait_timeout` |
| `close_hfss_project` | 关闭 AEDT 项目（COM 优先/可强制） | `project_name`, `save_before_close`, `force` |
| `launch_aedt` | 启动 AEDT（已运行检测+就绪等待） | `aedt_path`, `wait_timeout` |
| `get_hfss_project_info` | 获取项目列表/活动项目/设计 | — |
| `start_hfss_analysis_async` | 异步启动 HFSS 仿真 | `project_path`, `design_name`, `setup_name` |
| `get_hfss_analysis_status` | 查询 HFSS 仿真状态 | `task_id`, `refresh_from_aedt` |

### 图片

| 工具 | 说明 | 参数 |
|---|---|---|
| `show_image` | 读取本地图片，返回 MCP ImageContent | `image_path` |

### 图表

| 工具 | 说明 | 参数 |
|---|---|---|
| `compare_simulation_results` | 多 RAW 同曲线对比叠图 | `result_paths`, `curve`, `img_path`, `chart_type`, `labels`, `dependency` |
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
│   ├── mcp_instance.py          # 全局 MCP 实例（装饰器注册）
│   ├── registry_server.py       # 工具导入入口 + Web 路由注册
│   ├── chat/                     # 聊天模块
│   │   ├── service.py            # 聊天服务（会话/LLM/工具闭环）
│   │   ├── routes.py             # Web 路由（/health /chat /ui /tools/list）
│   │   └── index.html            # 聊天前端页面
│   ├── image_tools.py           # 图片工具 — show_image（1 工具）
│   ├── eda/
│   │   ├── config.py            # 配置 + validate_file + ProjectReader + S-expression
│   │   ├── grpc_client.py       # gRPC 通信（带 EDA 全局锁）
│   │   ├── project_manage.py    # 工程管理（6 工具）
│   │   ├── simulation.py        # 仿真（6 工具）
│   │   ├── design_export.py     # 网表/截图（2 工具）
│   │   ├── model_replace.py     # 模型替换（1 工具）
│   │   └── edi_launcher.py      # 启动 EDI（1 工具）
│   ├── turbocharts/
│   │   ├── config.py             # 公共函数（run_turbocharts）
│   │   ├── convert_raw.py        # RAW 转图（1 工具）
│   │   └── compare_results.py    # 仿真对比（1 工具）
│   └── ansys/                     # ANSYS 工具（6 个）
│       ├── config.py              # 公共工具（进程检测/COM附着/锁文件）
│       ├── project_manage.py      # 工程管理 + 信息查询
│       └── run_analysis.py        # 异步仿真
├── docs/                         # 文档
│   ├── API_REFERENCE.md           # API 参考
│   ├── HANDOVER.md                # 交接文档
│   ├── grpc接口调用.md             # gRPC 协议说明
│   └── EDI系统接口与外部调用汇总.md  # EDI 接口汇总
├── start_servers.py              # 入口
├── tests/                       # 测试套件
├── scripts/
│   ├── build.ps1                 # 打包脚本
│   ├── run.bat                   # Windows 启动脚本
│   └── edi_mcp_server.spec       # PyInstaller 配置
├── .mcp.json                    # Claude Code 配置
├── .env                         # 配置文件（不提交 Git）
├── LICENSE                      # MIT 许可证
└── pyproject.toml
```

---

## 常见问题

**端口被占用**
```powershell
netstat -ano | findstr 50026          # 查看占用
taskkill -f -pid <PID>               # 关闭进程
```

**检查 EDA 状态**
```powershell
netstat -ano | findstr 50055         # gRPC：有 LISTENING = 运行中
tasklist | findstr EDI.exe           # EDI 进程
```

**启动失败**
- 确认 `.env` 中 `EDA_GRPC_SERVER` 配置正确（`EDI_PATH`/`TURBOCHARTS_PATH` 留空则自动检测）
- `uv sync` 确认依赖已安装
- 确认 EDA gRPC 服务已启动

**健康检查**
```
curl http://127.0.0.1:50026/health
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

### 运行完整测试套件

```powershell
uv run pytest -q -p no:cacheprovider
```

### 打包发布

**PyPI 发布**（源码包）：

首次需要创建 `.pypirc` 配置 PyPI 凭证（已加入 `.gitignore`，不会提交）：

```ini
[pypi]
repository = https://upload.pypi.org/legacy/
username = __token__
password = pypi-xxxxxxxxxxxx
```

之后发布只需：
```powershell
uv build
uv publish
```

**PyInstaller 打包**（免安装二进制包）：

```powershell
powershell -File scripts/build.ps1
# 输出: dist/edi-mcp/（含 edi_mcp_server.exe + start_server.bat + .env，约 90 MB）
```

### 添加新工具

1. 在对应分类文件中添加函数 + `@mcp.tool()` 装饰器
2. 在 `servers/registry_server.py` 中 `import` 该模块（触发装饰器注册）

### 重新生成 proto

```powershell
python -m grpc_tools.protoc -I proto --python_out=proto --grpc_python_out=proto proto/ecserver.proto
# 编辑 proto/ecserver_pb2_grpc.py 第 5 行：import ecserver_pb2 → from proto import ecserver_pb2
```

### 相关文档

- [部署指南](./docs/DEPLOY.md) — 打包产物使用 & 智能体 Claude Code / OpenClaw 配置
- [API 参考](./docs/API_REFERENCE.md) — 全部 25 个函数的参数、返回值、使用示例
- [交接文档](./docs/HANDOVER.md) — 架构、技术栈、通信流程
- [接口汇总](./docs/EDI系统接口与外部调用汇总.md) — EDI 全量接口文档
- [gRPC 协议](./docs/grpc接口调用.md) — 底层 gRPC 调用说明
