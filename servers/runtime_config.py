"""运行时配置 — CLI 参数覆盖后的统一地址。"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ServerAddress:
    host: str = "127.0.0.1"
    port: int = 50026


_address = ServerAddress()
_lock = threading.Lock()


def set_server_address(host: str, port: int) -> None:
    """在 start_servers.py 确定最终 host/port 后调用。"""
    with _lock:
        _address.host = host
        _address.port = port


def get_server_base_url() -> str:
    """返回当前 HTTP 服务的 base URL，供图片 Token 等功能使用。"""
    with _lock:
        host = _address.host
        port = _address.port
    public_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    return f"http://{public_host}:{port}"


def build_file_link(path: str, label: str = "打开文件") -> dict:
    """为本地文件生成 file:// URI 和 Markdown 链接。

    只在 MCP 服务与客户端同机时可靠。
    """
    p = Path(path).resolve()
    uri = p.as_uri()
    return {
        "file_uri": uri,
        "markdown_link": f"[{label}]({uri})",
    }
