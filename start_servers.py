r"""一键启动所有 MCP 服务 — 统一入口。

将所有已注册的 MCP 工具汇集到单个进程中，支持两种通信方式：

    streamable-http   单端口 HTTP 服务器（OpenClaw / Web 客户端）
    stdio             标准输入输出（Claude Code / VS Code）

用法：
    uv run python start_servers.py
    uv run python start_servers.py --transport streamable-http --port 8000
    uv run python start_servers.py --transport stdio

传输方式优先级：命令行 > .env 中的 MCP_TRANSPORT > 默认 stdio
"""

from __future__ import annotations

import argparse
import os

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()
DEFAULT_TRANSPORT = os.getenv("MCP_TRANSPORT", "stdio")
DEFAULT_HOST = os.getenv("MCP_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.getenv("MCP_PORT", "8000"))

# ---------------------------------------------------------------------------
# 注册所有工具
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "EDA MCP",
    instructions=(
        "EDA 工程操作工具集："
        "打开工程、网表查看、仿真执行、启动 EDI 客户端、"
        "RAW 文件图表生成（turbocharts）。"
    ),
)

# -- EDA gRPC 工具 --
from servers.eda.server import (  # noqa: E402
    launch_edi,
    open_eda_project,
    simulate_project,
    view_project_netlist,
)

# 注册为MCP工具
mcp.tool()(open_eda_project)
mcp.tool()(view_project_netlist)
mcp.tool()(simulate_project)
mcp.tool()(launch_edi)

# -- Turbocharts 工具 --
from servers.turbocharts.server import turbocharts_convert

mcp.tool()(turbocharts_convert)

# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="启动所有 MCP 服务")
    parser.add_argument(
        "--transport",  # 参数名称
        choices=["stdio", "streamable-http"],  # 可选值列表
        default=DEFAULT_TRANSPORT,  # 默认值
        help=f"通信方式（默认: {DEFAULT_TRANSPORT}）",  # 帮助说明
    )  # 定义 --transport 参数
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"streamable-http 模式端口（默认: {DEFAULT_PORT}）",
    )
    args = parser.parse_args()  # 执行参数解析，作用是将用户在命令行输入的实际参数转换为 Python 对象，供程序后续使用。

    tools = [t.name for t in mcp._tool_manager._tools.values()]
    if args.transport == "streamable-http":
        print(f"MCP 服务启动 [transport=streamable-http, port={args.port}]")
        print(f"已加载 {len(tools)} 个工具: {', '.join(tools)}")
        print(f"地址: http://{DEFAULT_HOST}:{args.port}/mcp")
        mcp.settings.host = DEFAULT_HOST
        mcp.settings.port = args.port
        mcp.run(transport="streamable-http")
    else:
        # stdio 模式：不能向 stdout 输出任何内容（MCP 协议通道）
        mcp.run(transport="stdio")
