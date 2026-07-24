"""MCP 工具注册中心 — 导入即可自动注册所有 @mcp.tool() 工具。

═══════════════════════════════════════════════════════════
  已注册工具（共 24 个）：

  工程管理：
    list_epp_projects             扫描文件夹中的 .epp 工程
    open_edi_project              打开 .epp 工程
    close_edi_project             关闭 .epp 工程
    list_project_components       列出工程中的元件
    get_component_parameters      查询元件的完整参数
    get_project_summary           工程概览

  仿真：
    simulate_project              执行工程仿真（同步）
    start_simulation_async        启动异步仿真
    get_simulation_async_status   查询异步仿真状态
    get_simulation_async_result   获取异步仿真结果
    simulate_netlist_with_ads     调用 ADS 仿真控制器

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

  图表：
    compare_simulation_results    多 RAW 结果对比叠图
    turbocharts_convert           ADS RAW → 曲线图 + CSV
═══════════════════════════════════════════════════════════
"""

from __future__ import annotations

from servers.mcp_instance import mcp  # noqa: E402 — 全局 MCP 实例

# 导入工具模块即可触发 @mcp.tool() 装饰器注册
import servers.eda.project_manage       # noqa: F401
import servers.eda.simulation            # noqa: F401
import servers.eda.design_export         # noqa: F401
import servers.eda.model_replace         # noqa: F401
import servers.eda.edi_launcher          # noqa: F401
import servers.turbocharts.compare_results  # noqa: F401
import servers.turbocharts.convert_raw   # noqa: F401
import servers.ansys.project_manage       # noqa: F401
import servers.ansys.run_analysis         # noqa: F401
import servers.image_tools                # noqa: F401

# Web 路由
from servers.web_routes import ui_page, health_check, chat_endpoint, tool_list  # noqa: E402
from servers.image_tools import serve_image  # noqa: E402

mcp.custom_route("/", methods=["GET"])(ui_page)
mcp.custom_route("/ui", methods=["GET"])(ui_page)
mcp.custom_route("/health", methods=["GET"])(health_check)
mcp.custom_route("/chat", methods=["POST"])(chat_endpoint)
mcp.custom_route("/tools/list", methods=["GET"])(tool_list)
mcp.custom_route("/images/{token}", methods=["GET"])(serve_image)
