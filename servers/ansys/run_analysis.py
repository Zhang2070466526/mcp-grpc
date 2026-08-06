"""ANSYS HFSS 异步仿真工具 — 单 Worker 队列，不阻塞 MCP。"""

from __future__ import annotations

import queue
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import pythoncom

from servers.ansys.config import (
    aedt_is_running, get_setup_module, query_desktop_state,
    _attach_aedt, logger,
)
from servers.eda.config import validate_file
from servers import mcp

_HFSS_TASKS: dict[str, dict] = {}
_HFSS_TASKS_LOCK = threading.RLock()
_HFSS_QUEUE: queue.Queue = queue.Queue(maxsize=10)
_HFSS_WORKER_STARTED = False
_HFSS_WORKER_LOCK = threading.Lock()
_HFSS_TASK_TTL = 7200        # 过期任务保留 2 小时
_MAX_HFSS_TASKS = 50          # 最大任务数（含历史和排队）

def _prune_hfss_tasks() -> None:
    """清理过期的已完成/失败任务。"""
    now = time.time()
    with _HFSS_TASKS_LOCK:
        expired = [
            tid for tid, t in _HFSS_TASKS.items()
            if t.get("finished_at") is not None and now - t["finished_at"] > _HFSS_TASK_TTL
        ]
        for tid in expired:
            del _HFSS_TASKS[tid]


def _start_hfss_worker() -> None:
    global _HFSS_WORKER_STARTED
    with _HFSS_WORKER_LOCK:
        if _HFSS_WORKER_STARTED:
            return
        _HFSS_WORKER_STARTED = True
    t = threading.Thread(target=_hfss_worker_loop, daemon=True, name="hfss-worker")
    t.start()


def _hfss_worker_loop() -> None:
    while True:
        task_id = _HFSS_QUEUE.get()
        if task_id is None:
            break
        _run_hfss_analysis_task(task_id)


def _run_hfss_analysis_task(task_id: str) -> None:
    with _HFSS_TASKS_LOCK:
        task = _HFSS_TASKS.get(task_id)
        if task is None:
            return

    pythoncom.CoInitialize()
    try:
        with _HFSS_TASKS_LOCK:
            _HFSS_TASKS[task_id]["status"] = "STARTING"

        _, desktop = _attach_aedt()
        project = desktop.SetActiveProject(task.get("project_name", ""))
        design = project.SetActiveDesign(task.get("design_name", ""))
        module, _ = get_setup_module(design)
        setups = list(module.GetSetups())
        if task.get("setup_name") not in setups:
            raise RuntimeError(f"Setup {task['setup_name']} not found. Available: {setups}")

        if task.get("save_before_run", True):
            project.Save()

        with _HFSS_TASKS_LOCK:
            _HFSS_TASKS[task_id].update(status="RUNNING", started_at=time.time())

        result_dir = str(Path(task["project_path"]).with_suffix(".aedtresults"))
        before_mtime = Path(result_dir).stat().st_mtime if Path(result_dir).is_dir() else 0

        design.Analyze(task["setup_name"])

        result_verified = Path(result_dir).is_dir() and (
            before_mtime == 0 or Path(result_dir).stat().st_mtime > before_mtime
        )
        still_running = False
        try:
            still_running = desktop.AreThereSimulationsRunning(True)
        except Exception:
            pass

        outcome_ok = result_verified and not still_running
        final_status = "SUCCEEDED" if outcome_ok else "UNKNOWN"
        with _HFSS_TASKS_LOCK:
            _HFSS_TASKS[task_id].update(
                status=final_status, result_directory=result_dir,
                result_verified=result_verified,
                outcome_known=outcome_ok,
                task_success=True if outcome_ok else None,
                finished_at=time.time(),
            )
    except Exception as exc:
        logger.exception("HFSS analysis failed")
        with _HFSS_TASKS_LOCK:
            _HFSS_TASKS[task_id].update(
                status="FAILED", error=str(exc),
                outcome_known=True, task_success=False,
                finished_at=time.time(),
            )
    finally:
        pythoncom.CoUninitialize()


def _validate_setups(project_path: str, design_name: str) -> dict:
    pythoncom.CoInitialize()
    try:
        _, desktop = _attach_aedt()
        project_name = Path(project_path).stem
        projects = list(desktop.GetProjectList())

        if project_name not in projects:
            return {"success": False, "status": "project_not_open",
                    "project_name": project_name, "open_projects": projects}

        project = desktop.SetActiveProject(project_name)
        try:
            design = project.SetActiveDesign(design_name)
        except Exception:
            names = list(project.GetDesignNames()) if hasattr(project, "GetDesignNames") else []
            return {"success": False, "status": "design_not_found",
                    "requested_design": design_name, "available_designs": names}

        try:
            module, _ = get_setup_module(design)
            setups = list(module.GetSetups())
        except Exception:
            setups = []
        return {"success": True, "project_name": project_name,
                "design_name": design_name, "setups": setups}
    except Exception as exc:
        return {"success": False, "status": "com_error", "error": str(exc)}
    finally:
        pythoncom.CoUninitialize()


