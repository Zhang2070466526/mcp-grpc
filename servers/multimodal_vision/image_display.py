"""图片显示 — 纯 MCP ImageContent，不调模型，不复制文件。"""

from __future__ import annotations

import base64
import logging
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from mcp.types import ImageContent, TextContent
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse

from servers.mcp_instance import mcp
from servers.multimodal_vision.validators import validate_image_path

load_dotenv()
_logger = logging.getLogger("multimodal.display")

_MAX_NATIVE_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB
_TOKEN_TTL = 600

_IMAGE_TOKENS: dict[str, dict[str, Any]] = {}
_TOKEN_LOCK = threading.RLock()

_MIME_TYPES: dict[str, str] = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp",
}


# ═══════════════════════════════════════════════════════════
# show_image
# ═══════════════════════════════════════════════════════════

@mcp.tool(structured_output=False)
def show_image(image_path: str) -> list[Any]:
    """读取本地图片，返回标准 MCP ImageContent。

    如果客户端无法渲染 ImageContent，直接报告"客户端不支持"，停止处理。
    不得通过 Read、Exec、Write、Canvas、HTML 或 MEDIA 文本再次尝试显示。
    不得自动调用工作区复制工具。

    Args:
        image_path: 图片文件绝对路径。
    """
    path = validate_image_path(image_path)

    size = path.stat().st_size
    if size > _MAX_NATIVE_IMAGE_SIZE:
        return [
            TextContent(
                type="text",
                text=(
                    "图片文件较大（>10 MB），未内嵌到 MCP 返回内容中。\n\n"
                    f"原始路径：{path}\n\n"
                    "可以在本机查看，或明确要求复制到 OpenClaw 工作区。"
                ),
            ),
        ]

    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    mime = _MIME_TYPES.get(path.suffix.lower(), "application/octet-stream")

    return [
        TextContent(
            type="text",
            text=(
                "图片内容已返回给客户端。能否直接显示取决于客户端的图片渲染和文件访问策略。\n"
                f"原始路径：{path}\n"
                "如果客户端限制工作区外文件访问，可要求用户将图片复制到 OpenClaw 工作区。\n"
                "不要自行调用 Read、Exec 或 filePath 读取原始文件。"
            ),
        ),
        ImageContent(type="image", data=encoded, mimeType=mime),
    ]


# ═══════════════════════════════════════════════════════════
# HTTP Token — 供 Chat 界面渲染图片
# ═══════════════════════════════════════════════════════════

def _base_url() -> str:
    host = os.getenv("MCP_HOST", "127.0.0.1")
    port = os.getenv("MCP_PORT", "50026")
    return f"http://{host}:{port}"


def register_image_url(img_path: str) -> str:
    p = validate_image_path(img_path)
    _cleanup_expired()
    token = secrets.token_urlsafe(24)
    with _TOKEN_LOCK:
        _IMAGE_TOKENS[token] = {"path": str(p), "expires_at": time.time() + _TOKEN_TTL}
    return f"{_base_url()}/images/{token}"


def _cleanup_expired() -> None:
    now = time.time()
    with _TOKEN_LOCK:
        for t in [t for t, v in _IMAGE_TOKENS.items() if v["expires_at"] < now]:
            del _IMAGE_TOKENS[t]


# ═══════════════════════════════════════════════════════════
# HTTP 路由
# ═══════════════════════════════════════════════════════════

async def serve_image(request: Request) -> FileResponse | JSONResponse:
    token = request.path_params.get("token", "")
    _cleanup_expired()
    with _TOKEN_LOCK:
        entry = _IMAGE_TOKENS.get(token)
    if entry is None:
        return JSONResponse({"error": "not found or expired"}, status_code=404)

    image_path = Path(entry["path"])
    if not image_path.is_file():
        return JSONResponse({"error": "file gone"}, status_code=404)

    ext = image_path.suffix.lower()
    media_map = {**{k: v for k, v in _MIME_TYPES.items()},
                 ".svg": "image/svg+xml"}
    return FileResponse(
        image_path,
        media_type=media_map.get(ext, "application/octet-stream"),
        filename=image_path.name,
        content_disposition_type="inline",
        headers={"Cache-Control": "private, max-age=600", "X-Content-Type-Options": "nosniff"},
    )
