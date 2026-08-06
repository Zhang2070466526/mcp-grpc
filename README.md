# EDI MCP 服务

[![PyPI](https://img.shields.io/pypi/v/edi-mcp?label=PyPI)](https://pypi.org/project/edi-mcp/)

将 EDI 的 gRPC 接口、命令行工具和 ANSYS HFSS 封装为 **MCP 服务**，支持 SSE（Web）和 stdio（本地）两种传输方式，使 AI 客户端能通过自然语言操作 EDA 工程。

> 每台电脑独立运行，服务和文件都在本机。

## 快速开始

### 安装

```powershell
pip install edi-mcp
```

或源码：

```powershell
git clone <repo-url> && cd mcp-grpc && uv sync
```

### 配置

创建 `.env` 文件（通常只需确认第一行）：

```ini
EDA_GRPC_SERVER=127.0.0.1:50055
EDI_PATH=                                         # 留空自动检测
TURBOCHARTS_PATH=                                 # 留空自动检测
MCP_TRANSPORT=sse
MCP_PORT=50026
OPENCLAW_WORKSPACE=                               # 配置后启用 copy_image_to_workspace
```

> 完整配置和客户端接入说明见 [部署指南](./docs/DEPLOY.md)。

### 启动

```powershell
edi-mcp                    # SSE 模式，默认端口 50026
edi-mcp --transport stdio  # stdio 模式
edi-mcp --port 9000        # 自定义端口
```

验证：

```
curl http://127.0.0.1:50026/health
→ {"status":"ok","mcp_ready":true,"eda_grpc_ready":true}
```

---

## 使用方式

| 方式 | 说明 |
|---|---|
| **MCP 客户端** | Claude Code / OpenClaw 接入后，自然语言调用全部工具 |
| **聊天界面** | 浏览器访问 `http://127.0.0.1:50026/ui` |
| **Python 调用** | `from servers.eda import list_epp_projects` 直接调用函数 |

```python
from servers.eda.project_manage import list_epp_projects
from servers.eda.simulation import start_simulation_async

r = list_epp_projects("C:/Users/JGL/EDI-Workspace")
# → {"success": True, "count": 3, "projects": [...]}

r = start_simulation_async("C:/Projects/test/test.epp")
# → {"success": True, "task_id": "abc123...", "status": "QUEUED"}
```

---

## 工具一览

### 工程管理（7 个）

| 工具 | 说明 |
|---|---|
| `list_epp_projects` | 扫描文件夹中的 .epp 工程 |
| `open_edi_project` | 打开 .epp 工程 |
| `close_edi_project` | 关闭工程 |
| `list_project_components` | 列出工程中的元件 |
| `get_component_parameters` | 查询单个元件的完整参数 |
| `get_project_summary` | 工程概览（元数据/原理图/仿真配置） |
| `analyze_variables` | 分析变量定义、引用和 Sweep 配置 |

### 仿真器件（7 个）— 协议 v2

| 工具 | 说明 |
|---|---|
| `get_simulation_component_schema` | 查询 SP/HB/XDB 支持的参数和权限 |
| `list_simulation_components` | 查询工程中的仿真器件 |
| `create_simulation_component` | 新增器件（每次创建新实例） |
| `update_simulation_component` | 按实例名更新参数（自动识别类型） |
| `delete_simulation_component` | 按实例名删除器件 |
| `set_component_active_state` | 设置 NORMAL / DISABLED / SHORTED |
| `generate_schematic_from_netlist` | 从网表导入生成原理图 |

### 仿真（7 个）

| 工具 | 说明 |
|---|---|
| `simulate_project` | 执行工程仿真（同步） |
| `start_simulation_async` | 启动异步仿真 |
| `get_simulation_async_status` | 查询异步仿真进度 |
| `get_simulation_async_result` | 获取异步仿真结果 |
| `list_eda_tasks` | 列出当前仿真任务 |
| `simulate_netlist` | 仿真网表文件 |
| `simulate_netlist_with_ads` | 调用 ADS 仿真控制器 |

### 导出与分析

| 工具 | 说明 |
|---|---|
| `export_project_netlist` | 查看/导出工程网表 |
| `capture_schematic` | 截取原理图为图片 |

### 模型与启动

| 工具 | 说明 |
|---|---|
| `replace_models_from_csv` | 按 CSV 批量替换模型 |
| `launch_edi` | 启动 EDI 客户端 |

### ANSYS HFSS（6 个）

| 工具 | 说明 |
|---|---|
| `open_hfss_project` | 启动 AEDT 并打开 .aedt 项目 |
| `close_hfss_project` | 关闭 AEDT 项目 |
| `launch_aedt` | 启动 AEDT |
| `get_hfss_project_info` | 查询项目列表和活动设计 |
| `start_hfss_analysis_async` | 异步启动 HFSS 仿真 |
| `get_hfss_analysis_status` | 查询 HFSS 仿真状态 |

### 图表与图片

| 工具 | 说明 |
|---|---|
| `list_result_curves` | 解析 RAW 返回可用曲线名 |
| `turbocharts_convert` | ADS RAW → 曲线图 + CSV |
| `compare_simulation_results` | 多 RAW 同曲线对比叠图 |
| `show_image` | 返回 MCP ImageContent |
| `analyze_image` | 调用视觉模型分析图片内容 |
| `copy_image_to_workspace`* | 复制到工作区（需 OPENCLAW_WORKSPACE） |
| `generate_simulation_report` | 生成本地仿真报告（PDF/DOCX） |
| `open_document` | 为 PDF/DOCX 生成临时 HTTP 链接 |
| `open_local_document` | 用系统默认程序打开本地文档 |

> *条件注册。完整参数说明见 [API 参考](./docs/API_REFERENCE.md)。

---

## 项目结构

```
├── proto/                        protobuf 协议及生成代码
├── servers/
│   ├── mcp_instance.py           FastMCP 全局实例
│   ├── registry_server.py        工具 / Resource / Prompt 注册入口
│   ├── runtime_config.py          运行时配置（端口/地址）
│   ├── settings.py                统一配置加载
│   ├── mcp_content.py            3 个 Resource + 4 个 Prompt
│   ├── multimodal_vision/        图片显示 + 工作区复制 + 视觉分析
│   ├── document_tools.py           文档工具（临时链接 + 本地打开）
│   ├── report/                    仿真报告生成
│   ├── chat/                     聊天模块（LLM 多轮工具闭环）
│   ├── eda/                      EDI gRPC 工具
│   │   ├── config.py             配置 / S-expression 解析 / ProjectReader
│   │   ├── grpc_client.py        gRPC 通信层（FetchEvent + PerformAction）
│   │   ├── project_manage.py     工程管理（7 个工具）
│   │   ├── simulation.py         仿真（7 个工具）
│   │   ├── simulation_components.py     仿真器件（7 个工具）
│   │   ├── simulation_component_catalog.json  参数目录 v2.0
│   │   ├── design_export.py      网表 / 截图
│   │   ├── model_replace.py      模型替换
│   │   └── edi_launcher.py       启动 EDI
│   ├── turbocharts/              RAW 图表工具
│   └── ansys/                     ANSYS HFSS 工具
├── docs/                         项目文档
├── tests/                        测试套件（207 项）
├── scripts/                      打包 / 启动脚本
├── start_servers.py              入口
└── pyproject.toml
```

---

## 测试

```powershell
uv run pytest -q                 # 全量 207 项
uv run pytest tests/ -v          # 详细输出
```

---

## 打包发布

**PyPI：**

```powershell
uv build && uv publish
```

**PyInstaller 免安装包：**

```powershell
powershell -File scripts/build.ps1
# → dist/edi-mcp/（edi_mcp_server.exe + _internal/ + .env）
```

---

## 文档

| 文档 | 说明 |
|---|---|
| [部署指南](./docs/DEPLOY.md) | 打包产物使用、Claude Code / OpenClaw 配置 |
| [API 参考](./docs/API_REFERENCE.md) | 全部工具的参数、返回值、使用示例 |
| [实现原理](./docs/IMPLEMENTATION.md) | 每个工具的实现方式、通信流程、设计决策 |
| [交接文档](./docs/HANDOVER.md) | 架构设计、技术栈、扩展开发 |
| [gRPC 协议](./proto/grpc接口调用.md) | gRPC 接口调用说明 |
| [EDI 接口汇总](./docs/EDI系统接口与外部调用汇总.md) | EDI 系统全量对外接口 |

---

## 常见问题

### 端口被占用

```powershell
netstat -ano | findstr 50026         # 查找占用进程的 PID
taskkill -f -pid <PID>               # 强制结束
taskkill -f -im edi_mcp_server.exe   # EXE 版按名称结束
```

### 检查服务状态

```powershell
netstat -ano | findstr 50055         # gRPC：有 LISTENING = EDI 运行中
netstat -ano | findstr 50026         # MCP：有 LISTENING = 服务运行中
curl http://127.0.0.1:50026/health   # 健康检查
```

### analyze_image 注意事项

- **不会自动触发**：只有用户明确要求分析图片时才调用，AI 不应主动使用
- **显示给我看 ≠ 上传分析**：展示图片用 `show_image`，识别内容用 `analyze_image`
- **会上传到第三方**：图片会发送到配置的视觉模型服务
- **未配置不可用**：需配置 `VISION_API_KEY` + `VISION_BASE_URL` + `VISION_MODEL`
