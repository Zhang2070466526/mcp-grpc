r"""EDA 仿真工具。

simulate_project              对 .epp 工程执行仿真，等待结果返回
simulate_netlist              仿真网表，自动返回 RAW 结果和仿真器日志
simulate_netlist_with_ads    基于网表文件调用 ADS 仿真控制器
start_simulation_async        启动异步仿真，立即返回 task_id
get_simulation_async_status   查询状态和当前已接收的 ads_output 日志
get_simulation_async_result   获取结果（运行中返回部分日志，完成返回完整日志）

自然语言使用示例：
  帮我对 EDA 工程 C:\...\EDI_TEST.epp 执行仿真
  帮我对 C:\...\netlist.log 执行 ADS 仿真，超时设为 300 秒
  帮我仿真这个工程，日志来源标记为 my_test
  查看仿真进度
  获取仿真结果

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
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from proto import ecserver_pb2
from servers.eda.grpc_client import call_grpc
from servers.eda.config import validate_file, validate_project_path
from servers.mcp_instance import mcp

# -- 异步仿真任务注册表 --
_sim_tasks: dict[str, dict] = {}
_sim_lock = threading.Lock()

# 单工作线程执行器 — EDA 操作串行化，避免大量线程等待
_SIM_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sim")

# 任务保留 2 小时
_TASK_TTL = 7200


def _prune_tasks() -> None:
    """清理过期任务（超过 TTL 的已完成/失败任务）。"""
    now = time.time()
    with _sim_lock:
        expired = [
            tid for tid, t in _sim_tasks.items()
            if t.get("finished_at") is not None and now - t["finished_at"] > _TASK_TTL
        ]
        for tid in expired:
            del _sim_tasks[tid]


def _current_ads_output(task: dict) -> str:
    """获取当前日志：优先已完成的完整 result，否则拼接实时 chunk。"""
    if task.get("result") and isinstance(task["result"], dict):
        return task["result"].get("ads_output", "")
    return "".join(task.get("log_chunks", []))


# ---------------------------------------------------------------------------
# 事件回调 — 异步任务实时更新
# ---------------------------------------------------------------------------

def _handle_sim_event(task_id: str, update: dict[str, Any]) -> None:
    with _sim_lock:
        task = _sim_tasks.get(task_id)
        if task is None:
            return

        status = update.get("status", "")
        chunk = update.get("ads_output_chunk", "")
        details = update.get("details", {})

        if chunk:
            task["log_chunks"].append(chunk)

        if update.get("message"):
            task["message"] = update["message"]

        if details.get("project_path"):
            task["project_path"] = details["project_path"]

        if details.get("result_path"):
            task["result_path"] = details["result_path"]

        if status == "ACCEPTED":
            if task["status"] == "QUEUED":
                task["status"] = "ACCEPTED"

        elif status == "RESULT_STATUS_RUNNING":
            task["status"] = "RUNNING"
            if task["started_at"] is None:
                task["started_at"] = time.time()


# ---------------------------------------------------------------------------
# 后台执行
# ---------------------------------------------------------------------------

def _run_sim_task(
    task_id: str,
    client_uuid: str,
    project_path: str,
    log_source: str,
    timeout_seconds: int,
) -> None:
    try:
        result = call_grpc(
            ecserver_pb2.SIMULATE_PROJECT,
            {"project_path": project_path, "log_source": log_source},
            timeout_seconds,
            max_timeout_seconds=3600,
            task_id=task_id,
            client_uuid=client_uuid,
            on_event=lambda update: _handle_sim_event(task_id, update),
        )

        with _sim_lock:
            task = _sim_tasks.get(task_id)
            if task is None:
                return
            task["status"] = result["status"]
            task["message"] = result["message"]
            task["result_path"] = result.get("result_path", "")
            task["result"] = result
            task["error"] = None if result.get("success") else result.get("message")
            task["finished_at"] = time.time()
            # 最终 result 已含完整拼接日志，清 chunk 避免双份
            task["log_chunks"] = []

    except Exception as exc:
        with _sim_lock:
            task = _sim_tasks.get(task_id)
            if task is None:
                return
            partial_output = "".join(task.get("log_chunks", []))
            task["status"] = "FAILED"
            task["message"] = str(exc)
            task["error"] = str(exc)
            task["finished_at"] = time.time()
            task["result"] = {
                "success": False,
                "completed": False,
                "task_id": task_id,
                "client_uuid": client_uuid,
                "status": "FAILED",
                "message": str(exc),
                "project_path": project_path,
                "result_path": task.get("result_path", ""),
                "ads_output": partial_output,
                "log_complete": False,
            }
            task["log_chunks"] = []


# ---------------------------------------------------------------------------
# MCP 工具
# ---------------------------------------------------------------------------

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
    client_uuid = str(uuid.uuid4())

    _prune_tasks()

    with _sim_lock:
        _sim_tasks[task_id] = {
            "task_id": task_id,
            "client_uuid": client_uuid,
            "operation": "simulate_project",
            "project_path": resolved_path,
            "result_path": "",
            "status": "QUEUED",
            "message": "等待执行",
            "log_chunks": [],
            "result": None,
            "error": None,
            "created_at": time.time(),
            "started_at": None,
            "finished_at": None,
        }

    _SIM_EXECUTOR.submit(
        _run_sim_task,
        task_id,
        client_uuid,
        resolved_path,
        log_source,
        timeout_seconds,
    )

    return {
        "success": True,
        "task_id": task_id,
        "client_uuid": client_uuid,
        "status": "QUEUED",
        "message": "仿真任务已创建",
    }


@mcp.tool()
def get_simulation_async_status(task_id: str) -> dict[str, Any]:
    """查询异步仿真任务状态。

    返回字段包括 status、当前已接收的 ads_output、log_complete 等。
    运行中即可查询到实时日志。
    """
    _prune_tasks()

    with _sim_lock:
        task = _sim_tasks.get(task_id)

    if task is None:
        return {
            "success": False,
            "task_id": task_id,
            "status": "UNKNOWN",
            "message": "仿真任务不存在或服务已经重启",
            "ads_output": "",
            "log_complete": False,
        }

    completed = task["status"] in ("SUCCEEDED", "FAILED")

    return {
        "success": True,
        "completed": completed,
        "task_id": task_id,
        "client_uuid": task["client_uuid"],
        "status": task["status"],
        "message": task["message"],
        "project_path": task["project_path"],
        "result_path": task["result_path"],
        "ads_output": _current_ads_output(task),
        "log_complete": completed,
        "created_at": task["created_at"],
        "started_at": task["started_at"],
        "finished_at": task["finished_at"],
    }


@mcp.tool()
def get_simulation_async_result(task_id: str) -> dict[str, Any]:
    """获取已完成的异步仿真结果。

    任务运行中时返回当前状态和已接收的部分日志；
    完成后返回完整的仿真结果和日志。
    """
    _prune_tasks()

    with _sim_lock:
        task = _sim_tasks.get(task_id)

    if task is None:
        return {
            "success": False,
            "completed": False,
            "task_id": task_id,
            "status": "UNKNOWN",
            "message": "仿真任务不存在或服务已经重启",
            "ads_output": "",
            "log_complete": False,
        }

    # 已完成 — 返回完整 result
    if task["result"] is not None:
        return dict(task["result"])

    # 运行中 — 返回当前状态和部分日志
    return {
        "success": True,
        "completed": False,
        "task_id": task_id,
        "client_uuid": task["client_uuid"],
        "status": task["status"],
        "message": task["message"],
        "project_path": task["project_path"],
        "result_path": task["result_path"],
        "ads_output": _current_ads_output(task),
        "log_complete": False,
    }


@mcp.tool()
def simulate_project(
    project_path: str,
    log_source: str = "mcp_client",
    timeout_seconds: int = 600,
) -> dict[str, Any]:
    """对 EDA .epp 工程执行仿真，等待仿真完成并返回结果。

    FetchEvent 长连接期间实时收集 ads_output 增量日志，
    成功或失败均返回完整日志。

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
def simulate_netlist(
    netlist_path: str,
    timeout_seconds: int = 600,
) -> dict[str, Any]:
    """仿真指定的 netlist.log，返回 RAW 结果和仿真器输出日志。

    服务端自动将网表复制到临时目录 → 执行 ADS 仿真 → 复制 RAW 到原网表同级
    history/result.raw → 清理临时目录。ads_output 在最终事件中返回。

    Args:
        netlist_path: 网表文件路径（必须已存在）。
        timeout_seconds: 最长等待秒数，默认 600。
    """
    resolved_netlist = validate_file(netlist_path)
    return call_grpc(
        ecserver_pb2.SIMULATE_NETLIST,
        {"netlist_path": resolved_netlist},
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
