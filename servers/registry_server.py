"""MCP 工具注册中心 — 集中管理所有工具的注册。

已注册工具（共 6 个）：
    list_epp_projects     扫描文件夹中的 .epp 工程
    open_eda_project      打开 .epp 工程
    view_project_netlist  查看/导出工程网表
    simulate_project      执行工程仿真
    launch_edi            启动 EDI 客户端
    turbocharts_convert   ADS RAW → 曲线图 + CSV


"""

from __future__ import annotations
from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# MCP 实例（唯一）
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "EDA MCP",
    instructions=(
        "EDA 工程操作工具集："
        "扫描工程、打开工程、网表查看、仿真执行、启动 EDI 客户端、"
        "RAW 文件图表生成。"
    ),
)

# ---------------------------------------------------------------------------
# 注册 EDA gRPC 工具
# ---------------------------------------------------------------------------

from servers.eda.server import (  # noqa: E402
    launch_edi,
    list_epp_projects,
    open_eda_project,
    simulate_project,
    view_project_netlist,
)

mcp.tool()(list_epp_projects)
mcp.tool()(open_eda_project)
mcp.tool()(view_project_netlist)
mcp.tool()(simulate_project)
mcp.tool()(launch_edi)

# ---------------------------------------------------------------------------
# 注册 RawConverter 工具
# ---------------------------------------------------------------------------

from servers.turbocharts.server import (  # noqa: E402
    turbocharts_convert,
)

mcp.tool()(turbocharts_convert)
