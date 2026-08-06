"""EDA gRPC 通信层 — 封装 FetchEvent + PerformAction 异步调用流程。

内部模块，不直接暴露为 MCP 工具。
调用 call_grpc(task_type, payload, timeout_seconds) 提交任务并等待结果。

调用顺序：FetchEvent（建立订阅）→ PerformAction（提交任务），
与文档要求一致。两次调用使用相同的 client_uuid。

支持：
  - 增量 ads_output 日志收集（原样追加，不 strip）
  - 事件回调（on_event），供异步任务实时更新
  - 外部传入 task_id / client_uuid，贯穿整个调用链
  - 严格事件筛选（client_uuid + task_id + event_type）
  - 超时/断连保留已收日志，log_complete=False
  - 统一 deadline 控制总超时
  - finally 确保事件流释放
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from collections.abc import Callable
from typing import Any

import grpc

from proto import ecserver_pb2, ecserver_pb2_grpc
from servers.eda.config import EDA_GRPC_SERVER

_logger = logging.getLogger("eda.grpc_client")

# EDA 操作全局锁 — 确保同一时间只进行一项 gRPC 状态操作
_EDA_LOCK = threading.RLock()

# 回调类型
GrpcEventCallback = Callable[[dict[str, Any]], None]

# PerformAction 提交阶段最长等待（秒），主要时间留给 FetchEvent
_PERFORM_ACTION_TIMEOUT = 30.0


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _parse_payload_json(payload_json: str) -> tuple[dict[str, Any], str | None]:
    """解析 payload_json，返回 (dict, error_or_none)。"""
    if not payload_json:
        return {}, None
    try:
        value = json.loads(payload_json)
    except json.JSONDecodeError as exc:
        return {"raw_payload": payload_json}, f"payload_json 解析失败: {exc}"
    if not isinstance(value, dict):
        return {"raw_payload": value}, "payload_json 不是 JSON 对象"
    return value, None


def _emit_event(callback: GrpcEventCallback | None, update: dict[str, Any]) -> None:
    if callback is None:
        return
    try:
        callback(update)
    except Exception:
        _logger.exception("gRPC 事件回调失败 task_id=%s", update.get("task_id"))


# ---------------------------------------------------------------------------
# 终端结果构建
# ---------------------------------------------------------------------------

def _terminal_result(
    success: bool,
    status: str,
    message: str,
    client_uuid: str,
    task_id: str,
    task_type_name: str,
    project_path: str,
    result_path: str,
    ads_output: str,
    log_complete: bool,
    latest_details: dict[str, Any],
    *,
    outcome_known: bool = False,
) -> dict[str, Any]:
    """构建终端结果字典。

    outcome_known=True 表示已收到 EDI 的最终事件（SUCCEEDED/FAILED），
    此时 task_success 有意义；False 表示 EDI 任务结果未知（超时/断连等）。
    """
    return {
        "success": success,
        "completed": True,
        "outcome_known": outcome_known,
        "task_success": success if outcome_known else None,
        "client_uuid": client_uuid,
        "task_id": task_id,
        "task_type": task_type_name,
        "status": status,
        "message": message,
        "project_path": project_path,
        "result_path": result_path,
        "ads_output": ads_output,
        "log_complete": log_complete,
        "details": latest_details,
    }


# ---------------------------------------------------------------------------
# 公共接口
# ---------------------------------------------------------------------------

def call_grpc(
    task_type: int,
    payload: dict[str, Any],
    timeout_seconds: int,
    max_timeout_seconds: int = 3600,
    *,
    task_id: str | None = None,
    client_uuid: str | None = None,
    on_event: GrpcEventCallback | None = None,
) -> dict[str, Any]:
    """通用 gRPC 调用（带锁串行化）。

    Args:
        task_type: EventType 枚举值。
        payload: 任务参数字典。
        timeout_seconds: 总超时秒数（需 > 0）。
        max_timeout_seconds: 最大允许秒数，默认 3600。
        task_id: 外部预生成的任务 ID（None 时内部生成）。
        client_uuid: 外部预生成的客户端 ID（None 时内部生成）。
        on_event: 事件回调，接收每个 FetchEvent 事件的增量信息。

    Returns:
        统一结构：success / completed / client_uuid / task_id / task_type
        / status / message / project_path / result_path / ads_output / log_complete / details
    """
    if timeout_seconds < 1:
        raise ValueError("timeout_seconds 必须大于 0")
    if timeout_seconds > max_timeout_seconds:
        raise ValueError(f"timeout_seconds 不能超过 {max_timeout_seconds} 秒")

    actual_task_id = task_id or str(uuid.uuid4())
    actual_client_uuid = client_uuid or str(uuid.uuid4())

    deadline = time.monotonic() + timeout_seconds

    acquired = _EDA_LOCK.acquire(timeout=timeout_seconds)
    if not acquired:
        return _terminal_result(
            success=False, status="QUEUE_TIMEOUT",
            message=f"等待 EDA 执行槽位超时（{timeout_seconds:.0f}s）",
            client_uuid=actual_client_uuid, task_id=actual_task_id,
            task_type_name=ecserver_pb2.EventType.Name(task_type),
            project_path=payload.get("project_path", ""),
            result_path="", ads_output="", log_complete=False,
            latest_details={},
        )
    if time.monotonic() >= deadline:
        _EDA_LOCK.release()
        return _terminal_result(
            success=False, status="QUEUE_TIMEOUT",
            message=f"等待 EDA 执行槽位超时（{timeout_seconds:.0f}s）",
            client_uuid=actual_client_uuid, task_id=actual_task_id,
            task_type_name=ecserver_pb2.EventType.Name(task_type),
            project_path=payload.get("project_path", ""),
            result_path="", ads_output="", log_complete=False,
            latest_details={},
        )
    try:
        return _call_grpc_unlocked(
            task_type, payload, deadline,
            task_id=actual_task_id,
            client_uuid=actual_client_uuid,
            on_event=on_event,
        )
    finally:
        _EDA_LOCK.release()


# ---------------------------------------------------------------------------
# 内部实现
# ---------------------------------------------------------------------------

def _call_grpc_unlocked(
    task_type: int,
    payload: dict[str, Any],
    deadline: float,
    *,
    task_id: str,
    client_uuid: str,
    on_event: GrpcEventCallback | None,
) -> dict[str, Any]:
    task_type_name = ecserver_pb2.EventType.Name(task_type)

    request = ecserver_pb2.Request(
        client_uuid=client_uuid,
        task_id=task_id,
        type=task_type,
        payload_json=json.dumps(payload, ensure_ascii=False),
    )

    started_at = time.monotonic()
    ads_output_chunks: list[str] = []
    _given_timeout = max(0.0, deadline - started_at)
    latest_details: dict[str, Any] = {}
    event_stream = None
    action_accepted = False

    def remaining() -> float:
        return max(0.1, deadline - time.monotonic())

    try:
        with grpc.insecure_channel(EDA_GRPC_SERVER) as channel:
            stub = ecserver_pb2_grpc.ExternalCallStub(channel)

            # ── 1. 先建立 FetchEvent 订阅 ──
            _logger.info("task=%s client=%s type=%s phase=SUBSCRIBING",
                         task_id[:12], client_uuid[:12], task_type_name)
            event_stream = stub.FetchEvent(
                ecserver_pb2.FetchEventRequest(client_uuid=client_uuid),
                timeout=remaining(),
            )
            _logger.info("task=%s phase=SUBSCRIBED", task_id[:12])

            # ── 2. 再提交 PerformAction ──
            _logger.info("task=%s phase=PERFORM_ACTION", task_id[:12])
            response = stub.PerformAction(
                request,
                timeout=min(_PERFORM_ACTION_TIMEOUT, remaining()),
            )

            # ── 3. 未受理 ──
            if response.code != 0:
                message = response.message or f"EDA 服务未受理 {task_type_name} 任务"
                _logger.warning("task=%s phase=REJECTED code=%d message=%s",
                                task_id[:12], response.code, message)
                _emit_event(on_event, {
                    "phase": "REJECTED",
                    "client_uuid": client_uuid,
                    "task_id": task_id,
                    "task_type": task_type_name,
                    "status": "REJECTED",
                    "message": message,
                    "ads_output_chunk": "",
                    "details": {},
                })
                return _terminal_result(
                    success=False, status="REJECTED", message=message,
                    client_uuid=client_uuid, task_id=task_id,
                    task_type_name=task_type_name,
                    project_path=payload.get("project_path", ""),
                    result_path="", ads_output="", log_complete=True,
                    latest_details={},
                    outcome_known=True,
                )

            # ── 4. 回显校验 ──
            if response.client_uuid and response.client_uuid != client_uuid:
                msg = f"PerformAction client_uuid 不匹配: sent={client_uuid} got={response.client_uuid}"
                _logger.error("task=%s %s", task_id[:12], msg)
                return _terminal_result(
                    success=False, status="PROTOCOL_MISMATCH", message=msg,
                    client_uuid=client_uuid, task_id=task_id,
                    task_type_name=task_type_name,
                    project_path=payload.get("project_path", ""),
                    result_path="", ads_output="", log_complete=False,
                    latest_details={},
                )
            if response.task_id and response.task_id != task_id:
                msg = f"PerformAction task_id 不匹配: sent={task_id} got={response.task_id}"
                _logger.error("task=%s %s", task_id[:12], msg)
                return _terminal_result(
                    success=False, status="PROTOCOL_MISMATCH", message=msg,
                    client_uuid=client_uuid, task_id=task_id,
                    task_type_name=task_type_name,
                    project_path=payload.get("project_path", ""),
                    result_path="", ads_output="", log_complete=False,
                    latest_details={},
                )
            if response.event_type not in (
                ecserver_pb2.EVENT_TYPE_UNSPECIFIED,
                task_type,
            ):
                msg = f"PerformAction event_type 不匹配: sent={task_type_name} got={ecserver_pb2.EventType.Name(response.event_type)}"
                _logger.error("task=%s %s", task_id[:12], msg)
                return _terminal_result(
                    success=False, status="PROTOCOL_MISMATCH", message=msg,
                    client_uuid=client_uuid, task_id=task_id,
                    task_type_name=task_type_name,
                    project_path=payload.get("project_path", ""),
                    result_path="", ads_output="", log_complete=False,
                    latest_details={},
                )

            # ── 5. ACCEPTED 回调 ──
            _logger.info("task=%s phase=ACCEPTED code=0", task_id[:12])
            _emit_event(on_event, {
                "phase": "ACCEPTED",
                "client_uuid": client_uuid,
                "task_id": task_id,
                "task_type": task_type_name,
                "status": "ACCEPTED",
                "message": response.message or "task accepted",
                "ads_output_chunk": "",
                "details": {},
            })

            # ── 6. 消费已建立的事件流 ──
            chunk_count = 0
            action_accepted = response.code == 0
            for event in event_stream:
                chunk = ""  # 初始化，防止终态事件先到达时 UnboundLocalError
                if event.client_uuid != client_uuid:
                    continue
                if event.task_id != task_id:
                    continue
                if event.event_type != task_type:
                    continue

                details, parse_error = _parse_payload_json(event.payload_json)

                is_terminal = event.status in (
                    ecserver_pb2.RESULT_STATUS_SUCCESS,
                    ecserver_pb2.RESULT_STATUS_FAILED,
                )

                if is_terminal:
                    # 终态：使用完整日志
                    final_output = details.get("ads_output", "")
                    ads_output = final_output if isinstance(final_output, str) and final_output \
                        else "".join(ads_output_chunks)
                else:
                    chunk = details.get("ads_output", "")
                    if chunk is None:
                        chunk = ""
                    elif not isinstance(chunk, str):
                        chunk = str(chunk)
                    if chunk:
                        ads_output_chunks.append(chunk)
                        chunk_count += 1

                for key, value in details.items():
                    if key != "ads_output":
                        latest_details[key] = value

                status_name = ecserver_pb2.ResultStatus.Name(event.status)

                _emit_event(on_event, {
                    "phase": "EVENT",
                    "client_uuid": client_uuid,
                    "task_id": task_id,
                    "task_type": task_type_name,
                    "status": status_name,
                    "message": event.message,
                    "ads_output_chunk": chunk,
                    "details": {k: v for k, v in details.items() if k != "ads_output"},
                    "payload_parse_error": parse_error,
                })

                project_path = latest_details.get("project_path", payload.get("project_path", ""))
                result_path = latest_details.get("result_path", "")

                if event.status == ecserver_pb2.RESULT_STATUS_SUCCESS:
                    _logger.info("task=%s phase=COMPLETED status=SUCCEEDED duration=%.1fs chunks=%d",
                                 task_id[:12], time.monotonic() - started_at, chunk_count)
                    # Verify payload integrity: SUCCESS must have parseable payload
                    if parse_error:
                        _logger.error("task=%s SUCCEEDED but payload_json invalid: %s",
                                      task_id[:12], parse_error)
                        return _terminal_result(
                            success=False, status="PROTOCOL_MISMATCH",
                            message=f"SUCCEEDED 事件 payload_json 无法解析: {parse_error}",
                            client_uuid=client_uuid, task_id=task_id,
                            task_type_name=task_type_name,
                            project_path=project_path, result_path=result_path,
                            ads_output=ads_output, log_complete=True,
                            latest_details=latest_details,
                        )
                    return _terminal_result(
                        success=True, status="SUCCEEDED",
                        message=event.message or "task completed",
                        client_uuid=client_uuid, task_id=task_id,
                        task_type_name=task_type_name,
                        project_path=project_path, result_path=result_path,
                        ads_output=ads_output, log_complete=True,
                        latest_details=latest_details,
                        outcome_known=True,
                    )

                if event.status == ecserver_pb2.RESULT_STATUS_FAILED:
                    _logger.info("task=%s phase=COMPLETED status=FAILED duration=%.1fs chunks=%d",
                                 task_id[:12], time.monotonic() - started_at, chunk_count)
                    return _terminal_result(
                        success=False, status="FAILED",
                        message=event.message or "task failed",
                        client_uuid=client_uuid, task_id=task_id,
                        task_type_name=task_type_name,
                        project_path=project_path, result_path=result_path,
                        ads_output=ads_output, log_complete=True,
                        latest_details=latest_details,
                        outcome_known=True,
                    )

            # ── 流结束但无终态 ──
            return _terminal_result(
                success=False, status="STREAM_DISCONNECTED",
                message="FetchEvent 流已结束但未收到终态事件，EDI 端任务状态未知",
                client_uuid=client_uuid, task_id=task_id,
                task_type_name=task_type_name,
                project_path=latest_details.get("project_path", payload.get("project_path", "")),
                result_path=latest_details.get("result_path", ""),
                ads_output="".join(ads_output_chunks), log_complete=False,
                latest_details=latest_details,
            )

    except grpc.RpcError as exc:
        code = exc.code().name if exc.code() else "UNKNOWN"
        code_enum = exc.code()
        if code_enum == grpc.StatusCode.DEADLINE_EXCEEDED:
            _logger.warning("task=%s phase=TIMEOUT", task_id[:12])
            return _terminal_result(
                success=False, status="TIMEOUT",
                message=f"MCP 已停止等待（{_given_timeout:.0f}s），EDI 端任务状态未知",
                client_uuid=client_uuid, task_id=task_id,
                task_type_name=task_type_name,
                project_path=latest_details.get("project_path", payload.get("project_path", "")),
                result_path=latest_details.get("result_path", ""),
                ads_output="".join(ads_output_chunks), log_complete=False,
                latest_details=latest_details,
            )
        # 任务已受理后断开 → STREAM_DISCONNECTED；未受理 → GRPC_UNAVAILABLE
        if action_accepted:
            _logger.error("task=%s phase=STREAM_DISCONNECTED code=%s", task_id[:12], code)
            return _terminal_result(
                success=False, status="STREAM_DISCONNECTED",
                message=f"FetchEvent 长连接中断 ({code}): {exc.details() or exc}",
                client_uuid=client_uuid, task_id=task_id,
                task_type_name=task_type_name,
                project_path=latest_details.get("project_path", payload.get("project_path", "")),
                result_path=latest_details.get("result_path", ""),
                ads_output="".join(ads_output_chunks), log_complete=False,
                latest_details=latest_details,
            )
        return _terminal_result(
            success=False, status="GRPC_UNAVAILABLE",
            message=f"无法连接 EDA gRPC ({EDA_GRPC_SERVER}, {code}): {exc.details() or exc}",
            client_uuid=client_uuid, task_id=task_id,
            task_type_name=task_type_name,
            project_path=payload.get("project_path", ""),
            result_path="", ads_output="", log_complete=False,
            latest_details={},
        )

    finally:
        # ── 确保事件流释放 ──
        if event_stream is not None:
            event_stream.cancel()
