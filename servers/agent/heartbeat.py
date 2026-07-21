"""心跳上报模块。"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

from servers.agent import registration
from servers.eda.config import EDA_GRPC_SERVER


def start_heartbeat(
    send_fn: Callable[[dict[str, Any]], None],
    interval: int = 10,
) -> threading.Event:
    """启动心跳线程，每 interval 秒调用 send_fn。

    send_fn 接收心跳数据字典，负责发送到中央服务。
    返回 stop_event，set() 可停止心跳。
    """
    stop = threading.Event()

    def _loop() -> None:
        node = registration.get_or_create_node()
        while not stop.wait(interval):
            try:
                from servers.agent.local_store import list_jobs
                running = list_jobs(status="RUNNING", limit=10)
                queued = list_jobs(status="QUEUED", limit=100)
                status = "BUSY" if running else "IDLE"
                send_fn({
                    "node_id": node["node_id"],
                    "status": status,
                    "edi_ready": _check_edi(),
                    "agent_version": "0.1.0",
                    "current_job_id": running[0]["job_id"] if running else None,
                    "queued_job_count": len(queued),
                    "timestamp": time.time(),
                })
            except Exception:
                pass  # 心跳失败不中断

    t = threading.Thread(target=_loop, daemon=True, name="heartbeat")
    t.start()
    return stop


def _check_edi() -> bool:
    import socket as sock
    try:
        host, port_str = EDA_GRPC_SERVER.rsplit(":", 1)
        with sock.create_connection((host, int(port_str)), timeout=1):
            return True
    except Exception:
        return False
