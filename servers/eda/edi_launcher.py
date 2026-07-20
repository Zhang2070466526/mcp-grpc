r"""EDA 启动工具。

launch_edi     启动 EDI 客户端应用程序，自动等待 gRPC 服务就绪。
               如果 EDI 已在运行则跳过启动，避免重复。

自然语言使用示例：
  帮我启动 EDI
  帮我启动 EDI 客户端，等 60 秒确认 gRPC 就绪
  检查一下 EDI 是否已经在运行

参数说明：
  edi_path         EDI.exe 路径，默认使用 .env 中配置的 EDI_PATH
  wait_for_grpc    是否等待 gRPC 服务端口就绪，默认 True
  wait_timeout     等待 gRPC 就绪的超时秒数，默认 30 秒
"""

from __future__ import annotations

import socket
import subprocess
import time
from pathlib import Path
from typing import Any

from servers.eda.config import EDA_GRPC_SERVER, EDI_PATH


def launch_edi(
    edi_path: str = "",
    wait_for_grpc: bool = True,
    wait_timeout: int = 30,
) -> dict[str, Any]:
    """启动 EDI 客户端应用程序，等待 gRPC 服务就绪。

    Args:
        edi_path: EDI.exe 路径，默认使用配置的 EDI_PATH。
        wait_for_grpc: 是否等待 gRPC 服务端口就绪，默认 True。
        wait_timeout: 等待 gRPC 就绪的超时秒数，默认 30 秒。
    """
    exe = edi_path or EDI_PATH
    exe_path = Path(exe).expanduser()
    if not exe_path.is_file():
        raise FileNotFoundError(f"EDI.exe 不存在: {exe_path}")

    host, port_str = EDA_GRPC_SERVER.rsplit(":", 1)
    port = int(port_str)
    already_running = False
    try:
        with socket.create_connection((host, port), timeout=1):
            already_running = True
    except OSError:
        pass

    if already_running:
        return {
            "success": True,
            "message": f"EDI 已在运行（gRPC {EDA_GRPC_SERVER} 已就绪）",
            "edi_path": str(exe_path),
            "grpc_server": EDA_GRPC_SERVER,
        }

    try:
        subprocess.Popen(
            [str(exe_path)],
            cwd=str(exe_path.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        raise RuntimeError(f"无法启动 EDI.exe: {exc}") from exc

    result: dict[str, Any] = {
        "success": True,
        "message": "EDI 已启动",
        "edi_path": str(exe_path),
        "grpc_server": EDA_GRPC_SERVER,
    }

    if wait_for_grpc:
        started = time.monotonic()
        while time.monotonic() - started < wait_timeout:
            try:
                with socket.create_connection((host, port), timeout=1):
                    result["grpc_ready"] = True
                    result["message"] += (
                        f"，gRPC 服务已就绪（{time.monotonic() - started:.1f}s）"
                    )
                    return result
            except OSError:
                time.sleep(1)

        result["grpc_ready"] = False
        result["message"] += "，gRPC 服务未在规定时间内就绪"

    return result
