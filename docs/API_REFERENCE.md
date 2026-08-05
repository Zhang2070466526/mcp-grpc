# EDI MCP API 参考

> 所有函数均可通过 `from servers.xxx import func` 直接调用，无需启动 MCP 服务。

```python
# 安装
pip install edi-mcp

# 使用
from servers.eda.project_manage import list_epp_projects
```

---

## 工程管理（7 个）

### `list_epp_projects`

```python
from servers.eda.project_manage import list_epp_projects

list_epp_projects(folder_path: str) -> dict
```

扫描文件夹中所有 `.epp` 工程文件。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `folder_path` | str | 是 | 要扫描的文件夹绝对路径 |

返回：
```python
{
    "success": True,
    "folder": "C:/Users/JGL/EDI-Workspace",
    "count": 3,
    "projects": [
        {"name": "demo1", "path": "C:/Users/JGL/EDI-Workspace/demo1.epp", "size": 0},
    ]
}
```

---

### `open_edi_project`

```python
from servers.eda.project_manage import open_edi_project

open_edi_project(project_path: str, timeout_seconds: int = 60) -> dict
```

打开 `.epp` 工程。通过 gRPC 调用 EDI 服务。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `project_path` | str | 是 | — | `.epp` 文件绝对路径 |
| `timeout_seconds` | int | 否 | 60 | 最长等待秒数（上限 300） |

返回：
```python
{
    "success": True,
    "completed": True,
    "status": "SUCCEEDED",
    "message": "OPEN_PROJECT 成功",
    "project_path": "C:/Projects/test/test.epp",
    "details": {"project_path": "C:/Projects/test/test.epp"}
}
```

---

### `close_edi_project`

```python
from servers.eda.project_manage import close_edi_project

close_edi_project(project_path: str, need_save: bool = False, timeout_seconds: int = 60) -> dict
```

关闭 `.epp` 工程。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `project_path` | str | 是 | — | `.epp` 文件绝对路径 |
| `need_save` | bool | 否 | False | 关闭前是否保存 |
| `timeout_seconds` | int | 否 | 60 | 最长等待秒数 |

---

### `list_project_components`

```python
from servers.eda.project_manage import list_project_components

list_project_components(
    project_path: str,
    schematic_name: str = "main",
    component_type: str = "",
    name_contains: str = "",
    offset: int = 0,
    limit: int = 100,
) -> dict
```

列出原理图中的元件（不含完整参数，避免响应过大）。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `project_path` | str | 是 | — | `.epp` 文件绝对路径 |
| `schematic_name` | str | 否 | "main" | 原理图名称 |
| `component_type` | str | 否 | "" | 按类型过滤（如 "TermG"） |
| `name_contains` | str | 否 | "" | 按名称模糊匹配 |
| `offset` | int | 否 | 0 | 分页偏移 |
| `limit` | int | 否 | 100 | 每页上限（最大 500） |

返回：
```python
{
    "success": True,
    "total": 15,
    "components": [
        {"component_id": "uuid", "name": "R1", "type": "ResG", "model_id": "..."}
    ]
}
```

---

### `get_component_parameters`

```python
from servers.eda.project_manage import get_component_parameters

get_component_parameters(
    project_path: str,
    component_id: str,
    schematic_name: str = "main",
    include_hidden: bool = False,
) -> dict
```

查询单个元件的完整参数列表。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `project_path` | str | 是 | — | `.epp` 文件绝对路径 |
| `component_id` | str | 是 | — | 元件 UUID（从 `list_project_components` 获取） |
| `schematic_name` | str | 否 | "main" | 原理图名称 |
| `include_hidden` | bool | 否 | False | 是否包含隐藏参数 |

---

### `get_project_summary`

```python
from servers.eda.project_manage import get_project_summary

get_project_summary(
    project_path: str,
    include_component_types: bool = True,
    include_latest_result: bool = True,
) -> dict
```

获取 `.epp` 工程完整概览（元数据、原理图、仿真配置、最近结果）。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `project_path` | str | 是 | — | `.epp` 文件绝对路径 |
| `include_component_types` | bool | 否 | True | 是否统计元件类型分布 |
| `include_latest_result` | bool | 否 | True | 是否包含最近仿真结果 |

