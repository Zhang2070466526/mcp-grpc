# EDA MCP 项目交接文档

## 项目概述

将 EDA-PMDS/EDI 的 gRPC 接口和本地命令行工具封装为 MCP 服务，使 AI 客户端能通过自然语言操作 EDA 工程。

当前版本为**本地 MCP 模式**：每台电脑独立运行，服务、文件、EDI 均在本机，无需公共服务或远程 Agent。

## 代码仓库

D:\GitLabCode\mcp-grpc

## 目录结构

```
proto/                  # protobuf 协议文件
servers/
  __init__.py            # 全局 FastMCP 实例 + 版本号
  registry_server.py     # 工具注册 + Web 路由注册
  utils.py                # 公共工具函数
  settings.py             # 统一配置加载
  resources_prompts/       # 3 个 Resource + 4 个 Prompt
  multimodal_vision/      # 图片 + 视觉分析 + 文档工具
  report/                 # 仿真报告生成
  eda/                   # EDI 工程工具（26 个）
    __init__.py           # 公共 API + 工具清单
    config.py             # 配置 + ProjectReader + S-expression
    grpc_client.py        # gRPC 通信层（FetchEvent → PerformAction）
    project_manage.py     # 工程管理（7 工具）
    simulation.py         # 仿真（7 工具）
    simulation_components.py  # 仿真器件（8 工具）
    simulation_component_catalog.json  # 参数目录 v2.0
    design_export.py      # 网表/截图（2 工具）
    model_replace.py      # 模型替换（1 工具）
    edi_launcher.py       # 启动 EDI（1 工具）
  turbocharts/
    config.py             # run_turbocharts（信号量串行）
    convert_raw.py        # RAW 转图 + 曲线查询（2 工具）
    compare_results.py    # 仿真对比（1 工具）
  ansys/                  # ANSYS HFSS 工具（6 个）
    config.py             # 进程检测/COM 附着/锁文件
    project_manage.py     # 工程打开/关闭/启动/信息
    run_analysis.py       # 异步仿真
  chat/                   # 聊天模块
    service.py            # 聊天服务（会话/LLM/工具闭环）
    routes.py             # Web 路由（/health /chat /ui /tools/list）
    index.html            # 聊天前端页面
start_servers.py         # 一键启动入口
tests/                   # 测试套件
scripts/                 # 打包脚本 + PyInstaller 配置 + 启动脚本
docs/                    # 文档（API 参考/实现原理/交接/gRPC 协议）
.mcp.json                # Claude Code 配置
.env                     # 环境变量（不提交 Git）
pyproject.toml           # uv 项目配置 + PyPI 元数据
LICENSE                  # MIT 许可证
README.md                # 项目主文档
```

## 技术栈

Python 3.12+ / uv 包管理 / FastMCP (mcp >= 1.0.0) / grpcio >= 1.81.0 / protobuf >= 6.33.5 / python-dotenv

PyPI: https://pypi.org/project/edi-mcp/

## MCP 工具清单（启动时动态统计，配置 OPENCLAW_WORKSPACE 后多 1 个）

**工程管理**：list_epp_projects, open_edi_project, close_edi_project, list_project_components, get_component_parameters, get_project_summary, analyze_variables

**仿真器件**：get_simulation_component_schema, list_simulation_components, create_simulation_component, update_simulation_component, delete_simulation_component, set_component_active_state, generate_schematic_from_netlist, replace_port_component

**仿真**：simulate_project, start_simulation_async, get_simulation_async_status, get_simulation_async_result, list_eda_tasks, simulate_netlist, simulate_netlist_with_ads

**ANSYS**：open_hfss_project, close_hfss_project, launch_aedt, get_hfss_project_info, start_hfss_analysis_async, get_hfss_analysis_status

**导出分析**：export_project_netlist, capture_schematic

**模型/启动**：replace_models_from_csv, launch_edi

**图片**：show_image（MCP ImageContent）+ analyze_image（视觉模型分析，默认关闭）+ copy_image_to_workspace（需配置工作区，条件注册）

**文档**：open_document（临时 HTTP 链接）+ open_local_document（系统默认程序打开）

**图表**：list_result_curves, turbocharts_convert, compare_simulation_results

**报告**：generate_simulation_report

## 配置说明

每台电脑独立配置 `.env`，所有服务均为本机调用：

