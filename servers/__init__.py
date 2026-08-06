"""MCP 服务器集合 — 全局 MCP 实例 + 版本号。

子包：
  - servers.eda : EDA gRPC 服务（工程、网表、仿真）
  - servers.turbocharts : turbocharts_app 图表生成
  - servers.multimodal_vision : 图片显示 / 工作区复制 / 视觉分析
  - servers.report : 仿真报告生成
"""

from mcp.server.fastmcp import FastMCP

__version__ = "0.1.4"

mcp = FastMCP(
    "EDA MCP",
    instructions=(
        "EDA 工程操作工具集："
        "扫描工程、打开工程、网表查看、仿真执行、截图原理图、"
        "模型替换、关闭工程、ADS 仿真控制、启动 EDI、RAW 图表生成、"
        "ANSYS HFSS 工具。"
    ),
)
