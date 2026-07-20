"""EDA 仿真工具。

simulate_project              执行工程仿真
call_simulation_controller    调用 ADS 仿真控制器
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from proto import ecserver_pb2
from servers.eda.grpc_client import call_grpc
from servers.eda.config import validate_project_path


def simulate_project(
    project_path: str,
    log_source: str = "mcp_client",
    timeout_seconds: int = 600,
) -> dict[str, Any]:
    """对 EDA .epp 工程执行仿真，等待仿真完成并返回结果。

    Args:
        project_path: EDA 服务所在机器上的 .epp 工程文件绝对路径。
        log_source: 调用方日志标识。
        timeout_seconds: 最长等待时间，默认 600 秒。
    """
    resolved_path = validate_project_path(project_path)
    return call_grpc(
        ecserver_pb2.SIMULATE_PROJECT,
        {"project_path": resolved_path, "log_source": log_source},
        timeout_seconds,
    )


def call_simulation_controller(
    netlist_path: str,
    ads_path: str = "",
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    """调用 ADS 仿真控制器。

    Args:
        netlist_path: 网表文件路径。
        ads_path: ADS 安装路径，为空则自动判断。
        timeout_seconds: 最长等待时间，默认 120 秒。
    """
    netlist = Path(netlist_path).expanduser()
    if not netlist.is_file():
        raise FileNotFoundError(f"网表文件不存在: {netlist}")
    return call_grpc(
        ecserver_pb2.CALL_SIMULATION_CONTROLLER,
        {"netlist_path": str(netlist.resolve()), "ads_path": ads_path},
        timeout_seconds,
    )
