"""MCP 工具注册中心 — 集中管理所有工具的注册。

═══════════════════════════════════════════════════════════
  已注册工具（共 14 个）：

  工程管理：
    list_epp_projects             扫描文件夹中的 .epp 工程
    open_eda_project              打开 .epp 工程
    close_eda_project             关闭 .epp 工程
    list_project_components       列出工程中的元件
    get_component_parameters      查询元件的完整参数
    get_project_summary           工程概览

  仿真：
    simulate_project              执行工程仿真
    simulate_netlist_with_ads     调用 ADS 仿真控制器
    compare_simulation_results    多 RAW 结果对比叠图

  分析：
    export_project_netlist        查看/导出工程网表
    capture_schematic             截取原理图为图片

  模型：
    replace_models_from_csv       按 CSV 批量替换模型

  启动：
    launch_edi                    启动 EDI 客户端

  图表：
    turbocharts_convert           ADS RAW → 曲线图 + CSV
═══════════════════════════════════════════════════════════
"""

from __future__ import annotations
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "EDA MCP",
    instructions=(
        "EDA 工程操作工具集："
        "扫描工程、打开工程、网表查看、仿真执行、截图原理图、"
        "模型替换、关闭工程、ADS 仿真控制、启动 EDI、RAW 图表生成。"
    ),
)

# -- EDA gRPC 工具 --
from servers.eda import (  # noqa: E402
    capture_schematic,
    close_eda_project,
    compare_simulation_results,
    export_project_netlist,
    get_component_parameters,
    get_project_summary,
    launch_edi,
    list_epp_projects,
    list_project_components,
    open_eda_project,
    replace_models_from_csv,
    simulate_netlist_with_ads,
    simulate_project,
)
mcp.tool()(list_epp_projects)
mcp.tool()(open_eda_project)
mcp.tool()(close_eda_project)
mcp.tool()(simulate_project)
mcp.tool()(simulate_netlist_with_ads)
mcp.tool()(export_project_netlist)
mcp.tool()(capture_schematic)
mcp.tool()(replace_models_from_csv)
mcp.tool()(launch_edi)
mcp.tool()(list_project_components)
mcp.tool()(get_component_parameters)
mcp.tool()(get_project_summary)
mcp.tool()(compare_simulation_results)

# -- RawConverter 工具 --
from servers.turbocharts.server import (  # noqa: E402
    turbocharts_convert,
)
mcp.tool()(turbocharts_convert)