返回：
```python
{
    "success": True,
    "project": {"project_id": "...", "name": "demo", "author": ""},
    "schematics": {"count": 1, "names": ["main"]},
    "components": {"total": 15, "by_type": {"ResG": 5, "CapG": 3}},
    "simulation": {"type": "S_Param", "start": "0 GHz", "stop": "10 GHz"},
    "latest_result": {"path": ".../result.raw", "exists": True, "size": 2048}
}
```

---

### `analyze_variables`

```python
from servers.eda.project_manage import analyze_variables

analyze_variables(project_path: str) -> dict
```

分析工程中的 Var 变量定义、其他元件对变量的引用、Sweep 扫描配置。

返回：
```python
{
    "variables": [{"name": "freqin", "parameter": "freqin", "initial": "29", ...}],
    "references": [{"variable": "freqin", "component": "PORT1", "parameter": "Freq[1]"}, ...],
    "sweeps": [{"sweep": "Sweep2", "variable": "freqin", "start": "29", "stop": "31", ...}]
}
```

---

## 仿真（7 个）

### `simulate_project`

```python
from servers.eda.simulation import simulate_project

simulate_project(project_path: str, log_source: str = "mcp_client", timeout_seconds: int = 600) -> dict
```

对 `.epp` 工程执行仿真，**同步等待**完成。FetchEvent 长连接期间实时收集 `ads_output` 增量日志。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `project_path` | str | 是 | — | `.epp` 文件绝对路径 |
| `log_source` | str | 否 | "mcp_client" | 日志来源标识 |
| `timeout_seconds` | int | 否 | 600 | 最长等待秒数（上限 3600） |

返回：
```python
{
    "success": True,
    "completed": True,
    "status": "SUCCEEDED",
    "project_path": "C:/Projects/test/test.epp",
    "result_path": "C:/Projects/test/history/result.raw",
    "ads_output": "Parsing netlist...\nTask completed.\n",
    "log_complete": True
}
```

> **注意**：此函数为同步阻塞，一次 HTTP 请求可能等待数分钟。交互场景建议使用 `start_simulation_async`。

---

### `start_simulation_async`

```python
from servers.eda.simulation import start_simulation_async

start_simulation_async(project_path: str, log_source: str = "mcp_client", timeout_seconds: int = 600) -> dict
```

**异步启动**仿真，立即返回 `task_id`。通过以下工具查询进度和结果。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `project_path` | str | 是 | — | `.epp` 文件绝对路径 |
| `log_source` | str | 否 | "mcp_client" | 日志来源标识 |
| `timeout_seconds` | int | 否 | 600 | 后台任务最长等待秒数 |

返回：
```python
{
    "success": True,
    "task_id": "a1b2c3d4...",
    "client_uuid": "e5f6...",
    "status": "QUEUED",
    "message": "仿真任务已创建"
}
```

---

### `get_simulation_async_status`

```python
from servers.eda.simulation import get_simulation_async_status

get_simulation_async_status(task_id: str) -> dict
```

查询异步仿真任务状态和已实时接收的 `ads_output` 日志。运行中即可查询。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `task_id` | str | 是 | `start_simulation_async` 返回的 task_id |

返回：
```python
{
    "success": True,
    "completed": False,
    "task_id": "a1b2...",
    "status": "RUNNING",
    "ads_output": "Parsing netlist...\n",
    "log_complete": False,
    "project_path": "C:/Projects/test/test.epp",
    "result_path": "",
    "started_at": 1750000000.0
}
```

---

### `get_simulation_async_result`

```python
from servers.eda.simulation import get_simulation_async_result

get_simulation_async_result(task_id: str) -> dict
```

获取仿真最终结果。运行中返回当前部分日志，完成后返回完整 `ads_output`。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `task_id` | str | 是 | `start_simulation_async` 返回的 task_id |

运行中返回：
```python
{"success": True, "completed": False, "status": "RUNNING", "ads_output": "..."}
```

完成后返回：
```python
{
    "success": True, "completed": True,
    "status": "SUCCEEDED",
    "project_path": "...",
    "result_path": ".../history/result.raw",
    "ads_output": "完整日志...",
    "log_complete": True
}
```

---

### `simulate_netlist`

```python
from servers.eda.simulation import simulate_netlist

simulate_netlist(netlist_path: str, timeout_seconds: int = 600) -> dict
```

仿真指定网表文件，返回 RAW 结果和仿真器输出日志。服务端自动复制网表→仿真→归档→清理。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `netlist_path` | str | 是 | — | 网表文件路径（必须已存在） |
| `timeout_seconds` | int | 否 | 600 | 最长等待秒数 |

