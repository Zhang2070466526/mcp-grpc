r"""Web 路由 — /health, /chat, /ui, /tools/list, /。

职责：
  - 请求解析与格式校验
  - 委托 ChatService 处理聊天逻辑
  - /health 健康检查、/ui 静态页面、/tools/list 工具列表
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

from servers import mcp, __version__ as _ver
from servers.chat.service import ChatService
from servers.eda.config import EDA_GRPC_SERVER, TURBOCHARTS_PATH

import sys as _sys
if getattr(_sys, "frozen", False):
    _CLIENT_HTML_PATH = Path(_sys._MEIPASS) / "servers" / "chat" / "index.html"
else:
    _CLIENT_HTML_PATH = Path(__file__).resolve().parent / "index.html"


async def _check_tcp(endpoint: str) -> bool:
    try:
        host, port_text = endpoint.rsplit(":", 1)
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, int(port_text)),
            timeout=0.5,
        )
        writer.close()
        await writer.wait_closed()
        return True
    except (OSError, ValueError, asyncio.TimeoutError):
        return False


# ── 静态页面 ──

async def ui_page(request: Request):
    if _CLIENT_HTML_PATH.is_file():
        return HTMLResponse(_CLIENT_HTML_PATH.read_text(encoding="utf-8"))
    return HTMLResponse("<h2>chat_client.html not found</h2>", status_code=404)


# ── 工具列表 ──

async def tool_list(request: Request):
    tools = [{"name": t.name, "description": t.description or ""}
             for t in mcp._tool_manager._tools.values()]
    return JSONResponse(tools)


# ── 健康检查 ──

async def health_check(request: Request):
    eda_ready = await _check_tcp(EDA_GRPC_SERVER)
    turbocharts_ready = bool(TURBOCHARTS_PATH) and Path(TURBOCHARTS_PATH).is_file()
    return JSONResponse({
        "status": "ok" if eda_ready else "degraded",
        "version": _ver,
        "mcp_ready": True,
        "eda_grpc_ready": eda_ready,
        "turbocharts_ready": turbocharts_ready,
        "eda_grpc_server": EDA_GRPC_SERVER,
    })


# ── 聊天 ──

async def chat_endpoint(request: Request):
    """POST /chat — 委托 ChatService 处理多轮工具调用闭环。

    请求: {"session_id": "...", "message": "..."}
    返回: {"success": bool, "reply": "...", "activities": [...], "context": {...}}
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON body"}, status_code=400)

    if not isinstance(body, dict):
        return JSONResponse({"error": "body must be an object"}, status_code=400)

    session_id = body.get("session_id", "")
    message = body.get("message", "")

    if not isinstance(session_id, str):
        return JSONResponse({"error": "session_id must be a string"}, status_code=400)
    if not isinstance(message, str):
        return JSONResponse({"error": "message must be a string"}, status_code=400)

    session_id = session_id.strip()
    message = message.strip()

    if not message:
        return JSONResponse({"error": "message required"}, status_code=400)

    response = await ChatService.instance().chat(session_id, message)
    return JSONResponse(response.to_dict())
