"""三池执行器 — EDI串行 / 文件并发 / Turbocharts串行。"""

from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from servers.agent import local_store
from servers.agent.operation_registry import (
    EDA_OPS,
    TURBOCHARTS_OPS,
    get as _get_op,
)

# 执行池配置
_EDA_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="eda")
_FILE_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="file")
_TC_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tc")

_futures: dict[str, Future[Any]] = {}
_futures_lock = threading.Lock()


def submit(job_id: str, operation: str, parameters: dict[str, Any]) -> str:
    """提交任务到对应执行池，返回 job_id。

    幂等：如果 job_id 已存在，不重复执行。
    """
    if not local_store.insert_job(job_id, operation, parameters):
        # 已存在 — 检查是否需要恢复执行
        job = local_store.get_job(job_id)
        if job and job["status"] in ("QUEUED", "DELIVERED"):
            return _enqueue(job_id, operation, parameters)
        return job_id  # 幂等

    return _enqueue(job_id, operation, parameters)


def _enqueue(job_id: str, operation: str, parameters: dict[str, Any]) -> str:
    if operation in EDA_OPS:
        ex = _EDA_EXECUTOR
    elif operation in TURBOCHARTS_OPS:
        ex = _TC_EXECUTOR
    else:
        ex = _FILE_EXECUTOR

    fut = ex.submit(_run_job, job_id, operation, parameters)
    fut.add_done_callback(lambda f, jid=job_id: _futures.pop(jid, None))
    with _futures_lock:
        _futures[job_id] = fut
    return job_id


def get_job_status(job_id: str) -> dict[str, Any]:
    """查询任务状态。"""
    job = local_store.get_job(job_id)
    if job is None:
        return {"job_id": job_id, "status": "UNKNOWN"}
    return {
        "job_id": job_id,
        "operation": job["operation"],
        "status": job["status"],
        "received_at": job["received_at"],
        "started_at": job["started_at"],
        "finished_at": job["finished_at"],
        "result": job.get("result"),
        "error": job.get("error"),
    }


def get_job_result(job_id: str) -> dict[str, Any] | None:
    """获取已完成任务的结果。"""
    import json
    job = local_store.get_job(job_id)
    if job is None:
        return None
    result = job.get("result")
    if result and isinstance(result, str):
        result = json.loads(result)
    return {
        "job_id": job_id,
        "status": job["status"],
        "result": result,
        "error": job.get("error"),
    }


def cancel_job(job_id: str) -> dict[str, Any]:
    """取消任务（排队中可立即取消，运行中的 EDI 已受理后不可强制终止）。"""
    job = local_store.get_job(job_id)
    if job is None:
        return {"job_id": job_id, "cancelled": False, "reason": "not found"}
    status = job["status"]
    if status in ("QUEUED", "DELIVERED"):
        # 取消 Future（如果还在线程池队列中）
        with _futures_lock:
            fut = _futures.get(job_id)
            if fut is not None:
                fut.cancel()
        local_store.update_status(job_id, "CANCELLED")
        return {"job_id": job_id, "cancelled": True}
    if status == "RUNNING":
        local_store.update_status(job_id, "CANCEL_REQUESTED")
        return {"job_id": job_id, "cancelled": False, "reason": "already running, cancel requested"}
    return {"job_id": job_id, "cancelled": False, "reason": f"status is {status}"}


def list_jobs(status: str | None = None, limit: int = 50) -> list[dict]:
    return local_store.list_jobs(status=status, limit=limit)


# ---------------------------------------------------------------------------
# internal
# ---------------------------------------------------------------------------

def _run_job(job_id: str, operation: str, parameters: dict[str, Any]) -> None:
    # 原子状态转换 — 只有 QUEUED/DELIVERED 才允许进入 RUNNING
    if not local_store.transition_status(job_id, ("QUEUED", "DELIVERED"), "RUNNING"):
        return  # 已被取消或已完成

    func = _get_op(operation)
    if func is None:
        local_store.update_status(job_id, "FAILED", error=f"Unknown operation: {operation}")
        return
    try:
        result = func(**parameters)
        local_store.update_status(job_id, "SUCCEEDED", result=result)
    except Exception as exc:
        local_store.update_status(job_id, "FAILED", error=str(exc))


def recover_pending_jobs() -> int:
    """启动时恢复 QUEUED/DELIVERED 任务，RUNNING 标记为 RECOVERY_REQUIRED。

    返回重新入队的任务数。
    """
    recovered = 0
    for job in local_store.list_jobs(limit=1000):
        status = job["status"]
        jid = job["job_id"]
        if status in ("QUEUED", "DELIVERED"):
            _enqueue(jid, job["operation"], job.get("parameters", "{}"))
            recovered += 1
        elif status == "RUNNING":
            local_store.update_status(jid, "RECOVERY_REQUIRED",
                                      error="Agent restarted while job was running")
    return recovered
