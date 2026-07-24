r"""EDI MCP 一键启动 — 统一入口。

═══════════════════════════════════════════════════════════
  工具注册见：servers/registry_server.py
  工具定义见：servers/eda/*_service.py

  启动方式：
    uv run python start_servers.py                          # sse（默认）
    uv run python start_servers.py --transport stdio         # Claude Code
    uv run python start_servers.py --port 9000               # 自定义端口

  客户端连接：
    Claude Code   .mcp.json 自动管理，/mcp 重载
    OpenClaw      http://<IP>:8000/mcp
═══════════════════════════════════════════════════════════
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import socket
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# -- 配置 --
DEFAULT_TRANSPORT = os.getenv("MCP_TRANSPORT","sse")
# FastMCP 暴露的配置接口，底层用的 uvicorn.run(host="0.0.0.0")，0.0.0.0 = 这样就会监听本机所有网卡的所有 IP。
DEFAULT_HOST = os.getenv("MCP_HOST","127.0.0.1")
DEFAULT_PORT = int(os.getenv("MCP_PORT", "8026"))

from servers.mcp_instance import mcp
import servers.registry_server  #  — 触发工具注册


def _setup_logging() -> None:
    """按大小轮转的文件日志，写入 logs/mcp.log。"""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    handler = RotatingFileHandler(
        log_dir / "mcp.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    root.info("EDA MCP v0.1.0 starting")


def _run_http_server(port: int, transport: str = "streamable-http") -> None:
    """SSE / streamable-http 模式入口。"""
    host = DEFAULT_HOST or "127.0.0.1"
    if host != "127.0.0.1":
        print(f"WARNING: MCP_HOST={host} ignored, forcing 127.0.0.1 (local mode)")
        host = "127.0.0.1"

    # 单实例检查
    _test = socket.socket()
    try:
        _test.settimeout(1)
        if _test.connect_ex(("127.0.0.1", port)) == 0:
            print(f"端口 {port} 已被占用，MCP 可能已在运行。")
            sys.exit(1)
    finally:
        _test.close()

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(
            asyncio.WindowsSelectorEventLoopPolicy()
        )

    tools = [t.name for t in mcp._tool_manager._tools.values()]

    # 检测 50055 状态
    from servers.eda.config import EDA_GRPC_SERVER as _grpc_addr
    _grpc_host, _grpc_port = _grpc_addr.rsplit(":", 1)
    _test = socket.socket()
    _test.settimeout(1)
    _grpc_ok = _test.connect_ex((_grpc_host, int(_grpc_port))) == 0
    _test.close()

    print("=" * 50)
    print(f"  EDA MCP v0.1.0")
    print(f"  UI:   http://{host}:{port}/ui")
    print(f"  MCP:  http://{host}:{port}/sse")
    print(f"  Tools: {len(tools)} loaded")
    print(f"  gRPC: {_grpc_addr} [{'ONLINE' if _grpc_ok else 'OFFLINE'}]")
    print(f"  Close window to stop")
    print("=" * 50)

    mcp.settings.host = host
    mcp.settings.port = port
    mcp.run(transport=transport)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="启动所有 MCP 服务")
    parser.add_argument(
        "--transport",  # 参数名称
        choices=["stdio", "sse", "streamable-http"],  # 可选值列表
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

    if args.transport in ("sse", "streamable-http"):
        _setup_logging()
        _run_http_server(args.port, transport=args.transport)
    else:
        mcp.run(transport="stdio")
