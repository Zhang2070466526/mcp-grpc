"""MCP 图片工具 — show_image 始终注册，工作区未配置时返回本地路径供用户查看。

show_image
  - OPENCLAW_WORKSPACE 有效 → 复制到 media/eda/ → 返回 MEDIA:
  - 未配置/无效/复制失败 → 返回原始路径，让用户在本机打开

GET /images/{token}   临时图片访问路由（10 分钟过期）。

安全限制：
  - 只允许 PNG / JPG / GIF / WebP / BMP / SVG
  - 单张最大 20 MB
  - 禁止 UNC 网络路径
"""

from __future__ import annotations

import logging
import os
import secrets
import shutil
import threading
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from mcp.types import TextContent
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse

from servers.mcp_instance import mcp

load_dotenv()

_logger = logging.getLogger("image_tools")

_ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}
_MAX_IMAGE_SIZE = 20 * 1024 * 1024       # 20 MB，工作区复制上限
_TOKEN_TTL = 600                    # HTTP Token 有效期 10 分钟
_OPENCLAW_CACHE_TTL = 24 * 60 * 60  # 工作区缓存 24 小时

_IMAGE_TOKENS: dict[str, dict[str, Any]] = {}
_TOKEN_LOCK = threading.RLock()


# ═══════════════════════════════════════════════════════════
# 图片校验
# ═══════════════════════════════════════════════════════════

def _validate_image_path(image_path: str) -> Path:
    """校验图片路径，通过则返回 resolved Path。"""
    path = Path(image_path).expanduser().resolve()

    path_str = str(path)
    if path_str.startswith(r"\\") or path_str.startswith("//"):
        raise PermissionError(f"禁止访问网络路径: {path}")

    if not path.is_file():
        raise FileNotFoundError(f"图片不存在: {path}")

    if path.suffix.lower() not in _ALLOWED_EXTENSIONS:
        raise ValueError(
            f"不支持的图片格式: {path.suffix}，"
            f"请使用 {', '.join(sorted(_ALLOWED_EXTENSIONS))}"
        )

    return path


# ═══════════════════════════════════════════════════════════
# OpenClaw 工作区（每次调用时检查）
# ═══════════════════════════════════════════════════════════

def _get_openclaw_media_dir() -> Path | None:
    """解析 OPENCLAW_WORKSPACE，有效则返回 media/eda 路径，否则 None。"""
    value = os.getenv("OPENCLAW_WORKSPACE", "").strip()
    if not value:
        return None

    try:
        workspace = Path(value).expanduser().resolve()
        if not workspace.is_dir():
            _logger.warning("OpenClaw image display unavailable: workspace not a directory")
            return None

        media_dir = workspace / "media" / "eda"
        media_dir.mkdir(parents=True, exist_ok=True)
        return media_dir

    except OSError as exc:
        _logger.warning("OpenClaw image display unavailable: %s", exc)
        return None


def _cleanup_openclaw_media_cache(media_dir: Path) -> None:
    """删除超过 24 小时的缓存图片。"""
    expire_before = time.time() - _OPENCLAW_CACHE_TTL
    try:
        entries = list(media_dir.iterdir())
    except OSError:
        return
    for item in entries:
        try:
            if (
                item.is_file()
                and item.suffix.lower() in _ALLOWED_EXTENSIONS
                and item.stat().st_mtime < expire_before
            ):
                item.unlink()
        except OSError:
            continue


def _stage_image_for_openclaw(source: Path, media_dir: Path) -> Path | None:
    """复制图片到工作区，返回缓存路径。超过 20 MB 返回 None。"""
    if source.stat().st_size > _MAX_IMAGE_SIZE:
        _logger.warning("Image too large for workspace: %s", source)
        return None
    _cleanup_openclaw_media_cache(media_dir)

    safe_name = "".join(
        c if c.isalnum() or c in "._-" else "_"
        for c in source.name
    )
    target = media_dir / f"{secrets.token_hex(4)}_{safe_name}"
    shutil.copyfile(source, target)
    return target


# ═══════════════════════════════════════════════════════════
# HTTP Token（图表工具和其他 MCP 客户端使用）
# ═══════════════════════════════════════════════════════════

def _base_url() -> str:
    host = os.getenv("MCP_HOST", "127.0.0.1")
    port = os.getenv("MCP_PORT", "50026")
    return f"http://{host}:{port}"


def register_image_url(img_path: str) -> str:
    """将图片路径注册为临时 HTTP Token，返回可访问的 URL。"""
    p = Path(img_path).expanduser().resolve()
    if not p.is_file():
        return ""
    _cleanup_expired()
    token = secrets.token_urlsafe(24)
    with _TOKEN_LOCK:
        _IMAGE_TOKENS[token] = {
            "path": str(p),
            "expires_at": time.time() + _TOKEN_TTL,
        }
    return f"{_base_url()}/images/{token}"


def _cleanup_expired() -> None:
    now = time.time()
    with _TOKEN_LOCK:
        expired = [t for t, v in _IMAGE_TOKENS.items() if v["expires_at"] < now]
        for t in expired:
            del _IMAGE_TOKENS[t]


# ═══════════════════════════════════════════════════════════
# 返回内容构建
# ═══════════════════════════════════════════════════════════

def _build_media_response(cached_path: Path) -> list[Any]:
    return [
        TextContent(
            type="text",
            text=(
                "图片已准备完成。\n"
                "请原样输出下面的 MEDIA 行，"
                "不要读取图片，不要调用其他工具：\n\n"
                f"MEDIA:{cached_path}"
            ),
        )
    ]


def _build_local_view_response(path: Path) -> list[Any]:
    return [
        TextContent(
            type="text",
            text=(
                "图片文件已准备好。\n"
                f"本地路径：{path}\n\n"
                "如果当前客户端未自动显示，可以在本机打开该文件查看。\n"
                "这是正常的可选显示结果，无需重试或检查配置。"
            ),
        )
    ]


# ═══════════════════════════════════════════════════════════
# MCP 工具 — 始终注册
# ═══════════════════════════════════════════════════════════

@mcp.tool(structured_output=False)
def show_image(image_path: str) -> list[Any]:
    """显示本地图片

    配置了 OpenClaw 工作区时复制到 media/eda/ 并返回 MEDIA: 行。
    未配置时返回本地路径供用户本机查看。
    不要重试，不要检查环境变量、配置文件、服务进程或端口。

    Args:
        image_path: 图片文件绝对路径。
    """
    path = _validate_image_path(image_path)
    media_dir = _get_openclaw_media_dir()

    if media_dir is None:
        return _build_local_view_response(path)

    try:
        cached_path = _stage_image_for_openclaw(path, media_dir)
    except OSError as exc:
        _logger.warning("Failed to stage image for OpenClaw: %s", exc)
        return _build_local_view_response(path)

    if cached_path is None:
        return _build_local_view_response(path)

    return _build_media_response(cached_path)


# ═══════════════════════════════════════════════════════════
# HTTP 路由
# ═══════════════════════════════════════════════════════════

async def serve_image(request: Request) -> FileResponse | JSONResponse:
    """GET /images/{token} — 临时图片访问路由。"""
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
    media_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
        ".svg": "image/svg+xml",
    }

    return FileResponse(
        image_path,
        media_type=media_map.get(ext, "application/octet-stream"),
        filename=image_path.name,
        content_disposition_type="inline",
        headers={
            "Cache-Control": "private, max-age=600",
            "X-Content-Type-Options": "nosniff",
        },
    )