返回：
```python
{
    "success": True,
    "status": "SUCCEEDED",
    "result_path": "C:/test/history/result.raw",
    "ads_output": "ADS simulator output...",
    "details": {"netlist_path": "C:/test/netlist.log"}
}
```

---

### `simulate_netlist_with_ads`

```python
from servers.eda.simulation import simulate_netlist_with_ads

simulate_netlist_with_ads(netlist_path: str, ads_path: str = "", timeout_seconds: int = 120) -> dict
```

直接调用 ADS 仿真控制器处理网表。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `netlist_path` | str | 是 | — | 网表文件路径 |
| `ads_path` | str | 否 | "" | ADS 安装路径（空则自动判断） |
| `timeout_seconds` | int | 否 | 120 | 最长等待秒数 |

---

### `list_eda_tasks`

```python
from servers.eda.simulation import list_eda_tasks

list_eda_tasks(status: str = "") -> dict
```

列出当前 MCP 进程中已提交的异步仿真任务。可按状态过滤。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `status` | str | 否 | "" | 按状态过滤：QUEUED / RUNNING / SUCCEEDED / FAILED / TIMEOUT 等 |

返回：
```python
{"success": True, "total": 2, "tasks": [
    {"task_id": "abc123", "status": "RUNNING", "project_path": "...", ...}
]}
```

---

## 导出与分析（2 个）

### `export_project_netlist`

```python
from servers.eda.design_export import export_project_netlist

export_project_netlist(project_path: str, timeout_seconds: int = 60) -> dict
```

查看/导出 `.epp` 工程的网表，返回网表文件路径。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `project_path` | str | 是 | — | `.epp` 文件绝对路径 |
| `timeout_seconds` | int | 否 | 60 | 最长等待秒数 |

---

### `capture_schematic`

```python
from servers.eda.design_export import capture_schematic

capture_schematic(project_path: str, img_path: str, timeout_seconds: int = 60) -> dict
```

截取原理图为图片（PNG/JPG 等）。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `project_path` | str | 是 | — | `.epp` 文件绝对路径 |
| `img_path` | str | 是 | — | 输出图片路径 |
| `timeout_seconds` | int | 否 | 60 | 最长等待秒数 |

---

## 模型与启动（2 个）

### `replace_models_from_csv`

```python
from servers.eda.model_replace import replace_models_from_csv

replace_models_from_csv(project_path: str, csv_path: str, timeout_seconds: int = 60) -> dict
```

按 CSV 批量替换元件模型。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `project_path` | str | 是 | — | `.epp` 文件绝对路径 |
| `csv_path` | str | 是 | — | CSV 文件绝对路径 |
| `timeout_seconds` | int | 否 | 60 | 最长等待秒数 |

---

### `launch_edi`

```python
from servers.eda.edi_launcher import launch_edi

launch_edi(edi_path: str = "", wait_for_grpc: bool = True, wait_timeout: int = 30) -> dict
```

启动 EDI 客户端并等待 gRPC 就绪。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `edi_path` | str | 否 | .env 配置 | EDI.exe 路径 |
| `wait_for_grpc` | bool | 否 | True | 是否等待 gRPC 端口就绪 |
| `wait_timeout` | int | 否 | 30 | 等待超时秒数 |

---

## 图表（3 个）

### `list_result_curves`

```python
from servers.turbocharts.convert_raw import list_result_curves

list_result_curves(result_path: str) -> dict
```

解析 ADS RAW 仿真结果文件，返回可用曲线名和依赖轴。画图前调用避免猜测曲线名。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `result_path` | str | 是 | RAW 文件路径 |

返回：
```python
{"success": True, "format": "MDS", "datasets": [
    {"plot_name": "SP SP1[1]", "dependencies": ["freq"],
     "variables": [{"name": "S[2,1]", "type": "complex"}],
     "suggested_curves": ["DB_S[2,1]", "real_S[2,1]", ...]}
]}
```

---

### `turbocharts_convert`

```python
from servers.turbocharts.convert_raw import turbocharts_convert

turbocharts_convert(
    raw_path: str,
    img_path: str,
    chart_type: str,
    csv_path: str = "",
    linename: str = "",
    dependency: str = "",
    ac_config: str = "",
) -> dict
```

