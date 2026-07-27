"""MCP 图片工具 — 读取本地图片，通过临时 HTTP 路由返回可渲染的 Markdown URL。

show_image    读取本地图片，生成临时 HTTP 令牌，返回 Markdown URL + ImageContent。
               对 OpenClaw WebChat 真正起作用的是 image_url。

GET /images/{token}   临时图片访问路由（10 分钟过期，随机令牌，不暴露真实路径）。

安全限制：
  - 只允许 PNG / JPG / GIF / WebP
  - 单张最大 100 MB
  - 禁止 UNC 网络路径
  - 令牌 10 分钟过期
  - 禁止目录浏览
"""

from __future__ import annotations

import os
import secrets
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from mcp.server.fastmcp import Image
from mcp.types import TextContent
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse

from servers.mcp_instance import mcp

load_dotenv()

_ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
_MAX_IMAGE_SIZE = 100 * 1024 * 1024  # 100 MB
_TOKEN_TTL = 600  # 令牌有效期 10 分钟

# 临时图片令牌注册表: {token: {"path": str, "expires_at": float}}
_IMAGE_TOKENS: dict[str, dict[str, Any]] = {}


def _base_url() -> str:
    host = os.getenv("MCP_HOST", "127.0.0.1")
    port = os.getenv("MCP_PORT", "50026")
    return f"http://{host}:{port}"


def _cleanup_expired() -> None:
    now = time.time()
    expired = [t for t, v in _IMAGE_TOKENS.items() if v["expires_at"] < now]
    for t in expired:
        del _IMAGE_TOKENS[t]


@mcp.tool(structured_output=False)
def show_image(image_path: str) -> list[Any]:
    """读取本地图片，生成临时 HTTP 链接，用于在客户端中显示图片。

    适用于 capture_schematic / turbocharts_convert / compare_simulation_results
    等工具输出的图片路径。调用成功后，必须在最终回复中原样输出返回的
    markdown 字段，不要只描述图片名称。

    Args:
        image_path: 图片文件的绝对路径。
    """
    path = Path(image_path).expanduser().resolve()

    path_str = str(path)
    if path_str.startswith(r"\\") or path_str.startswith("//"):
        raise PermissionError(f"禁止访问网络路径: {path}")

    if not path.is_file():
        raise FileNotFoundError(f"图片不存在: {path}")

    ext = path.suffix.lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise ValueError(
            f"不支持的图片格式: {ext}，"
            f"请使用 {', '.join(sorted(_ALLOWED_EXTENSIONS))}"
        )

    size = path.stat().st_size
    if size > _MAX_IMAGE_SIZE:
        raise ValueError(
            f"图片大小为 {size / 1024 / 1024:.1f} MB，"
            f"超过 {_MAX_IMAGE_SIZE // 1024 // 1024} MB 限制"
        )

    _cleanup_expired()

    token = secrets.token_urlsafe(24)
    _IMAGE_TOKENS[token] = {
        "path": path_str,
        "expires_at": time.time() + _TOKEN_TTL,
    }

    image_url = f"{_base_url()}/images/{token}"
    markdown = f"![{path.name}]({image_url})"

    return [
        TextContent(
            type="text",
            text=(
                f"图片已生成，请在回复中原样输出以下 Markdown：\n\n"
                f"{markdown}\n\n"
                f"（链接有效期 {_TOKEN_TTL // 60} 分钟）"
            ),
        ),
        Image(path=path),
    ]


async def serve_image(request: Request) -> FileResponse | JSONResponse:
    """GET /images/{token} — 临时图片访问路由。"""
    token = request.path_params.get("token", "")

    _cleanup_expired()

    entry = _IMAGE_TOKENS.get(token)
    if entry is None:
        return JSONResponse({"error": "not found or expired"}, status_code=404)

    image_path = Path(entry["path"])
    if not image_path.is_file():
        return JSONResponse({"error": "file gone"}, status_code=404)

    ext = image_path.suffix.lower()
    media_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }

    return FileResponse(
        image_path,
        media_type=media_map.get(ext, "application/octet-stream"),
        filename=image_path.name,
        headers={
            "Cache-Control": "private, max-age=600",
            "X-Content-Type-Options": "nosniff",
        },
    )
