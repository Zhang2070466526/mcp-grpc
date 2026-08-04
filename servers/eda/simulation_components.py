r"""仿真器件管理工具。

get_simulation_component_schema  查询器件支持的参数、类型和单位
list_simulation_components       查询工程中的仿真器件
upsert_simulation_component      新增或更新仿真器件（调用前校验参数）
delete_simulation_component      删除仿真器件

协议：UPSERT_SIMULATION_COMPONENT (11) / DELETE_SIMULATION_COMPONENT (12)
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from proto import ecserver_pb2
from servers.eda.config import ProjectReader, parse_components, parse_paramsinfo, validate_project_path
from servers.eda.grpc_client import call_grpc
from servers.mcp_instance import mcp

_logger = logging.getLogger("sim_components")

_COMPONENT_TYPES = {"SParameter", "HarmonicBalance", "XDB"}


# ═══════════════════════════════════════════════════════════
# 参数目录
# ═══════════════════════════════════════════════════════════

@lru_cache(maxsize=1)
def _load_catalog() -> dict:
    try:
        here = Path(__file__).parent
        path = here / "simulation_component_catalog.json"
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        _logger.error("Failed to load component catalog: %s", exc)
        return {}


def _catalog_component(component_type: str) -> dict:
    cat = _load_catalog()
    comps = cat.get("components", {})
    return comps.get(component_type, {})


# ═══════════════════════════════════════════════════════════
# 参数校验
# ═══════════════════════════════════════════════════════════

def _validate_component_parameters(
    component_type: str,
    parameters: dict,
) -> tuple[bool, dict | None]:
    """校验参数是否合法。advisory 模式只做结构校验不拦截未知参数。"""
    catalog = _load_catalog()
    if not catalog:
        return False, {
            "success": False,
            "error_code": "COMPONENT_SCHEMA_UNAVAILABLE",
            "message": "仿真控件参数目录加载失败，请检查 simulation_component_catalog.json。",
        }

    comp = _catalog_component(component_type)
    if not comp:
        return False, {
            "success": False,
            "error_code": "UNSUPPORTED_COMPONENT_TYPE",
            "message": f"不支持的控件类型: {component_type}",
            "supported_component_types": sorted(_COMPONENT_TYPES),
        }

    if not isinstance(parameters, dict) or not parameters:
        return False, {
            "success": False,
            "error_code": "INVALID_PARAMETERS",
            "message": "parameters 必须是非空 JSON 对象",
        }

    schema_params = comp.get("parameters", {})
    mode = comp.get("validation_mode", "advisory")

    if mode == "strict":
        unsupported = [k for k in parameters if k not in schema_params]
        if unsupported:
            return False, {
                "success": False,
                "error_code": "UNSUPPORTED_PARAMETER",
                "message": f"{component_type} 不支持参数: {', '.join(sorted(unsupported))}",
                "unsupported_parameters": sorted(unsupported),
                "supported_parameters": sorted(schema_params.keys()),
                "hint": "请调用 get_simulation_component_schema 查询完整参数定义",
            }

    for pname, pval in parameters.items():
        schema = schema_params.get(pname, {})
        if not schema:
            continue  # advisory mode: skip deep validation for unknown params

        if schema.get("readonly"):
            return False, {
                "success": False,
                "error_code": "READONLY_PARAMETER",
                "message": f"参数 {pname} 严禁修改，请移除后重试。",
            }

        if not isinstance(pval, dict):
            return False, {
                "success": False,
                "error_code": "INVALID_PARAMETER_VALUE",
                "message": f"参数 {pname} 的值必须是对象",
            }
        extra = set(pval.keys()) - {"value", "unit"}
        if extra:
            return False, {
                "success": False,
                "error_code": "INVALID_PARAMETER_VALUE",
                "message": f"参数 {pname} 包含多余字段: {', '.join(sorted(extra))}",
            }

        if "value" not in pval:
            return False, {"success": False, "error_code": "MISSING_VALUE", "message": f"参数 {pname} 缺少 value"}

        raw = pval["value"]
        if raw is None:
            return False, {"success": False, "error_code": "INVALID_VALUE", "message": f"参数 {pname} 的 value 不能为 null"}

        vt = schema.get("value_type", "string")
        if vt in ("number", "integer"):
            try:
                float(str(raw))
            except (ValueError, TypeError):
                return False, {"success": False, "error_code": "INVALID_VALUE", "message": f"参数 {pname} 的值必须是 {vt}"}

        ev = schema.get("enum_values", [])
        if ev and str(raw) not in ev:
            return False, {"success": False, "error_code": "INVALID_ENUM_VALUE", "message": f"参数 {pname} 值不在允许范围: {', '.join(ev)}"}

        has_unit = "unit" in pval
        if schema.get("unit_required") and not has_unit:
            return False, {"success": False, "error_code": "MISSING_UNIT", "message": f"参数 {pname} 需要 unit"}
        if not schema.get("unit_required") and has_unit:
            return False, {"success": False, "error_code": "UNSUPPORTED_UNIT", "message": f"参数 {pname} 不需要 unit"}
        if has_unit:
            allowed = schema.get("units", [])
            if allowed and pval["unit"] not in allowed:
                return False, {"success": False, "error_code": "UNSUPPORTED_UNIT", "message": f"参数 {pname} 不支持单位 {pval['unit']}"}

    return True, None


def _to_wire_parameters(component_type: str, parameters: dict) -> dict:
    """将公共参数名转换为 gRPC 实际参数名。"""
    comp = _catalog_component(component_type)
    defs = comp.get("parameters", {})
    wire = {}
    for pub, val in parameters.items():
        wn = defs.get(pub, {}).get("wire_name", pub) or pub
        wire[wn] = val
    return wire


def _from_wire_parameters(component_type: str, parameters: dict) -> dict:
    """将 gRPC 实际参数名反向转换为公共参数名。"""
    comp = _catalog_component(component_type)
    defs = comp.get("parameters", {})
    reverse = {d.get("wire_name", pub) or pub: pub for pub, d in defs.items()}
    return {reverse.get(k, k): v for k, v in parameters.items()}


# ═══════════════════════════════════════════════════════════
# 内部辅助
# ═══════════════════════════════════════════════════════════

def _find_sim_components(project_path: str, component_type: str = "") -> list[dict]:
    reader = ProjectReader(project_path)
    schematics = reader.list_schematics()
    results = []
    for sname in schematics:
        raw = reader.read_schematic(sname)
        if not raw:
            continue
        for comp in parse_components(raw):
            ct = comp.get("type", "")
            if ct not in _COMPONENT_TYPES:
                continue
            if component_type and ct != component_type:
                continue
            params = _simplified_params(comp)
            results.append({
                "component_type": ct,
                "instance_name": comp.get("name", ""),
                "component_id": comp.get("component_id", ""),
                "schematic": sname,
                "parameters": _from_wire_parameters(ct, params),
                "enabled": _get_enabled_state(comp, ct),
            })
    return results


def _simplified_params(comp: dict) -> dict:
    parsed = parse_paramsinfo(comp.get("paramsinfo", {}))
    return {k: {"value": v["value"], "unit": v["unit"]} for k, v in parsed.items()}


def _get_enabled_state(comp: dict, ct: str) -> bool | None:
    schema = _catalog_component(ct)
    control = schema.get("enable_control")
    if not control:
        return None
    param = control.get("parameter")
    val = comp.get("paramsinfo", {}).get(param, {}).get("Value")
    if val == control.get("enabled_value"):
        return True
    if val == control.get("disabled_value"):
        return False
    return None


# ═══════════════════════════════════════════════════════════
# 1. get_simulation_component_schema
# ═══════════════════════════════════════════════════════════

@mcp.tool()
def get_simulation_component_schema(
    component_type: str,
    parameter_name: str = "",
) -> dict[str, Any]:
    """查询仿真控件支持的参数、值类型和单位。

    创建或修改 SParameter、HarmonicBalance、XDB 前，如果不确定参数名，
    必须先调用本工具。不要根据经验猜测参数名。

    Args:
        component_type: SParameter / HarmonicBalance / XDB。
        parameter_name: 指定参数名时只返回该参数，空则返回全部。
    """
    catalog = _load_catalog()
    if not catalog:
        return {
            "success": False,
            "error_code": "COMPONENT_SCHEMA_UNAVAILABLE",
            "message": "仿真控件参数目录加载失败。",
        }

    comp = _catalog_component(component_type)
    if not comp:
        return {
            "success": False,
            "error_code": "UNSUPPORTED_COMPONENT_TYPE",
            "message": f"不支持的控件类型: {component_type}",
            "supported_component_types": sorted(_COMPONENT_TYPES),
        }

    params = comp.get("parameters", {})
    if parameter_name:
        p = params.get(parameter_name)
        if not p:
            return {
                "success": False,
                "error_code": "UNSUPPORTED_PARAMETER",
                "message": f"{component_type} 不支持参数 {parameter_name}",
                "supported_parameters": sorted(params.keys()),
            }
        params = {parameter_name: p}

    return {
        "success": True,
        "component_type": component_type,
        "display_name": comp.get("display_name", ""),
        "schema_version": catalog.get("schema_version", ""),
        "parameters": params,
        "example": comp.get("example", {}),
        "readonly_parameters": [k for k, v in comp.get("parameters", {}).items() if v.get("readonly")],
    }


# ═══════════════════════════════════════════════════════════
# 2. list_simulation_components
# ═══════════════════════════════════════════════════════════

@mcp.tool()
def list_simulation_components(
    project_path: str,
    component_type: str = "",
) -> dict[str, Any]:
    """查询工程中的仿真器件（SParameter / HarmonicBalance / XDB）。

    Args:
        project_path: .epp 工程文件绝对路径。
        component_type: 按类型过滤，空则返回全部。
    """
    if component_type and component_type not in _COMPONENT_TYPES:
        return {
            "success": False,
            "message": f"不支持的器件类型: {component_type}，请使用 {', '.join(sorted(_COMPONENT_TYPES))} 或留空",
        }

    reader = ProjectReader(project_path)
    components = _find_sim_components(project_path, component_type)
    return {
        "success": True,
        "project_path": str(reader.epp_path.resolve()),
        "components": components,
    }


# ═══════════════════════════════════════════════════════════
# 3. upsert_simulation_component（带校验）
# ═══════════════════════════════════════════════════════════

@mcp.tool()
def upsert_simulation_component(
    project_path: str,
    component_type: str,
    parameters: dict,
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    """新增或更新仿真器件参数。

    parameters 中的参数名、值和单位必须符合 get_simulation_component_schema 的定义。
    不要使用未查询或未经确认的参数名。

    Args:
        project_path: .epp 工程文件绝对路径。
        component_type: SParameter / HarmonicBalance / XDB。
        parameters: 器件参数，如 {"Start": {"value": "1", "unit": "GHz"}}。
        timeout_seconds: 最长等待秒数。
    """
    resolved = validate_project_path(project_path)

    if component_type not in _COMPONENT_TYPES:
        return {"success": False, "message": f"不支持的器件类型: {component_type}，请使用 {', '.join(sorted(_COMPONENT_TYPES))}"}

    ok, err = _validate_component_parameters(component_type, parameters)
    if not ok:
        return err  # type: ignore[return-value]

    wire_params = _to_wire_parameters(component_type, parameters)
    _logger.info("component=%s public=%s wire=%s", component_type, sorted(parameters), sorted(wire_params))

    return call_grpc(
        ecserver_pb2.UPSERT_SIMULATION_COMPONENT,
        {
            "project_path": resolved,
            "component_type": component_type,
            "parameters": wire_params,
        },
        timeout_seconds,
        max_timeout_seconds=300,
    )


# ═══════════════════════════════════════════════════════════
# 4. delete_simulation_component
# ═══════════════════════════════════════════════════════════

@mcp.tool()
def delete_simulation_component(
    project_path: str,
    component_type: str,
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    """删除仿真器件。同类型超过一个时失败。

    Args:
        project_path: .epp 工程文件绝对路径。
        component_type: SParameter / HarmonicBalance / XDB。
        timeout_seconds: 最长等待秒数。
    """
    resolved = validate_project_path(project_path)

    if component_type not in _COMPONENT_TYPES:
        return {"success": False, "message": f"不支持的器件类型: {component_type}"}

    return call_grpc(
        ecserver_pb2.DELETE_SIMULATION_COMPONENT,
        {
            "project_path": resolved,
            "component_type": component_type,
        },
        timeout_seconds,
        max_timeout_seconds=300,
    )
