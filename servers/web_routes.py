"""Web 路由 — /health, /chat, /ui, /。"""

from __future__ import annotations

import asyncio
import json as _json
import os as _os
from pathlib import Path

import httpx
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

from servers.eda.config import EDA_GRPC_SERVER
from servers.eda.project_manage import (
    open_eda_project, close_eda_project,
    list_epp_projects, list_project_components,
    get_component_parameters, get_project_summary,
)
from servers.eda.simulation import simulate_project, simulate_netlist_with_ads
from servers.eda.design_export import export_project_netlist, capture_schematic
from servers.eda.model_replace import replace_models_from_csv
from servers.eda.edi_launcher import launch_edi
from servers.turbocharts.compare_results import compare_simulation_results
from servers.turbocharts.convert_raw import turbocharts_convert

import sys as _sys
if getattr(_sys, "frozen", False):
    # PyInstaller packaged — look in _MEIPASS
    _CLIENT_HTML_PATH = Path(_sys._MEIPASS) / "scripts" / "chat_client.html"
else:
    _CLIENT_HTML_PATH = Path(__file__).resolve().parent.parent / "scripts" / "chat_client.html"


async def _check_tcp(endpoint: str) -> bool:
    try:
        host, port_text = endpoint.rsplit(":", 1)
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, int(port_text)),
            timeout=0.5,
        )
        writer.close()
        await writer.wait_closed()
        return True
    except (OSError, ValueError, asyncio.TimeoutError):
        return False


async def ui_page(request: Request):
    if _CLIENT_HTML_PATH.is_file():
        return HTMLResponse(_CLIENT_HTML_PATH.read_text(encoding="utf-8"))
    return HTMLResponse("<h2>chat_client.html not found</h2>", status_code=404)


async def health_check(request: Request):
    eda_ready = await _check_tcp(EDA_GRPC_SERVER)
    tc_path = _os.getenv("TURBOCHARTS_PATH", "")
    turbocharts_ready = bool(tc_path) and Path(tc_path).is_file()
    return JSONResponse({
        "status": "ok" if eda_ready else "degraded",
        "version": "0.1.0",
        "mcp_ready": True,
        "eda_grpc_ready": eda_ready,
        "turbocharts_ready": turbocharts_ready,
        "eda_grpc_server": EDA_GRPC_SERVER,
    })


