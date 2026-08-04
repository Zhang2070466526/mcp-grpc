r"""聊天服务 — 会话管理、LLM 多轮调用、工具闭环、参数校验。

职责：
  - 会话创建/查询/清理（内存，2 小时 TTL，100 上限）
  - 构建带动态上下文的 system prompt
  - LLM 调用 → 工具执行 → 结果交回模型 → 最多 5 轮循环
  - 工具参数自动补齐（当前工程/task_id/"第一个"）
  - 重复调用保护、空参数拒绝

单例模式：ChatService.instance() 获取全局实例。
"""

from __future__ import annotations

import asyncio
import json as _json
import logging
import os as _os
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_logger = logging.getLogger("chat_service")

import httpx
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# 工具函数（直接导入，不走 MCP 装饰器开销）
# ---------------------------------------------------------------------------
from servers.eda.project_manage import (  # noqa: E402
    open_edi_project, close_edi_project,
    list_epp_projects,
    list_project_components,
    get_component_parameters, get_project_summary,
)
from servers.eda.simulation_components import get_simulation_component_schema, list_simulation_components, upsert_simulation_component, delete_simulation_component  # noqa: E402
from servers.eda.simulation import (  # noqa: E402
    start_simulation_async, get_simulation_async_status, get_simulation_async_result,
)
from servers.eda.design_export import (  # noqa: E402
    export_project_netlist, capture_schematic,
)
from servers.eda.model_replace import replace_models_from_csv  # noqa: E402
from servers.eda.edi_launcher import launch_edi  # noqa: E402
from servers.turbocharts.compare_results import compare_simulation_results  # noqa: E402
from servers.turbocharts.convert_raw import turbocharts_convert  # noqa: E402
from servers.image_tools import show_image, copy_image_to_workspace, OPENCLAW_WORKSPACE_PATH  # noqa: E402

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
_MAX_ROUNDS = 5          # 最多工具调用轮数
_MAX_MESSAGES = 30       # 每个会话最多保留消息数
_MAX_SESSIONS = 100      # 全局会话数上限
_SESSION_TTL = 7200      # 会话有效期 2 小时（秒）
_PRUNE_INTERVAL = 300    # 清理间隔 5 分钟

# ---------------------------------------------------------------------------
# 聊天工具注册表（不含同步仿真 simulate_project）
# ---------------------------------------------------------------------------
CHAT_TOOL_MAP: dict[str, Any] = {
    "list_epp_projects":              list_epp_projects,
    "open_edi_project":               open_edi_project,
    "close_edi_project":              close_edi_project,
    "list_project_components":        list_project_components,
    "get_component_parameters":       get_component_parameters,
    "get_project_summary":            get_project_summary,
    "start_simulation_async":         start_simulation_async,
    "get_simulation_async_status":    get_simulation_async_status,
    "get_simulation_async_result":    get_simulation_async_result,
    "capture_schematic":              capture_schematic,
    "export_project_netlist":         export_project_netlist,
    "replace_models_from_csv":        replace_models_from_csv,
    "launch_edi":                     launch_edi,
    "compare_simulation_results":     compare_simulation_results,
    "turbocharts_convert":            turbocharts_convert,
    "show_image":                     show_image,
    "get_simulation_component_schema": get_simulation_component_schema,
    "list_simulation_components": list_simulation_components,
    "upsert_simulation_component": upsert_simulation_component,
    "delete_simulation_component": delete_simulation_component,
}
if OPENCLAW_WORKSPACE_PATH is not None:
    CHAT_TOOL_MAP["copy_image_to_workspace"] = copy_image_to_workspace

def _rtool(name: str, desc: str, required: dict, optional: dict | None = None) -> dict:
    """构建单个 OpenAI function-call 工具 schema。"""
    props = {}
    for k, t in {**required, **(optional or {})}.items():
        if t == "array":
            props[k] = {"type": "array", "items": {"type": "string"}}
        else:
            props[k] = {"type": t}
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": desc,
            "parameters": {
                "type": "object",
                "properties": props,
                "required": list(required.keys()),
            },
        },
    }


