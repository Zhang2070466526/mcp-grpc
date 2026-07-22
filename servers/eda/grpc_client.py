"""EDA gRPC 通信层 — 封装 PerformAction + FetchEvent 异步调用流程。

内部模块，不直接暴露为 MCP 工具。
调用 call_grpc(task_type, payload, timeout_seconds) 提交任务并等待结果。
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from typing import Any

import grpc

from proto import ecserver_pb2, ecserver_pb2_grpc
from servers.eda.config import EDA_GRPC_SERVER  # 从 config 统一读取

# EDA 操作全局锁 — 确保同一时间只进行一项 gRPC 状态操作
_EDA_LOCK = threading.RLock()


def call_grpc(
    task_type: int,
    payload: dict[str, Any],
    timeout_seconds: int,
    max_timeout_seconds: int = 3600,
) -> dict[str, Any]:
    """通用 gRPC 调用（带锁串行化）。

    Args:
        task_type: EventType 枚举值。
        payload: 任务参数字典。
        timeout_seconds: 总超时秒数（需 > 0）。
        max_timeout_seconds: 最大允许秒数，默认 3600。

    Returns:
        包含 success / task_id / task_type / message / details 的结果字典。
    """
    if timeout_seconds < 1:
        raise ValueError("timeout_seconds 必须大于 0")
    if timeout_seconds > max_timeout_seconds:
        raise ValueError(f"timeout_seconds 不能超过 {max_timeout_seconds} 秒")

    with _EDA_LOCK:
        return _call_grpc_unlocked(task_type, payload, timeout_seconds)


def _call_grpc_unlocked(
    task_type: int,
    payload: dict[str, Any],
    timeout_seconds: int,
) -> dict[str, Any]:
    client_uuid = str(uuid.uuid4())
    task_id = str(uuid.uuid4())
    request = ecserver_pb2.Request(
        client_uuid=client_uuid,
        task_id=task_id,
        type=task_type,
        payload_json=json.dumps(payload, ensure_ascii=False),
    )

    started_at = time.monotonic()
    task_type_name = ecserver_pb2.EventType.Name(task_type)

    try:
        with grpc.insecure_channel(EDA_GRPC_SERVER) as channel:
            stub = ecserver_pb2_grpc.ExternalCallStub(channel)
            response = stub.PerformAction(request, timeout=timeout_seconds)

            if response.code != 0:
                return {
                    "success": False,
                    "task_id": task_id,
                    "task_type": task_type_name,
                    "message": response.message or f"EDA 服务未受理 {task_type_name} 任务",
                }

            elapsed = time.monotonic() - started_at
            remaining = max(0.1, timeout_seconds - elapsed)
            events = stub.FetchEvent(
                ecserver_pb2.FetchEventRequest(client_uuid=client_uuid),
                timeout=remaining,
            )

            for event in events:
                if event.task_id != task_id:
                    continue
                if event.status == ecserver_pb2.RESULT_STATUS_SUCCESS:
                    result: dict[str, Any] = {
                        "success": True,
                        "task_id": task_id,
                        "task_type": task_type_name,
                        "message": event.message or f"{task_type_name} 成功",
                    }
                    if event.payload_json:
                        try:
                            result["details"] = json.loads(event.payload_json)
                        except json.JSONDecodeError:
                            result["details"] = event.payload_json
                    return result
                if event.status == ecserver_pb2.RESULT_STATUS_FAILED:
                    return {
                        "success": False,
                        "task_id": task_id,
                        "task_type": task_type_name,
                        "message": event.message or f"{task_type_name} 失败",
                    }

            return {
                "success": False,
                "task_id": task_id,
                "task_type": task_type_name,
                "message": "EDA 事件流已结束，但没有收到任务最终结果",
            }
    except grpc.RpcError as exc:
        code = exc.code().name if exc.code() else "UNKNOWN"
        details = exc.details() or str(exc)
        raise RuntimeError(
            f"无法完成 EDA gRPC 调用 ({EDA_GRPC_SERVER}, {code}): {details}"
        ) from exc
