"""公共服务客户端 — 当前为本地测试桩（无需中央服务即可运行）。"""

from __future__ import annotations

from typing import Any, Callable


class LocalClient:
    """本地测试客户端 — 绕过网络直接调用本机执行器。"""

    def __init__(self) -> None:
        from servers.agent.executor import submit, get_job_status, get_job_result, cancel_job
        self._submit = submit
        self._status = get_job_status
        self._result = get_job_result
        self._cancel = cancel_job

    def submit_job(self, operation: str, parameters: dict[str, Any]) -> str:
        import uuid
        job_id = str(uuid.uuid4())
        self._submit(job_id, operation, parameters)
        return job_id

    def get_status(self, job_id: str) -> dict[str, Any]:
        return self._status(job_id)

    def get_result(self, job_id: str) -> dict[str, Any] | None:
        return self._result(job_id)

    def cancel_job(self, job_id: str) -> dict[str, Any]:
        return self._cancel(job_id)


# 全局单例
client = LocalClient()