ADS RAW 结果文件转换为曲线图 + CSV。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `raw_path` | str | 是 | RAW 文件路径 |
| `img_path` | str | 是 | 输出图片路径（PNG/JPG/BMP/SVG） |
| `chart_type` | str | 是 | `"SP"` / `"HB"` / `"XDB"` |
| `csv_path` | str | 否 | 同步导出 CSV 路径 |
| `linename` | str | 否 | 曲线名，如 `"DB_S[2,1]"` |
| `dependency` | str | 否 | 依赖轴，通常 `"freq"` |
| `ac_config` | str | 否 | 精度配置 |

常用曲线名：
- `DB_S[2,1]` — 增益
- `VSWR_S[1,1]` — 驻波
- `real_nf(1)` — 噪声系数
- `real_delayS[2,1]` — 群时延

返回：
```python
{
    "success": True,
    "return_code": 0,
    "img_generated": True,
    "csv_generated": True,
    "output_paths": {"img": "C:/result/gain.png", "csv": "C:/result/gain.csv"}
}
```

---

### `compare_simulation_results`

```python
from servers.turbocharts.compare_results import compare_simulation_results

compare_simulation_results(
    result_paths: list[str],
    curve: str,
    img_path: str,
    chart_type: str = "SP",
    labels: list[str] | None = None,
    dependency: str = "freq",
    csv_path: str = "",
    alignment: str = "intersection",
    reference_index: int = 0,
) -> dict
```

多个 RAW 结果同一条曲线对比叠图（Matplotlib）。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `result_paths` | list | 是 | RAW 文件路径（2-8 个） |
| `curve` | str | 是 | 曲线名 |
| `img_path` | str | 是 | 输出图片路径 |
| `labels` | list | 否 | 每条曲线标签 |
| `dependency` | str | 否 | 依赖轴（默认 "freq"） |
| `alignment` | str | 否 | 对齐方式："intersection" 或 "interpolation" |

返回：
```python
{
    "success": True,
    "image_path": "C:/compare.png",
    "curve": "DB_S[2,1]",
    "metrics": [
        {"label": "label1", "max_absolute_difference": 0.5, "rms_difference": 0.12}
    ]
}
```

---

## 图片（2 个）

### `show_image`

```python
from servers.image_tools import show_image

show_image(image_path: str) -> list
```

读取本地图片，返回标准 MCP ImageContent。不复制文件，不依赖 OpenClaw。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `image_path` | str | 是 | 图片文件绝对路径 |

返回 `[TextContent, ImageContent]`，其中 ImageContent 包含 Base64 编码的图片数据。
≤10MB 时内嵌图片；>10MB 时只返回本地路径供本机查看。

---

### `copy_image_to_workspace`（条件注册）

仅在 `OPENCLAW_WORKSPACE` 配置有效时注册。负责将图片复制到 `media/edi/`，返回绝对路径和 `openclaw_attachment.filePath`。显示由 OpenClaw Agent 的消息工具负责。

```python
from servers.image_tools import copy_image_to_workspace

copy_image_to_workspace(image_path: str) -> dict
```

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `image_path` | str | 是 | 图片文件绝对路径 |

返回：`{"success": true, "copied": true, "displayed": false, "image_path": "...", "openclaw_attachment": {"filePath": "..."}}`

---

## 仿真器件管理（7 个）— 协议 v2

### `get_simulation_component_schema`

```python
from servers.eda.simulation_components import get_simulation_component_schema

get_simulation_component_schema(component_type: str, parameter_name: str = "") -> dict
```

查询仿真控件支持的参数名、值类型、单位、创建/更新权限和动态参数模式。返回 `schema_version`、`protocol_version`、`parameter_patterns`。创建或修改器件前优先调用。

### `list_simulation_components`

```python
from servers.eda.simulation_components import list_simulation_components

list_simulation_components(project_path: str, component_type: str = "") -> dict
```

本地读取原理图，查询仿真器件（SParameter / HarmonicBalance / XDB）及其当前参数。

### `create_simulation_component`

```python
from servers.eda.simulation_components import create_simulation_component

create_simulation_component(project_path: str, component_type: str, parameters: dict | None = None, timeout_seconds: int = 120) -> dict
```

新增仿真器件。每次调用创建新实例，服务端自动分配实例名。parameters 可选，未提供的参数使用 EDI 默认值。

参数格式：`{"Start": {"value": "1", "unit": "GHz"}, "Pts": {"value": "101"}}`

### `update_simulation_component`

