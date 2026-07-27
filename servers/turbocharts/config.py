"""Turbocharts 串行执行器 — 使用信号量限制并发进程数。"""

from __future__ import annotations

import subprocess
import sys
import threading
from collections.abc import Sequence

_TURBOCHARTS_SEMAPHORE = threading.BoundedSemaphore(1)


def run_turbocharts(
    command: Sequence[str],
    timeout_seconds: int = 120,
) -> subprocess.CompletedProcess[str]:
    """串行执行 turbocharts_app.exe，同一时间只允许一个进程。

    Args:
        command: 命令行参数序列（含可执行文件路径）。
        timeout_seconds: 超时秒数（1-600）。

    Returns:
        subprocess.CompletedProcess 对象。

    Raises:
        ValueError: timeout_seconds 不在 1-600 范围内。
        RuntimeError: 执行超时。
    """
    if timeout_seconds < 1 or timeout_seconds > 600:
        raise ValueError("timeout_seconds 必须在 1 到 600 之间")

    with _TURBOCHARTS_SEMAPHORE:
        try:
            kwargs = dict(
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
            return subprocess.run(list(command), **kwargs)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"Turbocharts 执行超时（{timeout_seconds} 秒）"
            ) from exc
