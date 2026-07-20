"""MCP 工具注册中心 — 集中管理所有工具的注册。

═══════════════════════════════════════════════════════════
  已注册工具（共 10 个）：

  工程管理：
    list_epp_projects             扫描文件夹中的 .epp 工程
    open_eda_project              打开 .epp 工程
    close_eda_project                 关闭工程

  仿真：
    simulate_project              执行工程仿真
    simulate_netlist_with_ads    调用 ADS 仿真控制器

  分析：
    export_project_netlist          查看/导出工程网表
    capture_schematic             截取原理图为图片

  模型：
    replace_models_from_csv                 按 CSV 批量替换模型

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
    simulate_netlist_with_ads,
    capture_schematic,
    close_eda_project,
    launch_edi,
    list_epp_projects,
    replace_models_from_csv,
    open_eda_project,
    simulate_project,
    export_project_netlist,
)
mcp.tool()(open_eda_project)
mcp.tool()(list_epp_projects)
mcp.tool()(close_eda_project)
mcp.tool()(simulate_project)
mcp.tool()(simulate_netlist_with_ads)
mcp.tool()(export_project_netlist)
mcp.tool()(capture_schematic)
mcp.tool()(replace_models_from_csv)
mcp.tool()(launch_edi)

# -- RawConverter 工具 --
from servers.turbocharts.server import (  # noqa: E402
    turbocharts_convert,
)
mcp.tool()(turbocharts_convert)
