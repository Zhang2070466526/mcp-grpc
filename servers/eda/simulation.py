r"""EDA 仿真工具。

simulate_project              对 .epp 工程执行仿真，等待结果返回
simulate_netlist_with_ads    基于网表文件调用 ADS 仿真控制器

自然语言使用示例：
  帮我对 EDA 工程 C:\...\EDI_TEST.epp 执行仿真
  帮我对 C:\...\netlist.log 执行 ADS 仿真，超时设为 300 秒
  帮我仿真这个工程，日志来源标记为 my_test

参数说明：
  project_path     EDA 服务所在机器上的 .epp 工程文件绝对路径
  netlist_path     网表文件路径（simulate_netlist_with_ads）
  log_source       调用方日志标识，默认 "mcp_client"
  ads_path         ADS 安装路径，为空则自动判断
  timeout_seconds  最长等待秒数，无上限，默认 600（仿真）/ 120（控制器）
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


def simulate_netlist_with_ads(
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