def _build_tools_schema() -> list[dict]:
    """构建聊天工具 schema，与 CHAT_TOOL_MAP 保持一致。"""
    tools = [
        _rtool("list_epp_projects", "扫描文件夹中的 .epp 工程文件", {"folder_path": "string"}),
        _rtool("open_edi_project", "打开 .epp 工程", {"project_path": "string"}, {"timeout_seconds": "integer"}),
        _rtool("close_edi_project", "关闭 EDA 工程", {"project_path": "string"}, {"need_save": "boolean"}),
        _rtool("list_project_components", "列出工程原理图中的元件", {"project_path": "string"}, {"schematic_name": "string", "component_type": "string", "name_contains": "string", "offset": "integer", "limit": "integer"}),
        _rtool("get_component_parameters", "查询单个元件的完整参数", {"project_path": "string", "component_id": "string"}, {"schematic_name": "string", "include_hidden": "boolean"}),
        _rtool("get_project_summary", "获取 .epp 工程完整概览", {"project_path": "string"}, {"include_component_types": "boolean", "include_latest_result": "boolean"}),
        _rtool("start_simulation_async", "异步启动 EDA 工程仿真，立即返回 task_id", {"project_path": "string"}, {"log_source": "string", "timeout_seconds": "integer"}),
        _rtool("get_simulation_async_status", "查询仿真状态及已实时接收的 ads_output 日志", {"task_id": "string"}),
        _rtool("get_simulation_async_result", "获取仿真结果；运行中返回当前日志，完成后返回完整 ads_output", {"task_id": "string"}),
        _rtool("capture_schematic", "截取原理图为图片", {"project_path": "string", "img_path": "string"}, {"timeout_seconds": "integer"}),
        _rtool("export_project_netlist", "查看/导出工程网表", {"project_path": "string"}, {"timeout_seconds": "integer"}),
        _rtool("replace_models_from_csv", "按 CSV 批量替换元件模型", {"project_path": "string", "csv_path": "string"}, {"timeout_seconds": "integer"}),
        _rtool("launch_edi", "启动 EDI 客户端并等待 gRPC 就绪", {}, {"edi_path": "string", "wait_for_grpc": "boolean", "wait_timeout": "integer"}),
        _rtool("compare_simulation_results", "多个 RAW 结果同一条曲线对比叠图", {"result_paths": "array", "curve": "string", "img_path": "string"}, {"chart_type": "string", "labels": "array", "dependency": "string", "csv_path": "string", "alignment": "string", "reference_index": "integer"}),
        _rtool("turbocharts_convert", "ADS RAW 文件转曲线图和 CSV", {"raw_path": "string", "img_path": "string", "chart_type": "string"}, {"csv_path": "string", "linename": "string", "dependency": "string", "ac_config": "string"}),
        _rtool("show_image", "读取本地图片，返回 MCP ImageContent（不要自行生成 MEDIA）", {"image_path": "string"}),
        _rtool("get_simulation_component_schema", "查询仿真控件支持的参数、类型和单位；配置控件前优先调用", {"component_type": "string"}, {"parameter_name": "string"}),
        _rtool("list_simulation_components", "查询工程中的仿真器件", {"project_path": "string"}, {"component_type": "string"}),
        _rtool("upsert_simulation_component", "新增或更新仿真器件参数", {"project_path": "string", "component_type": "string", "parameters": "object"}, {"timeout_seconds": "integer"}),
        _rtool("delete_simulation_component", "删除仿真器件", {"project_path": "string", "component_type": "string"}, {"timeout_seconds": "integer"}),
    ]
    if OPENCLAW_WORKSPACE_PATH is not None:
        tools.append(_rtool("copy_image_to_workspace", "复制图片到工作区 media/edi，需配置 OPENCLAW_WORKSPACE", {"image_path": "string"}))
    return tools


CHAT_TOOLS_SCHEMA = _build_tools_schema()

# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class Activity:
    """一次工具调用的摘要。"""
    tool: str
    label: str
    status: str          # "success" | "error"
    duration_ms: float = 0
    summary: str = ""     # 简短描述
    args: dict | None = None
    result: Any = None
    error: str = ""


@dataclass
class ChatSession:
    """会话状态。"""
    session_id: str
    messages: list[dict] = field(default_factory=list)
    current_project_path: str | None = None
    current_project_name: str | None = None
    last_folder_path: str | None = None
    last_projects: list[dict] = field(default_factory=list)
    last_simulation_task_id: str | None = None
    simulation_task_ids: list[str] = field(default_factory=list)
    updated_at: float = field(default_factory=time.time)


@dataclass
class ChatResponse:
    success: bool
    session_id: str
    request_id: str
    reply: str
    activities: list[dict] = field(default_factory=list)
    context: dict = field(default_factory=dict)
    media: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "session_id": self.session_id,
            "request_id": self.request_id,
            "reply": self.reply,
            "activities": self.activities,
            "context": self.context,
            "media": self.media,
        }


