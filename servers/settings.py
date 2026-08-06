"""统一配置加载 — 集中管理所有环境变量读取和默认值。

所有模块通过 get_settings() 获取配置，不直接读 os.getenv。
配置一经加载不可变（frozen dataclass），启动时校验关键字段。

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


def _read_str(name: str, default: str = "") -> str:
    raw = os.getenv(name, "").strip()
    return raw if raw else default


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
    """MCP 服务全部配置，单例不可变。

    字段按类别分组：服务器、路径、LLM、视觉、报告、工作区。
    路径类字段仅存储环境变量原始值；自动检测逻辑由各模块自行实现。
    """

    # ── 服务器 ──
    eda_grpc_server: str = field(
        default_factory=lambda: _read_str("EDA_GRPC_SERVER", "127.0.0.1:50055"))
    mcp_host: str = field(
        default_factory=lambda: _read_str("MCP_HOST", "127.0.0.1"))
    mcp_port: int = field(
        default_factory=lambda: _read_int("MCP_PORT", 50026, 1, 65535))
    mcp_transport: str = field(
        default_factory=lambda: _read_str("MCP_TRANSPORT", "sse"))

    # ── 路径（环境变量覆盖优先，空字符串 = 未设置 = 自动检测）──
    edi_path: str = field(default_factory=lambda: _read_str("EDI_PATH"))
    turbocharts_path: str = field(default_factory=lambda: _read_str("TURBOCHARTS_PATH"))
    aedt_path: str = field(default_factory=lambda: _read_str("AEDT_PATH"))

    # ── LLM / Chat ──
    llm_api_key: str = field(default_factory=lambda: _read_str("LLM_API_KEY"))
    llm_base_url: str = field(default_factory=lambda: _read_str("LLM_BASE_URL"))
    llm_model: str = field(default_factory=lambda: _read_str("LLM_MODEL"))

    # ── 视觉分析 ──
    vision_api_key: str = field(default_factory=lambda: _read_str("VISION_API_KEY"))
    vision_base_url: str = field(default_factory=lambda: _read_str("VISION_BASE_URL"))
    vision_model: str = field(default_factory=lambda: _read_str("VISION_MODEL"))
    vision_timeout: int = field(
        default_factory=lambda: _read_int("VISION_TIMEOUT_SECONDS", 45, 5, 120))
    vision_max_mb: int = field(
        default_factory=lambda: _read_int("VISION_MAX_IMAGE_MB", 10, 1, 100))

    # ── 报告渲染 ──
    report_render_url: str = field(
        default_factory=lambda: _read_str("REPORT_RENDER_URL",
                                          "http://127.0.0.1:17867/api/v1/reports/render"))
    report_timeout: int = field(
        default_factory=lambda: _read_int("REPORT_RENDER_TIMEOUT_SECONDS", 45, 5, 120))

    # ── 工作区 ──
    openclaw_workspace: str = field(
        default_factory=lambda: _read_str("OPENCLAW_WORKSPACE"))

    def validate(self) -> list[str]:
        """启动时校验关键配置，返回问题列表。"""
        issues: list[str] = []
        if ":" not in self.eda_grpc_server:
            issues.append(f"EDA_GRPC_SERVER 格式无效: {self.eda_grpc_server}")
        if self.mcp_transport not in ("sse", "stdio", "streamable-http"):
            issues.append(f"MCP_TRANSPORT 不支持: {self.mcp_transport}")
        return issues


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