async def chat_endpoint(request: Request):
    body = await request.json()
    user_msg = body.get("message", "").strip()
    if not user_msg:
        return JSONResponse({"error": "message required"}, status_code=400)

    tool_map = {
        "open_eda_project": open_eda_project,
        "close_eda_project": close_eda_project,
        "list_epp_projects": list_epp_projects,
        "list_project_components": list_project_components,
        "get_component_parameters": get_component_parameters,
        "get_project_summary": get_project_summary,
        "simulate_project": simulate_project,
        "simulate_netlist_with_ads": simulate_netlist_with_ads,
        "capture_schematic": capture_schematic,
        "export_project_netlist": export_project_netlist,
        "replace_models_from_csv": replace_models_from_csv,
        "launch_edi": launch_edi,
        "compare_simulation_results": compare_simulation_results,
        "turbocharts_convert": turbocharts_convert,
    }

    tools = [
        *_rtool("list_epp_projects", "Scan a folder for .epp project files", {"folder_path": "string"}),
        *_rtool("open_eda_project", "Open an .epp EDA project", {"project_path": "string"}, {"timeout_seconds": "integer"}),
        *_rtool("close_eda_project", "Close an EDA project", {"project_path": "string"}, {"need_save": "boolean"}),
        *_rtool("list_project_components", "List components in schematic", {"project_path": "string"}, {"schematic_name": "string", "component_type": "string", "name_contains": "string"}),
        *_rtool("get_component_parameters", "Get parameters of a component", {"project_path": "string", "component_id": "string"}, {"schematic_name": "string", "include_hidden": "boolean"}),
        *_rtool("get_project_summary", "Get overview of an EDA project", {"project_path": "string"}, {"include_component_types": "boolean", "include_latest_result": "boolean"}),
        *_rtool("simulate_project", "Run simulation on a project", {"project_path": "string"}, {"log_source": "string", "timeout_seconds": "integer"}),
        *_rtool("simulate_netlist_with_ads", "Call ADS simulation controller", {"netlist_path": "string"}, {"ads_path": "string", "timeout_seconds": "integer"}),
        *_rtool("capture_schematic", "Capture schematic as image", {"project_path": "string", "img_path": "string"}, {"timeout_seconds": "integer"}),
        *_rtool("export_project_netlist", "Export netlist of a project", {"project_path": "string"}, {"timeout_seconds": "integer"}),
        *_rtool("replace_models_from_csv", "Replace models via CSV", {"project_path": "string", "csv_path": "string"}, {"timeout_seconds": "integer"}),
        *_rtool("launch_edi", "Launch EDI client", {}, {"edi_path": "string", "wait_for_grpc": "boolean", "wait_timeout": "integer"}),
        *_rtool("compare_simulation_results", "Compare curves across RAW files", {"result_paths": "array", "curve": "string", "img_path": "string"}, {"chart_type": "string", "labels": "array", "dependency": "string", "csv_path": "string", "alignment": "string", "reference_index": "integer"}),
        *_rtool("turbocharts_convert", "Convert RAW to chart and CSV", {"raw_path": "string", "img_path": "string", "chart_type": "string"}, {"csv_path": "string", "linename": "string", "dependency": "string", "ac_config": "string"}),
    ]

    api_key = _os.getenv("LLM_API_KEY")
    base_url = _os.getenv("LLM_BASE_URL")
    model = _os.getenv("LLM_MODEL")

    if not api_key or not base_url or not model:
        return JSONResponse({
            "reply": "Chat not available. Configure LLM_API_KEY/LLM_BASE_URL/LLM_MODEL in .env, or use MCP client to call tools directly.",
            "tool_call": None,
        })

    messages: list[dict] = [
        {"role": "system", "content": "You are an EDA engineering assistant. Use tools to help. Reply in Chinese."},
        {"role": "user", "content": user_msg},
    ]

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{base_url}/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "max_tokens": 2048, "messages": messages, "tools": tools},
        )
        if resp.status_code != 200:
            return JSONResponse({"error": f"LLM error: {resp.status_code} {resp.text[:200]}"})

        data = resp.json()
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message", {})
        reply_text = msg.get("content", "")
        tool_calls = msg.get("tool_calls", [])

        tool_name = ""
        tool_args = {}
        if tool_calls:
            tc = tool_calls[0]
            fn = tc.get("function", {})
            tool_name = fn.get("name", "")
            try:
                tool_args = _json.loads(fn.get("arguments", "{}"))
            except _json.JSONDecodeError:
                tool_args = {}
            func = tool_map.get(tool_name)
            if func:
                try:
                    tool_result = await asyncio.to_thread(func, **tool_args)
                    reply_text = _json.dumps(tool_result, ensure_ascii=False, indent=2)
                    if len(reply_text) > 3000:
                        reply_text = reply_text[:3000] + "\n...(truncated)"
                except Exception as exc:
                    reply_text = f"Tool error: {exc}"

    return JSONResponse({
        "reply": reply_text or "Done.",
        "tool_call": tool_name or None,
        "tool_args": tool_args if tool_name else None,
    })


def _rtool(name: str, desc: str, required: dict, optional: dict | None = None) -> list[dict]:
    """Build tool schema with proper required/optional split."""
    props = {}
    for k, t in {**required, **(optional or {})}.items():
        if t == "array":
            props[k] = {"type": "array", "items": {"type": "string"}}
        else:
            props[k] = {"type": t}
    return [{"type": "function", "function": {"name": name, "description": desc, "parameters": {"type": "object", "properties": props, "required": list(required.keys())}}}]
