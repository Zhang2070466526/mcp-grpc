"""MCP 工具注册中心 — 导入即可自动注册所有 @mcp.tool() 工具。

═══════════════════════════════════════════════════════════
  已注册工具（数量由实际模块加载决定，配置工作区后 +1）：

  工程管理：
    list_epp_projects             扫描文件夹中的 .epp 工程
    open_edi_project              打开 .epp 工程
    close_edi_project             关闭 .epp 工程
    list_project_components       列出工程中的元件
    get_component_parameters      查询元件的完整参数
    get_project_summary           工程概览
    analyze_variables             分析变量定义和引用关系

  仿真：
    simulate_project              执行工程仿真（同步）
    start_simulation_async        启动异步仿真
    get_simulation_async_status   查询异步仿真状态
    get_simulation_async_result   获取异步仿真结果
    list_eda_tasks                列出异步仿真任务
    simulate_netlist              仿真网表，返回 RAW 结果
    simulate_netlist_with_ads     调用 ADS 仿真控制器
    list_simulation_components    查询仿真器件
    get_simulation_component_schema  查询器件参数 schema
    create_simulation_component   新增仿真器件
    update_simulation_component   更新仿真器件参数
    delete_simulation_component   按实例名删除器件
    set_component_active_state    设置器件状态（NORMAL/DISABLED/SHORTED）
    generate_schematic_from_netlist  从网表生成原理图
    replace_port_component          替换端口器件类型

  分析：
    export_project_netlist        查看/导出工程网表
    capture_schematic             截取原理图为图片

  模型：
    replace_models_from_csv       按 CSV 批量替换模型

  启动：
    launch_edi                    启动 EDI 客户端

  ANSYS：
    open_hfss_project             打开 .aedt HFSS 项目
    close_hfss_project            关闭 HFSS 项目
    launch_aedt                   启动 AEDT
    get_hfss_project_info         获取 HFSS 项目信息
    start_hfss_analysis_async     异步启动 HFSS 仿真
    get_hfss_analysis_status      查询 HFSS 仿真状态

  图片：
    show_image                    读取本地图片，返回 MCP ImageContent
    analyze_image                 调用视觉模型分析图片内容
    copy_image_to_workspace       条件注册，复制到 media/edi/mcp-cache/（需配置工作区）

  文档：
    open_document                 为本地 PDF/DOCX 生成临时 HTTP 链接
    open_local_document           使用系统默认程序打开本地文档

  报告：
    generate_simulation_report    生成本地仿真报告（PDF/DOCX）

  图表：
    list_result_curves            解析 RAW 返回可用曲线
    compare_simulation_results    多 RAW 结果对比叠图
    turbocharts_convert           ADS RAW → 曲线图 + CSV
═══════════════════════════════════════════════════════════
"""

from __future__ import annotations

from servers import mcp  # noqa: E402 — 全局 MCP 实例

# 导入工具模块即可触发 @mcp.tool() 装饰器注册
import servers.eda.project_manage       # noqa: F401
import servers.eda.simulation            # noqa: F401
import servers.eda.simulation_components # noqa: F401
import servers.eda.design_export         # noqa: F401
import servers.eda.model_replace         # noqa: F401
import servers.eda.edi_launcher          # noqa: F401
import servers.turbocharts.compare_results  # noqa: F401
import servers.turbocharts.convert_raw   # noqa: F401
import servers.ansys.project_manage       # noqa: F401
import servers.ansys.run_analysis         # noqa: F401
import servers.multimodal_vision          # noqa: F401 — show_image + copy + analyze + open_document + open_local_document
import servers.report                     # noqa: F401 — generate_simulation_report

# Resources & Prompts
import servers.resources_prompts      # noqa: F401 — @mcp.resource() / @mcp.prompt()

# Web 路由
from servers.chat.routes import ui_page, health_check, chat_endpoint, tool_list, upload_file  # noqa: E402
from servers.multimodal_vision import serve_image  # noqa: E402
from servers.multimodal_vision import serve_document  # noqa: E402

mcp.custom_route("/", methods=["GET"])(ui_page)
mcp.custom_route("/ui", methods=["GET"])(ui_page)
mcp.custom_route("/health", methods=["GET"])(health_check)
mcp.custom_route("/chat", methods=["POST"])(chat_endpoint)
mcp.custom_route("/tools/list", methods=["GET"])(tool_list)
mcp.custom_route("/images/{token}", methods=["GET"])(serve_image)
mcp.custom_route("/documents/{token}", methods=["GET"])(serve_document)
mcp.custom_route("/upload", methods=["POST"])(upload_file)