```
EDA_GRPC_SERVER=127.0.0.1:50055
EDI_PATH=C:\Program Files (x86)\EDI\EDI.exe    # 留空自动检测
TURBOCHARTS_PATH=C:\Program Files (x86)\EDI\turbocharts_app.exe  # 留空自动检测
MCP_TRANSPORT=streamable-http
MCP_HOST=127.0.0.1
MCP_PORT=50026
```

## 启动方式

```powershell
cd D:\GitLabCode\mcp-grpc
uv run python start_servers.py                        # HTTP 模式（推荐）
uv run python start_servers.py --transport stdio       # stdio 模式
```

## 通信流程

gRPC 工具：AI 客户端 -> MCP 工具 -> grpc_client.call_grpc() -> PerformAction + FetchEvent -> 返回结果

本地工具：AI 客户端 -> MCP 工具 -> subprocess -> 返回结果

## 并发控制

- EDA gRPC 操作：全局 RLock，最大并发 1
- 文件读取：允许并发（最多 4）
- Turbocharts：BoundedSemaphore(1)
- 单实例控制：启动时检查端口

## 测试

```powershell
uv run python tests/test_project_reader.py
uv run python tests/test_component_tools.py
uv run python tests/test_turbocharts_runner.py
uv run python tests/test_health.py
uv run python tests/test_tool_registry.py
```

## 打包

### PyPI（源码包）

```powershell
uv build
uv publish
```

首次使用需创建 `.pypirc` 配置 PyPI 令牌（已加入 `.gitignore`）。

发布后用户通过 `pip install edi-mcp` 安装，通过 `edi-mcp` 命令启动。

### PyInstaller（免安装二进制包）

```powershell
powershell -File scripts/build.ps1
# 输出: dist/edi-mcp/（含 edi_mcp_server.exe + start_server.bat + .env，约 90 MB）
```

目录型打包，复制 `dist/edi-mcp/` 到目标电脑后创建 `.env` 即可运行。
```

## 工具注册机制

所有工具函数通过 `@mcp.tool()` 装饰器定义在 `servers/` 各子包中（eda/、ansys/、turbocharts/、multimodal_vision/、report/），由 `servers/registry_server.py` 统一导入触发注册。各子包的 `__init__.py` 作为公共 API re-export 所有工具函数。

```
project_manage.py  ->  eda/__init__.py  ->  registry_server.py  ->  start_servers.py
  (定义 @mcp.tool())     (re-export)           (import 触发注册)        (解析参数, 启动)
