"""MCP 工具注册中心 — 集中管理所有工具的注册。

添加新工具时只需在此文件中：
1. import 工具函数
2. 调用 mcp.tool()(工具函数)
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
        "打开工程、网表查看、仿真执行、启动 EDI 客户端、"
        "RAW 文件图表生成。"
    ),
)

# ---------------------------------------------------------------------------
# 注册 EDA gRPC 工具
# ---------------------------------------------------------------------------

from servers.eda.server import (  # noqa: E402
    launch_edi,
    open_eda_project,
    simulate_project,
    view_project_netlist,
)

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