# ---------------------------------------------------------------------------
# 系统提示词
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "你是本地 EDI 工程助手，请使用中文回答。\n\n"
    "规则：\n"
    "1. 不得虚构文件路径、工程名称、元件或仿真结果。\n"
    "2. 工具必填参数缺失时，先询问用户，不要使用空字符串或猜测的路径调用。\n"
    "3. 如果提供了当前工程，\"当前工程\"\"这个工程\"均指该路径。\n"
    "4. 执行仿真时优先调用 start_simulation_async。仿真日志通过 FetchEvent 长连接增量推送，"\
    "用户询问\"当前日志\"\"仿真输出\"\"失败原因\"时，使用最近一次 task_id 调用 "\
    "get_simulation_async_result 获取 ads_output 分析。不得调用 LOG_EVENT，不得为查询日志重新启动仿真。\n"
    "5. 工具执行成功后，用自然语言概括结果，不要直接输出原始 JSON。\n"
    "6. 工具失败时说明失败原因和下一步，不要反复使用相同参数调用。\n"
    "7. 用户说\"第一个\"\"第二个\"时，根据最近一次工程列表解析。\n"
    "8. 除非用户要求，不展示内部工具名称、参数和调用细节。"
)


def _system_with_context(session: ChatSession) -> str:
    ctx_parts = []
    if session.current_project_path:
        ctx_parts.append(f"当前工程：{session.current_project_name or session.current_project_path}")
    else:
        ctx_parts.append("当前工程：未选择")
    if session.last_folder_path:
        ctx_parts.append(f"最近扫描目录：{session.last_folder_path}")
    if session.last_simulation_task_id:
        ctx_parts.append(f"最近仿真任务：{session.last_simulation_task_id}")
    ctx = "\n".join(ctx_parts)
    return f"{_SYSTEM_PROMPT}\n\n当前上下文：\n{ctx}"


# ---------------------------------------------------------------------------
# 错误码
# ---------------------------------------------------------------------------

ERROR_CODES = {
    "MISSING_REQUIRED_ARGUMENT": "缺少必填参数",
    "INVALID_PATH": "路径格式不正确",
    "FILE_NOT_FOUND": "文件不存在",
    "EDA_GRPC_OFFLINE": "EDA gRPC 服务未启动",
    "TOOL_TIMEOUT": "工具执行超时",
    "TOOL_EXECUTION_FAILED": "工具执行失败",
    "DUPLICATE_TOOL_CALL": "重复调用保护",
    "TOOL_LOOP_LIMIT": "超过最大工具调用轮数",
    "SIMULATION_ALREADY_RUNNING": "工程已有仿真正在运行",
    "LLM_REQUEST_FAILED": "模型接口请求失败",
    "NO_CURRENT_PROJECT": "当前没有选定工程",
}


def _tool_error(code: str, detail: str = "") -> dict:
    return {
        "success": False,
        "error": {
            "code": code,
            "message": ERROR_CODES.get(code, code),
            "detail": detail,
        },
    }


# ---------------------------------------------------------------------------
# ChatService 单例
# ---------------------------------------------------------------------------

