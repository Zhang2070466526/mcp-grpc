"""全局 MCP 实例 — 所有工具模块共享此实例。

工具函数直接使用 @mcp.tool() 装饰器注册，无需手动调用 mcp.tool()(func)。
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "EDA MCP",
    instructions=(
        "EDA 工程操作工具集："
        "扫描工程、打开工程、网表查看、仿真执行、截图原理图、"
        "模型替换、关闭工程、ADS 仿真控制、启动 EDI、RAW 图表生成、"
        "ANSYS HFSS 工具。"
    ),
)
