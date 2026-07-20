r"""MCP 服务启动器 — 只负责启动，工具注册见 servers/registry_server.py。

用法：
    uv run python start_servers.py
    uv run python start_servers.py --transport streamable-http --port 8000
    uv run python start_servers.py --transport stdio
"""

from __future__ import annotations

import argparse

import os

from dotenv import load_dotenv

load_dotenv()

# -- 配置 --
DEFAULT_TRANSPORT = os.getenv("MCP_TRANSPORT", "stdio")
DEFAULT_HOST = os.getenv("MCP_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.getenv("MCP_PORT", "8000"))

from servers.registry_server import mcp

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
        # stdio 模式：不向 stdout 输出（MCP 协议通道）
        mcp.run(transport="stdio")
