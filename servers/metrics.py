"""运行时指标收集 — 供 /metrics 端点输出 Prometheus 格式。

记录工具调用次数 / 失败次数 / 耗时，用于可观测性监控。
"""

from __future__ import annotations

import threading

# 工具调用指标：{tool_name: {"count", "errors", "total_ms"}}
_tool_metrics: dict[str, dict] = {}
_metrics_lock = threading.Lock()


def record_tool_call(tool_name: str, success: bool, elapsed_ms: float) -> None:
    """记录一次工具调用（次数、失败数、耗时）。"""
    with _metrics_lock:
        m = _tool_metrics.setdefault(tool_name, {"count": 0, "errors": 0, "total_ms": 0.0})
        m["count"] += 1
        if not success:
            m["errors"] += 1
        m["total_ms"] += elapsed_ms


def get_tool_metrics() -> dict[str, dict]:
    """返回工具调用指标快照（浅拷贝，脱离锁）。"""
    with _metrics_lock:
        return {name: dict(m) for name, m in _tool_metrics.items()}
