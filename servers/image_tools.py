"""MCP 图片工具。

show_image              返回标准 MCP ImageContent，不复制文件，不依赖 OpenClaw。
copy_image_to_workspace 条件注册，复制到 media/edi/mcp-cache/，返回 openclaw_attachment。

GET /images/{token}     临时图片访问路由（10 分钟过期）。
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import secrets
import shutil
import threading
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from mcp.types import ImageContent, TextContent
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse

from servers.mcp_instance import mcp

load_dotenv()

_logger = logging.getLogger("image_tools")

_ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
_MAX_NATIVE_IMAGE_SIZE = 10 * 1024 * 1024       # 10 MB，Base64 原生图片上限
_MAX_WORKSPACE_IMAGE_SIZE = 40 * 1024 * 1024    # 40 MB，工作区复制上限
_TOKEN_TTL = 600
_OPENCLAW_CACHE_TTL = 24 * 60 * 60

_IMAGE_TOKENS: dict[str, dict[str, Any]] = {}
_TOKEN_LOCK = threading.RLock()

_MIME_TYPES: dict[str, str] = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp",
}


# ═══════════════════════════════════════════════════════════
# 图片校验
# ═══════════════════════════════════════════════════════════

def _validate_image_path(image_path: str) -> Path:
    """校验图片路径，通过则返回 resolved Path。"""
    path = Path(image_path).expanduser().resolve()
    if str(path).startswith(r"\\") or str(path).startswith("//"):
        raise PermissionError(f"禁止访问网络路径: {path}")
    if not path.is_file():
        raise FileNotFoundError(f"图片不存在: {path}")
    if path.suffix.lower() not in _ALLOWED_EXTENSIONS:
        raise ValueError(f"不支持的图片格式: {path.suffix}")
    return path


# ═══════════════════════════════════════════════════════════
# show_image — 纯 MCP ImageContent，不复制文件
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
    path = _validate_image_path(image_path)

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
# copy_image_to_workspace — 工作区复制
# ═══════════════════════════════════════════════════════════

def _get_openclaw_workspace() -> Path | None:
    """读取 OPENCLAW_WORKSPACE，仅当有效时返回路径。"""
    value = os.getenv("OPENCLAW_WORKSPACE", "").strip()
    if not value:
        return None
    try:
        w = Path(value).expanduser().resolve()
        if not w.is_dir():
            _logger.warning("OPENCLAW_WORKSPACE is invalid; copy_image_to_workspace disabled")
            return None
        return w
    except OSError:
        _logger.warning("OPENCLAW_WORKSPACE is invalid; copy_image_to_workspace disabled")
        return None

OPENCLAW_WORKSPACE_PATH = _get_openclaw_workspace()

if OPENCLAW_WORKSPACE_PATH is not None:
    _logger.info("copy_image_to_workspace enabled")
else:
    _logger.info("OPENCLAW_WORKSPACE not configured; copy_image_to_workspace disabled")


def _copy_to_workspace(source: Path, workspace: Path) -> str:
    """复制图片到 workspace/media/edi/，返回目标路径。超过 40 MB 返回空。"""
    if source.stat().st_size > _MAX_WORKSPACE_IMAGE_SIZE:
        return ""

    media_dir = workspace / "media" / "edi" / "mcp-cache"
    media_dir.mkdir(parents=True, exist_ok=True)

    # 清理过期缓存
    expire_before = time.time() - _OPENCLAW_CACHE_TTL
    try:
        for item in media_dir.iterdir():
            try:
                if item.is_file() and item.suffix.lower() in _ALLOWED_EXTENSIONS and item.stat().st_mtime < expire_before:
                    item.unlink()
            except OSError:
                continue
    except OSError:
        pass

    # 基于源路径哈希生成稳定文件名
    path_hash = hashlib.md5(str(source.resolve()).encode()).hexdigest()[:8]
    safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in source.stem)
    target = media_dir / f"{safe_name}_{path_hash}{source.suffix}"
    shutil.copyfile(source, target)
    return str(target)


def copy_image_to_workspace(image_path: str) -> dict[str, Any]:
    """复制图片到 OpenClaw 工作区 media/edi，返回绝对路径供结构化附件发送。

    仅当用户明确要求复制到 OpenClaw 工作区时才调用。
    需要 MCP 服务配置 OPENCLAW_WORKSPACE，未配置时不复制，只返回配置提示。
    不得猜测默认工作区，不得使用 Read 或 Exec 手动复制。
    不要在 show_image 成功后自动调用。

    Args:
        image_path: 图片文件绝对路径。
    """
    path = _validate_image_path(image_path)

    workspace = OPENCLAW_WORKSPACE_PATH
    if workspace is None:
        return {
            "success": True,
            "copied": False,
            "status": "WORKSPACE_NOT_CONFIGURED",
            "retryable": False,
            "source_path": str(path),
            "message": (
                "未配置 OPENCLAW_WORKSPACE，未执行图片复制。"
                "请在 MCP 服务的 .env 中配置 OPENCLAW_WORKSPACE 并重启服务，"
                "或由用户手动复制图片到工作区media目录下。"
            ),
        }

    size = path.stat().st_size
    if size > _MAX_WORKSPACE_IMAGE_SIZE:
        return {
            "success": True,
            "copied": False,
            "status": "IMAGE_TOO_LARGE",
            "retryable": False,
            "source_path": str(path),
            "message": "图片超过工作区复制大小限制（40 MB），可以直接在本机查看。",
        }

    try:
        target = _copy_to_workspace(path, workspace)
    except OSError as exc:
        _logger.warning("Failed to copy to workspace: %s", exc)
        return {
            "success": False,
            "copied": False,
            "status": "COPY_FAILED",
            "retryable": False,
            "source_path": str(path),
            "message": "图片复制到工作区失败，可以直接查看原始文件。",
        }

    if not target:
        return {
            "success": True,
            "copied": False,
            "status": "IMAGE_TOO_LARGE",
            "retryable": False,
            "source_path": str(path),
            "message": "图片超过工作区复制大小限制（40 MB），可以直接在本机查看。",
        }

    return {
        "success": True,
        "copied": True,
        "displayed": False,
        "status": "COPIED",
        "retryable": False,
        "source_path": str(path),
        "workspace_path": str(workspace),
        "image_path": target,
        "openclaw_attachment": {"filePath": target},
        "message": (
            "图片已复制到工作区。"
            "请使用 OpenClaw 原生消息工具的 filePath 或 media 结构化字段发送图片。"
            "不要在普通文本中输出 MEDIA 行。"
        ),
    }


# ═══════════════════════════════════════════════════════════
# HTTP Token（保留供图表工具或其他客户端使用）
# ═══════════════════════════════════════════════════════════

def _base_url() -> str:
    host = os.getenv("MCP_HOST", "127.0.0.1")
    port = os.getenv("MCP_PORT", "50026")
    return f"http://{host}:{port}"


def register_image_url(img_path: str) -> str:
    p = _validate_image_path(img_path)
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


# ═══════════════════════════════════════════════════════════
# 条件注册 copy_image_to_workspace
# ═══════════════════════════════════════════════════════════

if OPENCLAW_WORKSPACE_PATH is not None:
    mcp.tool()(copy_image_to_workspace)
    _logger.info("Image mode: native ImageContent; workspace copy enabled")
else:
    _logger.info("Image mode: native ImageContent only; workspace copy disabled")