```

## 扩展开发

添加 gRPC 工具：在 servers/eda/ 对应文件中添加 @mcp.tool() 装饰器 -> registry_server.py import 模块

重新生成 proto：
```powershell
python -m grpc_tools.protoc -I proto --python_out=proto --grpc_python_out=proto proto/ecserver.proto
# 编辑 proto/ecserver_pb2_grpc.py：import ecserver_pb2 -> from proto import ecserver_pb2
```

## 已知问题与注意事项

1. 本地 proto 目录名为 `proto`，避免与 grpcio 包名冲突
2. stdio 模式下不能向 stdout 输出任何内容（会破坏 MCP 协议）
3. `.env` 通过 `python-dotenv` 加载，在所有 service 模块首次 import 时生效
4. Windows 路径反斜杠在 `.env` 中不需要转义
5. gRPC 服务地址格式必须为 `host:port`
6. 超时上限：open/close 300s, simulate 3600s, turbocharts 600s
7. 端口占用：`netstat -ano | findstr <端口>` -> `taskkill -f -pid <PID>`
8. `launch_edi` 返回 success/process_started/grpc_ready 三个字段
9. `grpc_client.py` 从 `config.py` 统一导入 EDA_GRPC_SERVER
10. `.gitignore` 已排除 .idea/、.claude/、.env、dist/、build/、logs/
11. `start_servers.py` 使用私有属性 _tool_manager，MCP 版本升级后需验证
12. Windows HTTP 使用 SelectorEventLoop 避免 WinError 64
13. `/health` 端点可区分 MCP 故障与 EDI 离线
14. `compare_simulation_results` 使用 Matplotlib + numpy 做叠图插值
15. 打包为目录型，复制 dist/edi-mcp/ 到目标电脑后创建 .env 即可运行
16. 使用 Streamable HTTP 传输模式（stateless，支持 /ui /health /ready /chat /tools/list 自定义路由）
17. 控制台启动时显示 gRPC 50055 端口状态
18. 打包时自动过滤 LLM_API_KEY 等敏感配置，强制 MCP_TRANSPORT=streamable-http
19. ANSYS COM 支持多 ProgID 回退（AnsoftHfss.HfssScriptInterface / Ansoft.ElectronicsDesktop）
20. AEDT 工程锁文件管理：打开前检查/清理失效锁，关闭后安全删除，PID 活跃时绝不删除
21. `/tools/list` 端点返回全部 MCP 工具列表（40/41 个），`chat_client.html` 动态加载面板
22. EXE 使用 `exclude_binaries=True`，DLL/Pyd 统一放 `_internal/`，不再重复打包（预计减 45~50 MB）
23. `matplotlib.use("Agg")` 必须在 `import matplotlib.pyplot` 之前调用，否则 GUI 后端被意外加载
24. UPX 压缩已关闭（某些原生 DLL 压缩后兼容性问题），目录模式依赖 `_internal/` 不可单独分发 EXE
25. 构建脚本增加体积阈值检查：目录 > 105 MB 或 ZIP > 80 MB 视为失败，EXE > 15 MB 告警重复打包
26. Pillow AVIF/WebP 编码器已排除（节省约 7~8 MB），需通过 .spec excludes 控制，不可手动删除文件
27. `show_image` 始终返回 ImageContent；`copy_image_to_workspace` 仅当 OPENCLAW_WORKSPACE 有效时条件注册
28. SIMULATE_PROJECT 的 ads_output 通过 FetchEvent 长连接增量推送，每个事件追加原样片段；最终 SUCCESS/FAILED 事件的片段同样追加；不 strip、不覆写
29. 仿真 task_id 和 client_uuid 由 MCP 侧生成，贯穿 FetchEvent → PerformAction → 状态/结果查询
30. FetchEvent 必须在 PerformAction 之前建立（文档要求），否则 EDI 返回 external handler not ready
32. PyPI 包 (`edi-mcp`) 仅含 Python 源码，不含 PyInstaller 二进制；Windows 专属（pywin32/COM）
33. 配置统一到 `servers/settings.py`，所有模块通过 `get_settings()` 读取，不再各自调用 os.getenv
34. gRPC 返回增加 `outcome_known` / `task_success` 字段：TIMEOUT/STREAM_DISCONNECTED 时 `outcome_known=False, task_success=None`，MCP 异常增加 `failure_source: "mcp"`
35. `start_servers.py` 启动时调用 `settings.validate()`，校验 gRPC 地址格式、端口范围、传输方式
36. `document_tools.py` 已迁移到 `multimodal_vision/document.py`，PyInstaller spec 同步更新
37. Chat 工具列表和 Schema 改为从 MCP 元数据自动生成，不再手工维护两套；新增 MCP 工具无需手动同步（排除列表除外）
38. Chat 确认流程支持简单肯定词（确认/是/yes/ok/好的等），不需要输入随机 ID
39. HFSS 异步任务：2 小时 TTL 自动清理、最大 50 个任务、`outcome_known` / `task_success` 字段
40. `compare_simulation_results`：增加 alignment/reference_index/labels/X 轴递增/重复值/路径规范化校验
41. 报告日志脱敏：INFO 仅记录 file_type/output_path/size，完整 body 移入 DEBUG 级别
42. 传输方式切换为 Streamable HTTP + stateless，SSE 已删除，默认端点 `/mcp`
43. 新增 `/ready` 端点（初始化中 503，就绪后 200）+ 优雅关闭（SIGINT/SIGTERM）+ 生命周期日志
44. 重启后旧 MCP session 返回 Session not found，不伪造会话，客户端需重新 initialize
45. OPENCLAW_WORKSPACE 支持自动检测：留空时在 edi-mcp 同级找 rfclaw/openclaw-service/state/workspace
46. 文件生成工具统一返回 `artifacts` 数组（type/path/name/generated_by），message 用"已生成"不用"已显示"
47. `copy_image_to_workspace` 返回增加 `media_path`（相对路径）和 `media_type`（MIME），便于客户端生成 MEDIA 指令

## 维护人

- 负责人：--
- 更新时间：2026-08-06


