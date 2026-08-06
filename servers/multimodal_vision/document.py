"""文档访问工具 — 本地文档的 HTTP 链接 + 本地程序打开。

open_document         生成临时 HTTP 链接，PDF 在线预览、DOCX 下载。
open_local_document   使用系统默认程序打开本地文档（Word/WPS/PDF 阅读器等）。
"""

from __future__ import annotations

import logging
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse

from servers import mcp
from servers.runtime_config import get_server_base_url

load_dotenv()
_logger = logging.getLogger("multimodal.document")

_LINK_EXTENSIONS = {".pdf", ".docx"}
_LOCAL_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".ppt", ".pptx", ".txt", ".csv", ".rtf",
}
_TOKEN_TTL = 600

_DOC_TOKENS: dict[str, dict[str, Any]] = {}
_TOKEN_LOCK = threading.RLock()

_MIME_TYPES: dict[str, tuple[str, str]] = {
    ".pdf": ("application/pdf", "inline"),
    ".docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "attachment"),
}


# ═══════════════════════════════════════════════════════════
# 校验（共用）
# ═══════════════════════════════════════════════════════════

def _validate_path(file_path: str, allowed: set[str]) -> Path:
    raw = Path(file_path).expanduser()
    if not raw.is_absolute():
        raise ValueError("file_path 必须是绝对路径")
    p = raw.resolve()
    if str(p).startswith(r"\\") or str(p).startswith("//"):
        raise PermissionError(f"禁止访问网络路径: {p}")
    if not p.is_file():
        raise FileNotFoundError(f"文件不存在: {p}")
    if p.suffix.lower() not in allowed:
        raise ValueError(f"不支持的文件格式: {p.suffix}，允许: {sorted(allowed)}")
    return p


# ═══════════════════════════════════════════════════════════
# Token 管理
# ═══════════════════════════════════════════════════════════

def _cleanup_expired() -> None:
    now = time.time()
    with _TOKEN_LOCK:
        for t in [t for t, v in _DOC_TOKENS.items() if v["expires_at"] < now]:
            del _DOC_TOKENS[t]


def _base_url() -> str:
    return get_server_base_url()


def _register_token(path: Path, disposition: str) -> tuple[str, str]:
    _cleanup_expired()
    token = secrets.token_urlsafe(24)
    with _TOKEN_LOCK:
        _DOC_TOKENS[token] = {
            "path": str(path),
            "disposition": disposition,
            "expires_at": time.time() + _TOKEN_TTL,
        }
    return token, f"{_base_url()}/documents/{token}"


# ═══════════════════════════════════════════════════════════
# open_document — 临时 HTTP 链接
# ═══════════════════════════════════════════════════════════

@mcp.tool()
def open_document(
    file_path: str,
    disposition: str = "inline",
) -> dict[str, Any]:
    """为本地 PDF/DOCX 文件生成临时 HTTP 链接。

    链接 10 分钟后自动失效。不会自动打开浏览器。
    只生成链接，不自动打开。仅当用户明确要求查看文档时调用。

    Args:
        file_path: 本地 PDF/DOCX 文件绝对路径。
        disposition: inline（浏览器内预览）或 attachment（触发下载）。
    """
    try:
        path = _validate_path(file_path, _LINK_EXTENSIONS)
    except PermissionError as e:
        return {"success": False, "error_code": "INVALID_PATH", "message": str(e)}
    except FileNotFoundError as e:
        return {"success": False, "error_code": "FILE_NOT_FOUND", "message": str(e)}
    except ValueError as e:
        return {"success": False, "error_code": "UNSUPPORTED_FORMAT", "message": str(e)}

    if disposition not in ("inline", "attachment"):
        disposition = "inline"

    ext = path.suffix.lower()
    mime, _ = _MIME_TYPES.get(ext, ("application/octet-stream", "attachment"))
    token, url = _register_token(path, disposition)

    return {
        "success": True,
        "file_name": path.name,
        "mime_type": mime,
        "url": url,
        "expires_in": _TOKEN_TTL,
        "display_mode": disposition,
        "markdown_link": f"[{path.name}]({url})",
    }


# ═══════════════════════════════════════════════════════════
# open_local_document — 系统默认程序打开
# ═══════════════════════════════════════════════════════════

@mcp.tool()
def open_local_document(file_path: str) -> dict[str, Any]:
    """使用当前电脑的默认关联程序打开本地文档。

    Windows 会根据文件关联自动选择程序：.docx→Word/WPS, .pdf→默认阅读器。
    仅当用户明确要求"打开文件"时调用。不得在生成报告、查询文件或返回链接后自动调用。

    注意：打开的是 MCP 服务所在电脑上的文件（本地模式即用户电脑）。

    Args:
        file_path: 本地文档绝对路径。
    """
    try:
        path = _validate_path(file_path, _LOCAL_EXTENSIONS)
    except PermissionError as e:
        return {"success": False, "error_code": "INVALID_PATH", "message": str(e)}
    except FileNotFoundError as e:
        return {"success": False, "error_code": "DOCUMENT_NOT_FOUND", "message": str(e)}
    except ValueError as e:
        return {"success": False, "error_code": "UNSUPPORTED_DOCUMENT_TYPE", "message": str(e)}

    try:
        os.startfile(str(path))
    except OSError as exc:
        return {"success": False,
                "error_code": "DEFAULT_APPLICATION_UNAVAILABLE",
                "message": f"系统没有可用于打开该文件的默认程序: {exc}"}

    return {
        "success": True,
        "status": "OPEN_REQUESTED",
        "file_path": str(path),
        "file_type": path.suffix.lower(),
        "message": "已请求使用系统默认程序打开文件",
    }


# ═══════════════════════════════════════════════════════════
# HTTP 路由
# ═══════════════════════════════════════════════════════════

async def serve_document(request: Request) -> FileResponse | JSONResponse:
    token = request.path_params.get("token", "")
    _cleanup_expired()
    with _TOKEN_LOCK:
        entry = _DOC_TOKENS.get(token)
    if entry is None:
        return JSONResponse({"error": "not found or expired"}, status_code=404)

    path = Path(entry["path"])
    if not path.is_file():
        return JSONResponse({"error": "file gone"}, status_code=404)

    ext = path.suffix.lower()
    mime, default_disp = _MIME_TYPES.get(ext, ("application/octet-stream", "attachment"))
    disp = entry.get("disposition", default_disp)

    return FileResponse(
        path,
        media_type=mime,
        filename=path.name,
        content_disposition_type=disp,
        headers={
            "Cache-Control": "private, max-age=600",
            "X-Content-Type-Options": "nosniff",
        },
    )
