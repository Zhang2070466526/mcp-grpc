r"""EDI MCP 一键启动 — 统一入口。

═══════════════════════════════════════════════════════════
  工具注册见：servers/registry_server.py
  工具定义见：servers/eda/*.py

  启动方式：
    uv run python start_servers.py                          # sse（默认）
    uv run python start_servers.py --transport stdio         # Claude Code
    uv run python start_servers.py --port 9000               # 自定义端口

  客户端连接：
    Claude Code   .mcp.json 自动管理，/mcp 重载
    OpenClaw      http://127.0.0.1:50026/sse
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

if getattr(sys, "frozen", False):
    load_dotenv(Path(sys.executable).parent / ".env")
else:
    load_dotenv()

# -- 配置（从统一配置读取）--
from servers.settings import get_settings
_cfg = get_settings()
DEFAULT_TRANSPORT = _cfg.mcp_transport
DEFAULT_HOST = _cfg.mcp_host
DEFAULT_PORT = _cfg.mcp_port

# ── 启动时配置校验 ──
_cfg_issues = _cfg.validate()
if _cfg_issues:
    print("WARNING: 配置存在问题 —")
    for issue in _cfg_issues:
        print(f"  - {issue}")
    print()

from servers import mcp, __version__ as _server_ver
from servers.eda.config import EDA_GRPC_SERVER as _grpc_cfg_addr
from servers.runtime_config import set_server_address
import servers.registry_server  #  — 触发工具注册


def _setup_logging() -> None:
    """按大小轮转的文件日志，写入 %TEMP%/edi/data/log/。"""
    import tempfile as _tmp
    from datetime import datetime as _dt
    log_dir = Path(_tmp.gettempdir()) / "edi" / "data" / "log"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = f"edi_mcp_{_dt.now().strftime('%Y%m')}.log"

    handler = RotatingFileHandler(
        log_dir / log_file,
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
    root.info("EDI MCP v%s starting", _server_ver)


def _run_http_server(port: int, transport: str = "streamable-http") -> None:
    """SSE / streamable-http 模式入口。"""
    # 冻结模式无控制台时，重定向 stdout/stderr 避免 uvicorn 日志报错
    if getattr(sys, "frozen", False) and sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
        sys.stderr = open(os.devnull, "w")

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
    _grpc_host, _grpc_port = _grpc_cfg_addr.rsplit(":", 1)
    _test = socket.socket()
    _test.settimeout(1)
    _grpc_ok = _test.connect_ex((_grpc_host, int(_grpc_port))) == 0
    _test.close()

    print("=" * 50)
    print(f"  EDI MCP v{_server_ver}")
    print(f"  UI:   http://{host}:{port}/ui")
    endpoint = "/mcp" if transport == "streamable-http" else "/sse"
    print(f"  MCP:  http://{host}:{port}{endpoint}")
    print(f"  Tools: {len(tools)} loaded")
    print(f"  gRPC: {_grpc_cfg_addr} [{'ONLINE' if _grpc_ok else 'OFFLINE'}]")
    print(f"  Close window to stop")
    print("=" * 50)

    mcp.settings.host = host
    mcp.settings.port = port
    set_server_address(host, port)
    mcp.run(transport=transport)


def main() -> None:
    """CLI 入口 — 解析参数并启动 MCP 服务。"""
    parser = argparse.ArgumentParser(description="启动所有 MCP 服务")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default=DEFAULT_TRANSPORT,
        help=f"通信方式（默认: {DEFAULT_TRANSPORT}）",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"HTTP 服务端口（默认: {DEFAULT_PORT}）",
    )
    args = parser.parse_args()

    # 校验 --port 范围
    if args.port < 1 or args.port > 65535:
        print(f"错误：端口号无效（{args.port}），必须在 1-65535 之间。")
        sys.exit(1)

    if args.transport in ("sse", "streamable-http"):
        _setup_logging()
        _run_http_server(args.port, transport=args.transport)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
