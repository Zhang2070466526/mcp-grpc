"""EDA 分析工具。

view_project_netlist  查看/导出工程网表
capture_schematic     截取原理图为图片
"""

from __future__ import annotations

from typing import Any

from proto import ecserver_pb2
from servers.eda.grpc_client import call_grpc
from servers.eda.config import validate_project_path


def view_project_netlist(
    project_path: str,
    timeout_seconds: int = 60,
) -> dict[str, Any]:
    """查看 EDA .epp 工程的网表，返回网表文件路径。

    Args:
        project_path: EDA 服务所在机器上的 .epp 工程文件绝对路径。
        timeout_seconds: 最长等待时间，默认 60 秒。
    """
    resolved_path = validate_project_path(project_path)
    return call_grpc(
        ecserver_pb2.VIEW_PROJECT_NETLIST,
        {"project_path": resolved_path},
        timeout_seconds,
    )


def capture_schematic(
    project_path: str,
    img_path: str,
    timeout_seconds: int = 60,
) -> dict[str, Any]:
    """截取 EDA 工程原理图为图片。

    Args:
        project_path: EDA 服务所在机器上的 .epp 工程文件绝对路径。
        img_path: 输出图片路径，支持 PNG/JPG 等。
        timeout_seconds: 最长等待时间，默认 60 秒。
    """
    resolved_path = validate_project_path(project_path)
    return call_grpc(
        ecserver_pb2.CAPTURE_SCHEMATIC,
        {"project_path": resolved_path, "img_path": img_path},
        timeout_seconds,
    )
