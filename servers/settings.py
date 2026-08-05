"""统一配置加载 — 集中管理环境变量读取和默认值。

使用方式：
    from servers.settings import get_settings
    s = get_settings()
    print(s.eda_grpc_server)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()
_logger = logging.getLogger("settings")


def _read_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return max(minimum, min(int(raw), maximum))
    except ValueError:
        _logger.warning("%s=%s is invalid; using %d", name, raw, default)
        return default


@dataclass(frozen=True)
class Settings:
    eda_grpc_server: str = field(default_factory=lambda: os.getenv("EDA_GRPC_SERVER", "127.0.0.1:50055"))
    mcp_host: str = field(default_factory=lambda: os.getenv("MCP_HOST", "127.0.0.1"))
    mcp_port: int = field(default_factory=lambda: _read_int("MCP_PORT", 50026, 1, 65535))
    mcp_transport: str = field(default_factory=lambda: os.getenv("MCP_TRANSPORT", "sse"))
    report_render_url: str = field(default_factory=lambda: os.getenv("REPORT_RENDER_URL", "http://127.0.0.1:17867/api/v1/reports/render"))
    report_timeout: int = field(default_factory=lambda: _read_int("REPORT_RENDER_TIMEOUT_SECONDS", 45, 5, 120))
    vision_timeout: int = field(default_factory=lambda: _read_int("VISION_TIMEOUT_SECONDS", 45, 5, 120))
    vision_max_mb: int = field(default_factory=lambda: _read_int("VISION_MAX_IMAGE_MB", 10, 1, 100))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