class ChatService:
    """聊天服务 — 单例，管理会话和工具调用闭环。"""

    _instance: ChatService | None = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._sessions: dict[str, ChatSession] = {}
        self._session_lock = threading.Lock()
        self._last_prune = time.time()

    @classmethod
    def instance(cls) -> ChatService:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ── 会话管理 ──

    def _get_or_create(self, session_id: str) -> ChatSession:
        self._prune()
        sid = session_id.strip() if session_id else ""
        with self._session_lock:
            if sid and sid in self._sessions:
                s = self._sessions[sid]
                s.updated_at = time.time()
                return s
            new_id = sid or uuid.uuid4().hex[:12]
            s = ChatSession(session_id=new_id)
            self._sessions[new_id] = s
            return s

    def _prune(self) -> None:
        now = time.time()
        if now - self._last_prune < _PRUNE_INTERVAL:
            return
        self._last_prune = now
        with self._session_lock:
            expired = [
                sid for sid, s in self._sessions.items()
                if now - s.updated_at > _SESSION_TTL
            ]
            for sid in expired:
                del self._sessions[sid]
            # 超过上限则删最旧的
            if len(self._sessions) > _MAX_SESSIONS:
                sorted_ids = sorted(
                    self._sessions.keys(),
                    key=lambda sid: self._sessions[sid].updated_at,
                )
                for sid in sorted_ids[:len(self._sessions) - _MAX_SESSIONS]:
                    del self._sessions[sid]

    # ── 主入口 ──

    async def chat(self, session_id: str, message: str) -> ChatResponse:
        request_id = uuid.uuid4().hex[:12]
        session = self._get_or_create(session_id)
        activities: list[Activity] = []
        called_fingerprints: set[str] = set()
        media: list[dict] = []
        t_start = time.time()

        _logger.info("request=%s session=%s chat started msg_len=%d",
                      request_id, session.session_id[:12], len(message))

        # 构建 messages
        system_content = _system_with_context(session)
        if not session.messages or session.messages[0].get("role") != "system":
            session.messages.insert(0, {"role": "system", "content": system_content})
        else:
            session.messages[0]["content"] = system_content
        session.messages.append({"role": "user", "content": message})

        api_key = _os.getenv("LLM_API_KEY")
        base_url = _os.getenv("LLM_BASE_URL")
        model = _os.getenv("LLM_MODEL")

        if not all([api_key, base_url, model]):
            return ChatResponse(
                success=False, session_id=session.session_id,
                request_id=request_id,
                reply="Chat 不可用。请在 .env 中配置 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL。",
            )

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                for _round in range(_MAX_ROUNDS):
                    resp = await client.post(
                        f"{base_url}/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": model,
                            "max_tokens": 2048,
                            "messages": session.messages,
                            "tools": CHAT_TOOLS_SCHEMA,
                        },
                    )

                    if resp.status_code != 200:
                        return ChatResponse(
                            success=False, session_id=session.session_id,
                            request_id=request_id,
                            reply=f"LLM 调用失败: {resp.status_code}",
                        )

                    data = resp.json()
                    choice = (data.get("choices") or [{}])[0]
                    msg = choice.get("message", {})
                    assistant_text = msg.get("content", "")
                    tool_calls = msg.get("tool_calls", [])

                    # 无 tool_calls → 最终回复
                    if not tool_calls:
                        session.messages.append({
                            "role": "assistant",
                            "content": assistant_text or "操作已完成。",
                        })
                        self._trim_messages(session)
                        _logger.info("request=%s chat finished rounds=%d total_duration=%dms",
                                     request_id, _round + 1,
                                     round((time.time() - t_start) * 1000))
                        return ChatResponse(
                            success=True, session_id=session.session_id,
                            request_id=request_id,
                            reply=assistant_text or "操作已完成。",
                            media=media, activities=[a.__dict__ for a in activities],
                            context=self._build_context(session),
                        )

                    # 有 tool_calls → 执行工具
                    session.messages.append({
                        "role": "assistant",
                        "content": assistant_text or "",
                        "tool_calls": tool_calls,
                    })

                    for tc in tool_calls:
                        fn = tc.get("function", {})
                        tool_name = fn.get("name", "")
                        tool_args = _safe_json(fn.get("arguments", "{}"))

                        # 校验 + 自动补齐
                        is_valid, validation_result = self._validate(
                            tool_name, tool_args, session
                        )

                        act = Activity(
                            tool=tool_name,
                            label=_tool_label(tool_name),
                            status="success" if is_valid else "error",
                        )
                        t0 = time.time()

                        if not is_valid:
                            act.error = validation_result.get("error", {}).get("detail", "")
                            act.status = "error"
                            act.result = validation_result
                            tool_result = validation_result
                        else:
                            # 重复调用保护 — 仅限本轮，下一条用户消息重置
                            if _is_duplicate_tool_call(called_fingerprints, tool_name, validation_result):
                                act.status = "error"
                                act.error = "本轮对话中相同参数重复调用"
                                tool_result = _tool_error("DUPLICATE_TOOL_CALL")
                            else:
                                try:
                                    func = CHAT_TOOL_MAP[tool_name]
                                    result = await asyncio.to_thread(func, **validation_result)
                                    # 将 TextContent 列表转为纯文本，避免 JSON 序列化报错
                                    if isinstance(result, list):
                                        act.result = "\n".join(r.text for r in result if hasattr(r, "text"))
                                    else:
                                        act.result = result
                                    if isinstance(result, dict) and not result.get("success", True):
                                        act.status = "error"
                                        act.error = result.get("message", "")
                                    self._update_context(session, tool_name, validation_result, result)
                                    tool_result = result
                                except Exception as exc:
                                    act.status = "error"
                                    act.error = str(exc)
                                    tool_result = _tool_error("TOOL_EXECUTION_FAILED", str(exc))

                        act.duration_ms = round((time.time() - t0) * 1000)
                        act.summary = _result_summary(act)

                        _logger.info("request=%s tool=%s duration=%dms success=%s",
                                     request_id, tool_name, act.duration_ms,
                                     act.status == "success")

                        # show_image：用原始 image_path 注册 HTTP URL 供前端渲染
                        if tool_name == "show_image" and act.status == "success":
                            img_path = validation_result.get("image_path", "")
                            if img_path:
                                from servers.image_tools import register_image_url
                                image_url = register_image_url(img_path)
                                if image_url:
                                    media.append({"type": "image", "url": image_url, "name": Path(img_path).name})

                        activities.append(act)

                        # 工具结果交回模型
                        serialized = tool_result
                        if isinstance(tool_result, list):
                            text_parts = []
                            for item in tool_result:
                                if hasattr(item, "text"):
                                    text_parts.append(item.text)
                            serialized = "\n".join(text_parts) if text_parts else _json.dumps(tool_result, ensure_ascii=False)
                        else:
                            serialized = _json.dumps(tool_result, ensure_ascii=False)
                        session.messages.append({
                            "role": "tool",
                            "tool_call_id": tc.get("id", ""),
                            "name": tool_name,
                            "content": serialized,
                        })

                # 超过最大轮数
                _logger.warning("request=%s tool loop limit reached rounds=%d",
                                request_id, _MAX_ROUNDS)
                return ChatResponse(
                    success=False, session_id=session.session_id,
                    request_id=request_id,
                    reply=f"工具调用轮数超过上限（{_MAX_ROUNDS} 轮），请简化你的问题或补充必要信息。",
                    media=media, activities=[a.__dict__ for a in activities],
                    context=self._build_context(session),
                )

        except httpx.RequestError as exc:
            _logger.error("request=%s llm_request_failed error=%s", request_id, exc)
            return ChatResponse(
                success=False, session_id=session.session_id,
                request_id=request_id,
                reply=f"模型接口连接失败: {exc}",
            )
        except Exception:
            _logger.exception("request=%s chat internal error", request_id)
            return ChatResponse(
                success=False, session_id=session.session_id,
                request_id=request_id,
                reply="聊天服务内部错误，请重试。",
                media=media, activities=[a.__dict__ for a in activities],
            )

    # ── 工具校验 ──

    def _validate(self, tool_name: str, args: dict, session: ChatSession) -> tuple[bool, dict]:
        """校验工具参数，必要时自动补齐。返回 (is_valid, args_or_error_dict)。"""
        func = CHAT_TOOL_MAP.get(tool_name)
        if func is None:
            return False, _tool_error("TOOL_EXECUTION_FAILED", f"未知工具: {tool_name}")

        if isinstance(args, list):
            return False, _tool_error("INVALID_PATH", f"{tool_name} 的参数格式错误，不应为数组")

        # 通用：空字符串拒绝
        for key, val in args.items():
            if isinstance(val, str) and val.strip() == "":
                if key in ("project_path", "folder_path", "netlist_path",
                           "raw_path", "img_path", "csv_path", "image_path",
                           "component_id", "result_paths", "curve"):
                    return False, _tool_error("MISSING_REQUIRED_ARGUMENT",
                                              f"{key} 不能为空，请提供正确的 {key}")

        # 自动补齐 project_path
        if tool_name not in ("list_epp_projects", "launch_edi", "compare_simulation_results",
                              "turbocharts_convert", "show_image", "copy_image_to_workspace", "simulate_netlist_with_ads",
                              "get_simulation_async_status", "get_simulation_async_result"):
            if not args.get("project_path"):
                if session.current_project_path:
                    args = dict(args, project_path=session.current_project_path)
                else:
                    return False, _tool_error("NO_CURRENT_PROJECT",
                                              "当前没有选定工程，请先提供工程路径或让我扫描目录")

        # 自动补齐仿真 task_id
        if tool_name in ("get_simulation_async_status", "get_simulation_async_result"):
            if not args.get("task_id"):
                if session.last_simulation_task_id:
                    args = dict(args, task_id=session.last_simulation_task_id)
                else:
                    return False, _tool_error("MISSING_REQUIRED_ARGUMENT",
                                              "没有可查询的仿真任务，请先执行 start_simulation_async")

        return True, args

    # ── 上下文更新 ──

    def _update_context(self, session: ChatSession, tool_name: str, args: dict, result: Any) -> None:
        """工具执行成功后更新会话上下文。"""
        if not isinstance(result, dict) or not result.get("success"):
            return

        if tool_name == "list_epp_projects":
            session.last_folder_path = args.get("folder_path")
            session.last_projects = result.get("projects", [])

        elif tool_name == "open_edi_project":
            session.current_project_path = args.get("project_path")
            session.current_project_name = (
                Path(args["project_path"]).stem if args.get("project_path") else None
            )

        elif tool_name == "close_edi_project":
            session.current_project_path = None
            session.current_project_name = None

        elif tool_name == "start_simulation_async":
            task_id = result.get("task_id")
            if task_id:
                session.last_simulation_task_id = task_id
                session.simulation_task_ids.append(task_id)
                session.simulation_task_ids = session.simulation_task_ids[-20:]

    # ── 上下文导出 ──

    def _build_context(self, session: ChatSession) -> dict:
        sim_status = None
        sim_ads_output = ""
        sim_log_complete = False
        if session.last_simulation_task_id:
            try:
                status_result = get_simulation_async_status(session.last_simulation_task_id)
                sim_status = status_result.get("status")
                sim_ads_output = status_result.get("ads_output", "")
                sim_log_complete = status_result.get("log_complete", False)
            except Exception:
                pass
        return {
            "current_project_name": session.current_project_name,
            "simulation_task_id": session.last_simulation_task_id,
            "simulation_status": sim_status,
            "simulation_ads_output_tail": sim_ads_output[-2000:] if sim_ads_output else "",
            "simulation_log_complete": sim_log_complete,
        }

    # ── 消息裁剪 ──

    def _trim_messages(self, session: ChatSession) -> None:
        """按完整轮次裁剪，不从 tool_calls 中间切断。"""
        messages = session.messages
        if len(messages) <= _MAX_MESSAGES:
            return

        system_msgs = [m for m in messages if m.get("role") == "system"]
        conversation = [m for m in messages if m.get("role") != "system"]

        # 从截断点向前查找最近的 user 消息边界
        start = max(0, len(conversation) - _MAX_MESSAGES)
        while start > 0 and conversation[start].get("role") != "user":
            start -= 1

        session.messages = system_msgs + conversation[start:]


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _is_duplicate_tool_call(
    called: set[str],
    tool_name: str,
    arguments: dict[str, Any],
) -> bool:
    """检查本轮是否已用相同参数调用过该工具。"""
    fingerprint = (
        f"{tool_name}:"
        f"{_json.dumps(arguments, sort_keys=True, ensure_ascii=False)}"
    )
    if fingerprint in called:
        return True
    called.add(fingerprint)
    return False


