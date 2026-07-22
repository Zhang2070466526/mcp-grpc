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

import threading
import time
import uuid
from typing import Any

from proto import ecserver_pb2
from servers.eda.grpc_client import call_grpc
from servers.eda.config import validate_file, validate_project_path
from servers.mcp_instance import mcp

# -- 异步仿真任务注册表 --
_sim_tasks: dict[str, dict] = {}
_sim_lock = threading.Lock()
_sim_executor = threading.Thread(target=lambda: None, daemon=True)


def _run_sim_task(task_id: str, project_path: str, log_source: str, timeout_seconds: int) -> None:
    with _sim_lock:
        _sim_tasks[task_id]["status"] = "RUNNING"
    try:
        result = call_grpc(
            ecserver_pb2.SIMULATE_PROJECT,
            {"project_path": project_path, "log_source": log_source},
            timeout_seconds,
            max_timeout_seconds=3600,
        )
        with _sim_lock:
            _sim_tasks[task_id]["status"] = "SUCCEEDED" if result.get("success") else "FAILED"
            _sim_tasks[task_id]["result"] = result
            _sim_tasks[task_id]["finished_at"] = time.time()
    except Exception as exc:
        with _sim_lock:
            _sim_tasks[task_id]["status"] = "FAILED"
            _sim_tasks[task_id]["error"] = str(exc)
            _sim_tasks[task_id]["finished_at"] = time.time()


@mcp.tool()
def start_simulation_async(
    project_path: str,
    log_source: str = "mcp_client",
    timeout_seconds: int = 600,
) -> dict[str, Any]:
    """启动异步仿真，立即返回 task_id。通过 get_simulation_async_status 查询进度。

    Args:
        project_path: EDA 服务所在机器上的 .epp 工程文件绝对路径。
        log_source: 调用方日志标识。
        timeout_seconds: 最长等待秒数，默认 600。
    """
    resolved_path = validate_project_path(project_path)
    task_id = str(uuid.uuid4())
    with _sim_lock:
        _sim_tasks[task_id] = {
            "task_id": task_id,
            "operation": "simulate_project",
            "project_path": resolved_path,
            "status": "QUEUED",
            "started_at": time.time(),
            "result": None,
            "error": None,
            "finished_at": None,
        }
    t = threading.Thread(
        target=_run_sim_task,
        args=(task_id, resolved_path, log_source, timeout_seconds),
        daemon=True,
    )
    t.start()
    return {"task_id": task_id, "status": "QUEUED"}


@mcp.tool()
def get_simulation_async_status(task_id: str) -> dict[str, Any]:
    """查询异步仿真任务状态。"""
    with _sim_lock:
        task = _sim_tasks.get(task_id)
    if task is None:
        return {"task_id": task_id, "status": "UNKNOWN"}
    return {
        "task_id": task_id,
        "status": task["status"],
        "started_at": task["started_at"],
        "finished_at": task.get("finished_at"),
        "error": task.get("error"),
    }


@mcp.tool()
def get_simulation_async_result(task_id: str) -> dict[str, Any]:
    """获取已完成的异步仿真结果。"""
    with _sim_lock:
        task = _sim_tasks.get(task_id)
    if task is None:
        return {"task_id": task_id, "status": "UNKNOWN"}
    if task["status"] in ("QUEUED", "RUNNING"):
        return {"task_id": task_id, "status": task["status"], "message": "Task not finished yet"}
    return {
        "task_id": task_id,
        "status": task["status"],
        "result": task.get("result"),
        "error": task.get("error"),
    }


@mcp.tool()
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
        max_timeout_seconds=3600,
    )


@mcp.tool()
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
    resolved_netlist = validate_file(netlist_path)
    return call_grpc(
        ecserver_pb2.CALL_SIMULATION_CONTROLLER,
        {"netlist_path": resolved_netlist, "ads_path": ads_path},
        timeout_seconds,
        max_timeout_seconds=3600,
    )