```python
from servers.eda.simulation_components import update_simulation_component

update_simulation_component(project_path: str, instance_name: str, parameters: dict, component_type: str = "", timeout_seconds: int = 120) -> dict
```

按实例名更新仿真器件参数。优先从已保存工程自动识别器件类型；实例未保存时可显式提供 `component_type`。显式类型与实际类型不一致会返回 `COMPONENT_TYPE_MISMATCH`。只更新传入的参数，其余保持原值。

### `delete_simulation_component`

```python
from servers.eda.simulation_components import delete_simulation_component

delete_simulation_component(project_path: str, instance_name: str, timeout_seconds: int = 120) -> dict
```

按实例名删除任意原理图器件及其连接线。MCP 只校验实例名非空，最终查找、删除和回滚由 EDI 服务完成。建议调用前先查询目标实例。

### `set_component_active_state`

```python
from servers.eda.simulation_components import set_component_active_state

set_component_active_state(project_path: str, instance_name: str, state: str, timeout_seconds: int = 120) -> dict
```

确定性设置器件状态。state 接受 NORMAL / DISABLED / SHORTED（大小写不敏感）。不是状态切换，重复调用具有幂等性。

### `generate_schematic_from_netlist`

```python
from servers.eda.simulation_components import generate_schematic_from_netlist

generate_schematic_from_netlist(project_path: str, netlist_path: str, clear_before_import: bool = False, confirm_clear: bool = False, timeout_seconds: int = 300) -> dict
```

从网表文件导入生成 main 原理图。默认追加模式。`clear_before_import=true` 会清空原理图，必须同时传 `confirm_clear=true` 确认。

---

## Resources & Prompts（协议 v2）

除了 36 个 Tool，服务还注册了只读 Resource 和可复用 Prompt 工作流模板。

### Resources（3 个）

| URI | MIME | 说明 |
|---|---|---|
| `edi://service/overview` | `application/json` | 服务版本、协议版本、gRPC 目标、安全规则 |
| `edi://reference/simulation-components` | `application/json` | 仿真器件参数目录（与 `get_simulation_component_schema` 同源） |
| `edi://reference/operation-guide` | `text/markdown` | Markdown 操作规则：创建/删除/网表导入的安全约束 |

> Resource 是只读上下文，由客户端主动拉取。标准 MCP 客户端可通过 `resources/list` 和 `resources/read` 访问。

### Prompts（3 个）

| Prompt | 参数 | 用途 |
|---|---|---|
| `inspect_edi_project` | `project_path`, `detail_level` | 只读检查工程（概览→变量→器件→仿真配置） |
| `run_and_review_simulation` | `project_path`, `execution_mode`, `analyze_log` | 统一异步仿真流程 + 日志分析 |
| `configure_simulation_component` | `project_path`, `action`, `component_type`, `instance_name`, `requirements` | Schema→参数→确认→创建/更新 |

> Prompt 是用户主动选择的工作流模板。标准 MCP 客户端可通过 `prompts/list` 和 `prompts/get` 访问。

> 注意：内置 EDI Chat (`/ui`) 当前主要消费 Tool，不自动拉取 Resources 或 Prompts。能否在客户端中显示取决于具体 MCP 客户端的实现。

---

## 辅助

### Chat 上下文

`servers/chat/service.py` 维护会话级状态，支持多轮对话：

```python
from servers.chat.service import ChatService

svc = ChatService.instance()
response = await svc.chat(session_id="abc123", message="打开第一个工程")
# response: ChatResponse(success=True, reply="已打开 demo1.epp", activities=[...], context={...}, media=[...])
```

会话自动记住当前工程路径和最近仿真 task_id，消除重复输入。

---

## 返回结构约定

所有 gRPC 工具的返回结构统一为：

```python
{
    "success": bool,        # 是否成功
    "completed": bool,      # 是否已终态（异步任务运行中为 False）
    "status": str,          # QUEUED / ACCEPTED / RUNNING / SUCCEEDED / FAILED / REJECTED / TIMEOUT
    "message": str,         # 描述信息
    "project_path": str,    # 工程路径（如适用）
    "result_path": str,     # 结果路径（如适用）
    "ads_output": str,      # 增量拼接的完整日志
    "log_complete": bool,   # 日志是否接收完整
    "details": dict,        # 原始事件 payload 字段
}
```

纯本地工具（如 `list_epp_projects`）使用各自的简化结构。