def _safe_json(raw: str) -> dict:
    try:
        val = _json.loads(raw)
        return val if isinstance(val, dict) else {}
    except (_json.JSONDecodeError, TypeError):
        return {}


_TOOL_LABELS: dict[str, str] = {
    "list_epp_projects": "扫描工程",
    "open_edi_project": "打开工程",
    "close_edi_project": "关闭工程",
    "list_project_components": "列出元件",
    "get_component_parameters": "查询参数",
    "get_project_summary": "工程概览",
    "start_simulation_async": "启动仿真",
    "get_simulation_async_status": "查询进度",
    "get_simulation_async_result": "获取结果",
    "capture_schematic": "截图原理图",
    "export_project_netlist": "导出网表",
    "replace_models_from_csv": "替换模型",
    "launch_edi": "启动 EDI",
    "compare_simulation_results": "对比结果",
    "turbocharts_convert": "RAW 转图",
    "show_image": "显示图片",
    "get_simulation_component_schema": "查询参数",
    "list_simulation_components": "查询器件",
    "upsert_simulation_component": "仿真器件",
    "delete_simulation_component": "删除器件",
}
if OPENCLAW_WORKSPACE_PATH is not None:
    _TOOL_LABELS["copy_image_to_workspace"] = "复制到工作区"


def _tool_label(name: str) -> str:
    return _TOOL_LABELS.get(name, name)


def _result_summary(act: Activity) -> str:
    if act.status == "error":
        return act.error or "执行失败"
    r = act.result
    if isinstance(r, dict):
        if r.get("success"):
            if "count" in r:
                return f"找到 {r['count']} 个工程"
            if "total" in r:
                return f"共 {r['total']} 个元件"
            if "task_id" in r:
                return f"任务: {r['task_id']}"
            return "OK"
        return r.get("message", "执行失败")[:80]
    return "OK"
