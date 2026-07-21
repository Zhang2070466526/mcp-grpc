"""Turbocharts 串行执行器 — 使用信号量限制并发进程数。"""

from __future__ import annotations

import subprocess
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
        timeout_seconds: 超时秒数。

    Returns:
        subprocess.CompletedProcess 对象。

    Raises:
        RuntimeError: 执行超时。
    """
    with _TURBOCHARTS_SEMAPHORE:
        try:
            return subprocess.run(
                list(command),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"Turbocharts 执行超时（{timeout_seconds} 秒）"
            ) from exc