def _any_hfss_running() -> bool:
    with _HFSS_TASKS_LOCK:
        for t in _HFSS_TASKS.values():
            if t["status"] in ("QUEUED", "STARTING", "RUNNING"):
                return True
    return False


@mcp.tool()
def start_hfss_analysis_async(
    project_path: str,
    design_name: str,
    setup_name: str,
    save_before_run: bool = True,
) -> dict[str, Any]:
    """异步启动 HFSS Setup 仿真，立即返回 task_id。"""
    try:
        resolved = validate_file(project_path, (".aedt", ".aedtz"))
    except (FileNotFoundError, ValueError) as exc:
        return {"success": False, "status": "invalid_path", "message": str(exc)}

    if not aedt_is_running():
        return {"success": False, "status": "aedt_not_running",
                "message": "AEDT 未运行，请先用 open_hfss_project 打开工程"}

    validation = _validate_setups(resolved, design_name)
    if not validation["success"]:
        return validation

    if setup_name not in validation["setups"]:
        return {"success": False, "status": "setup_not_found",
                "requested_setup": setup_name, "available_setups": validation["setups"]}

    project_name = Path(resolved).stem
    task_id = f"hfss-{uuid.uuid4().hex[:12]}"

    with _HFSS_TASKS_LOCK:
        _prune_hfss_tasks()

        if _any_hfss_running():
            return {"success": False, "status": "analysis_busy",
                    "message": "当前已有 HFSS 仿真正在运行或排队"}

        if len(_HFSS_TASKS) >= _MAX_HFSS_TASKS:
            return {"success": False, "status": "task_limit_reached",
                    "message": f"HFSS 任务数已达上限 ({_MAX_HFSS_TASKS})，请稍后重试"}

        _HFSS_TASKS[task_id] = {
            "task_id": task_id, "operation": "hfss_analysis",
            "project_path": resolved, "project_name": project_name,
            "design_name": design_name, "setup_name": setup_name,
            "save_before_run": save_before_run,
            "status": "QUEUED", "created_at": time.time(),
            "started_at": None, "finished_at": None,
            "result_directory": "", "error": "",
            "outcome_known": False, "task_success": None,
        }
        _start_hfss_worker()
        try:
            _HFSS_QUEUE.put_nowait(task_id)
        except queue.Full:
            del _HFSS_TASKS[task_id]
            return {"success": False, "status": "queue_full",
                    "message": "仿真队列已满，请等待当前任务完成"}

    return {
        "success": True, "task_id": task_id, "status": "QUEUED",
        "project_name": project_name, "design_name": design_name,
        "setup_name": setup_name, "message": "HFSS 仿真任务已提交",
    }


@mcp.tool()
def get_hfss_analysis_status(
    task_id: str,
    refresh_from_aedt: bool = False,
) -> dict[str, Any]:
    """查询 HFSS 异步仿真状态（默认只读本地，不访问 AEDT）。"""
    with _HFSS_TASKS_LOCK:
        task = _HFSS_TASKS.get(task_id)

    if task is None:
        return {
            "success": False,
            "task_id": task_id,
            "status": "UNKNOWN",
            "task_success": None,
            "outcome_known": False,
            "error_code": "TASK_NOT_FOUND",
            "message": "HFSS 仿真任务不存在、已过期或服务已重启",
        }

    completed = task.get("finished_at") is not None
    result: dict[str, Any] = {
        "success": True, "task_id": task["task_id"], "status": task["status"],
        "completed": completed,
        "task_success": task.get("task_success"),
        "outcome_known": task.get("outcome_known", False),
        "project_path": task["project_path"], "project_name": task["project_name"],
        "design_name": task["design_name"], "setup_name": task["setup_name"],
        "created_at": task["created_at"], "started_at": task["started_at"],
        "finished_at": task["finished_at"],
        "result_directory": task.get("result_directory", ""),
        "result_verified": task.get("result_verified"),
        "error": task.get("error", ""),
    }
    if task["started_at"] is not None:
        end = task["finished_at"] or time.time()
        result["elapsed_seconds"] = round(end - task["started_at"], 1)

    if refresh_from_aedt:
        try:
            pythoncom.CoInitialize()
            _, desktop = _attach_aedt()
            result["aedt_refresh_succeeded"] = True
            result["aedt_simulations_running"] = desktop.AreThereSimulationsRunning(True)
        except Exception as exc:
            result["aedt_refresh_succeeded"] = False
            result["aedt_refresh_error"] = str(exc)
        finally:
            pythoncom.CoUninitialize()

    return result
