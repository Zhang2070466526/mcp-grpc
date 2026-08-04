r"""仿真器件管理工具 — 协议 v2。

get_simulation_component_schema  查询器件支持的参数、类型、单位和权限
list_simulation_components       查询工程中的仿真器件及其参数
create_simulation_component      新增仿真器件（每次创建新实例）
update_simulation_component      按实例名更新参数（自动识别类型）
delete_simulation_component      按实例名删除器件（EDI 直接执行）
set_component_active_state       确定性设置 NORMAL/DISABLED/SHORTED
generate_schematic_from_netlist  从网表追加或重建 main 原理图

协议枚举：
  CREATE_SIMULATION_COMPONENT = 11
  DELETE_SIMULATION_COMPONENT = 12
  GENERATE_SCHEMATIC_FROM_NETLIST = 13
  SET_COMPONENT_ACTIVE_STATE = 14
  UPDATE_SIMULATION_COMPONENT = 15
"""

from __future__ import annotations

import json as _json
import logging
import math
import re as _re
from functools import lru_cache
from pathlib import Path
from typing import Any

from proto import ecserver_pb2
from servers.eda.config import (
    ProjectReader,
    parse_components,
    validate_project_path,
)
from servers.eda.grpc_client import call_grpc
from servers.mcp_instance import mcp

_logger = logging.getLogger("sim_components")

_COMPONENT_TYPES = {"SParameter", "HarmonicBalance", "XDB"}
_ACTIVE_STATES = {"NORMAL", "DISABLED", "SHORTED"}


# ═══════════════════════════════════════════════════════════
# Catalog
# ═══════════════════════════════════════════════════════════

@lru_cache(maxsize=1)
def _load_catalog() -> dict:
    try:
        here = Path(__file__).parent
        path = here / "simulation_component_catalog.json"
        return _json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, _json.JSONDecodeError) as exc:
        _logger.error("Failed to load component catalog: %s", exc)
        return {}


def _catalog_component(component_type: str) -> dict:
    cat = _load_catalog()
    return cat.get("components", {}).get(component_type, {})


# ═══════════════════════════════════════════════════════════
# 参数解析
# ═══════════════════════════════════════════════════════════

def _resolve_parameter_schema(
    component_type: str,
    parameter_name: str,
) -> tuple[dict | None, str]:
    """Resolve a public parameter name to its schema and wire name.

    Search order:
      1. Fixed parameters (exact match).
      2. Dynamic patterns (Freq[{index}], Order[{index}]).

    Returns (parameter_schema, wire_name).  schema is None on failure.
    """
    comp = _catalog_component(component_type)
    if not comp:
        return None, ""

    # 1. Fixed parameters
    fixed = comp.get("parameters", {})
    if parameter_name in fixed:
        return fixed[parameter_name], fixed[parameter_name].get("wire_name", parameter_name)

    # 2. Dynamic patterns
    patterns = comp.get("parameter_patterns", [])
    for pat in patterns:
        public_pattern = pat.get("public_pattern", "")
        # 把 {index} 替换成捕获组
        regex = _re.escape(public_pattern).replace(r"\{index\}", r"(\d+)")
        m = _re.fullmatch(regex, parameter_name)
        if m:
            index = int(m.group(1))
            idx_min = pat.get("index_min", 1)
            idx_max = pat.get("index_max", 32)
            if index < idx_min or index > idx_max:
                return None, ""
            wire_pattern = pat.get("wire_pattern", public_pattern)
            wire_name = wire_pattern.replace("{index}", str(index))
            return pat, wire_name

    return None, ""


def _prepare_parameters(
    component_type: str,
    parameters: dict,
    operation: str,
    *,
    allow_empty: bool,
) -> tuple[dict | None, dict | None]:
    """Validate and convert public parameters to wire parameters.

    Returns (wire_parameters, error).  One is always None.

    Checks (in order):
      1. parameters must be a dict
      2. Empty check based on operation
      3. Component type exists in catalog
      4. Each parameter name resolves via _resolve_parameter_schema
      5. create_allowed / update_allowed based on operation
      6. Each value must be a dict with only "value" / "unit"
      7. "value" must be present, not null/array/object
      8. Value type validation (number / integer / boolean / enum)
      9. Unit validation (required, allowed values)

    Args:
        component_type: "SParameter", "HarmonicBalance", or "XDB".
        parameters: Public parameter dict.
        operation: "create" or "update".
        allow_empty: If True, empty parameters dict is OK.
    """
    if not isinstance(parameters, dict):
        return None, _param_error("INVALID_PARAMETERS",
                                   "parameters 必须是对象", component_type)

    cat = _load_catalog()
    if not cat:
        return None, _param_error("COMPONENT_SCHEMA_UNAVAILABLE",
                                   "仿真控件参数目录加载失败", component_type)

    comp = _catalog_component(component_type)
    if not comp:
        return None, _param_error("UNSUPPORTED_COMPONENT_TYPE",
                                   f"不支持的控件类型: {component_type}",
                                   component_type,
                                   supported_types=sorted(_COMPONENT_TYPES))

    # Empty check
    if not parameters:
        if allow_empty:
            return {}, None
        return None, _param_error("INVALID_PARAMETERS",
                                   "parameters 必须是非空对象", component_type)

    # Parameter schema
    schemas: dict[str, tuple[dict, str]] = {}
    for pname in parameters:
        schema, wire = _resolve_parameter_schema(component_type, pname)
        if schema is None:
            return None, _param_error("UNSUPPORTED_PARAMETER",
                                       f"{component_type} 不支持参数: {pname}",
                                       component_type, parameter=pname,
                                       supported_parameters=_supported_param_names(component_type))
        schemas[pname] = (schema, wire)

    # Permission check
    for pname, (schema, wire) in schemas.items():
        if operation == "create" and not schema.get("create_allowed", False):
            return None, _param_error("CREATE_PARAMETER_NOT_ALLOWED",
                                       f"{component_type}.{pname} 不允许在创建时设置",
                                       component_type, parameter=pname)
        if operation == "update" and not schema.get("update_allowed", False):
            return None, _param_error("UPDATE_PARAMETER_NOT_ALLOWED",
                                       f"{component_type}.{pname} 不允许更新",
                                       component_type, parameter=pname)

    # Value validation
    wire_params: dict = {}
    for pname, (schema, wire_name) in schemas.items():
        pval = parameters[pname]

        # Must be dict
        if not isinstance(pval, dict):
            return None, _param_error("INVALID_PARAMETER_VALUE",
                                       f"参数 {pname} 的值必须是对象 {{\"value\": ...}}",
                                       component_type, parameter=pname)

        # Only "value" and "unit" allowed
        extra = set(pval.keys()) - {"value", "unit"}
        if extra:
            return None, _param_error("INVALID_PARAMETER_VALUE",
                                       f"参数 {pname} 包含多余字段: {', '.join(sorted(extra))}",
                                       component_type, parameter=pname)

        # "value" required
        if "value" not in pval:
            return None, _param_error("MISSING_VALUE",
                                       f"参数 {pname} 缺少 value",
                                       component_type, parameter=pname)

        raw_value = pval["value"]

        # value must not be null, array, or object
        if raw_value is None:
            return None, _param_error("INVALID_VALUE",
                                       f"参数 {pname} 的 value 不能为 null",
                                       component_type, parameter=pname)
        if isinstance(raw_value, (list, dict)):
            return None, _param_error("INVALID_VALUE",
                                       f"参数 {pname} 的 value 必须是标量",
                                       component_type, parameter=pname)

        # Type validation
        vt = schema.get("value_type", "string")
        if vt in ("number", "integer"):
            try:
                num = float(str(raw_value))
            except (ValueError, TypeError):
                return None, _param_error("INVALID_VALUE",
                                           f"参数 {pname} 的值必须是 {vt}",
                                           component_type, parameter=pname)
            if not math.isfinite(num):
                return None, _param_error("INVALID_VALUE",
                                           f"参数 {pname} 的值不能是 NaN 或 Infinity",
                                           component_type, parameter=pname)
            if vt == "integer" and not num.is_integer():
                return None, _param_error("INVALID_VALUE",
                                           f"参数 {pname} 的值必须是整数",
                                           component_type, parameter=pname)

        # Enum check
        ev = schema.get("enum_values", [])
        if ev and str(raw_value) not in ev:
            return None, _param_error("INVALID_ENUM_VALUE",
                                       f"参数 {pname} 的值必须是 {'/'.join(ev)}",
                                       component_type, parameter=pname,
                                       allowed_values=ev)

        # Unit validation
        unit_required = schema.get("unit_required", False)
        if unit_required and "unit" not in pval:
            return None, _param_error("MISSING_UNIT",
                                       f"参数 {pname} 需要 unit",
                                       component_type, parameter=pname)
        if not unit_required and "unit" in pval:
            return None, _param_error("UNSUPPORTED_UNIT",
                                       f"参数 {pname} 不需要 unit",
                                       component_type, parameter=pname)

        if "unit" in pval:
            unit_val = pval["unit"]
            if not isinstance(unit_val, str) or not unit_val.strip():
                return None, _param_error("UNSUPPORTED_UNIT",
                                           f"参数 {pname} 的 unit 必须是有效字符串",
                                           component_type, parameter=pname)
            allowed = schema.get("units", [])
            if allowed and unit_val not in allowed:
                return None, _param_error("UNSUPPORTED_UNIT",
                                           f"参数 {pname} 不支持单位 {unit_val}",
                                           component_type, parameter=pname,
                                           allowed_units=allowed)

        # Detect duplicate (alias conflict): Freq → Freq[1] + Freq[1] → Freq[1]
        if wire_name in wire_params:
            # Find the conflicting public name
            conflicting = next(
                (n for n, (s, w) in schemas.items()
                 if w == wire_name and n != pname),
                pname,
            )
            return None, _param_error("DUPLICATE_PARAMETER_ALIAS",
                                       f"参数 {pname} 和 {conflicting} 映射到同一个底层参数 {wire_name}",
                                       component_type, parameter=pname,
                                       conflicting_parameter=conflicting,
                                       wire_name=wire_name)

        wire_params[wire_name] = pval

    return wire_params, None


def _supported_param_names(component_type: str) -> list[str]:
    """Build a sorted list of supported parameter names for error messages."""
    comp = _catalog_component(component_type)
    names = sorted(comp.get("parameters", {}).keys())
    # Add abbreviated pattern hints
    for pat in comp.get("parameter_patterns", []):
        pp = pat.get("public_pattern", "")
        idx_min = pat.get("index_min", 1)
        idx_max = pat.get("index_max", 32)
        names.append(pp.replace("{index}", f"{{{idx_min}..{idx_max}}}"))
    return names


# ═══════════════════════════════════════════════════════════
# Wire ↔ public name conversion
# ═══════════════════════════════════════════════════════════

def _to_wire_parameters(component_type: str, parameters: dict) -> dict:
    """Convert public parameter names to wire names."""
    result: dict = {}
    for pname, pval in parameters.items():
        schema, wire_name = _resolve_parameter_schema(component_type, pname)
        if wire_name:
            result[wire_name] = pval
        else:
            result[pname] = pval
    return result


def _from_wire_parameters(component_type: str, parameters: dict) -> dict:
    """Convert wire parameter names back to public names."""
    comp = _catalog_component(component_type)
    fixed = comp.get("parameters", {})

    # Build reverse map: wire_name → public_name
    reverse: dict[str, str] = {}
    for pub_name, defn in fixed.items():
        reverse[defn.get("wire_name", pub_name)] = pub_name

    # Also map dynamic patterns (don't override fixed mappings)
    for pat in comp.get("parameter_patterns", []):
        public_pat = pat.get("public_pattern", "")
        wire_pat = pat.get("wire_pattern", public_pat)
        for wire_key in parameters:
            if wire_key in reverse:
                continue  # already mapped by fixed parameter
            wire_regex = _re.escape(wire_pat).replace(r"\{index\}", r"(\d+)")
            m = _re.fullmatch(wire_regex, wire_key)
            if m:
                reverse[wire_key] = public_pat.replace("{index}", m.group(1))

    result: dict = {}
    for wire_name, pval in parameters.items():
        pub_name = reverse.get(wire_name, wire_name)
        result[pub_name] = pval

    return result


# ═══════════════════════════════════════════════════════════
# 实例查找（供 update / delete 复用）
# ═══════════════════════════════════════════════════════════

def _find_component_by_instance(
    project_path: str,
    instance_name: str,
) -> tuple[dict | None, dict | None]:
    """Locate a component by its instance name in saved project files.

    Returns (component, error).  One is always None.
    """
    target = instance_name.strip()
    if not target:
        return None, _component_error("EMPTY_INSTANCE_NAME",
                                       "instance_name 不能为空")

    try:
        reader = ProjectReader(project_path)
    except (FileNotFoundError, ValueError) as exc:
        return None, _component_error("COMPONENT_NOT_FOUND",
                                       f"无法读取工程: {exc}")

    matches: list[dict] = []
    for sname in reader.list_schematics() or []:
        raw = reader.read_schematic(sname)
        if not raw:
            continue
        for comp in parse_components(raw):
            if comp.get("name") != target:
                continue
            matches.append({**comp, "schematic": sname})

    if not matches:
        return None, _component_error("COMPONENT_NOT_FOUND",
                                       f"在已保存工程中未找到器件实例 {target}",
                                       hint="请确认 EDI 中已保存工程，或使用 list_simulation_components 查看当前器件")

    if len(matches) > 1:
        return None, _component_error("AMBIGUOUS_INSTANCE_NAME",
                                       f"发现多个名为 {target} 的器件",
                                       details={"matches": [
                                           {"schematic": m["schematic"],
                                            "component_type": m.get("type", ""),
                                            "component_id": m.get("component_id", "")}
                                           for m in matches
                                       ]})

    return matches[0], None


# ═══════════════════════════════════════════════════════════
# 参数格式化（供 list_simulation_components）
# ═══════════════════════════════════════════════════════════

def _format_component_parameters(
    component_type: str,
    paramsinfo: dict,
) -> dict:
    """Build public-facing parameter dict from raw paramsinfo.

    paramsinfo is the already-parsed dict from parse_paramsinfo().
    Does NOT call parse_paramsinfo again.
    """
    parameters: dict = {}
    for wire_name, metadata in paramsinfo.items():
        if not isinstance(metadata, dict):
            continue

        value = metadata.get("value", "")
        unit = metadata.get("unit", "")

        entry: dict = {"value": value}
        if unit:
            entry["unit"] = unit

        parameters[wire_name] = entry

    return _from_wire_parameters(component_type, parameters)


# ═══════════════════════════════════════════════════════════
# 辅助
# ═══════════════════════════════════════════════════════════

def _param_error(
    code: str,
    message: str,
    component_type: str = "",
    parameter: str = "",
    **extra,
) -> dict:
    result: dict = {
        "success": False,
        "error_code": code,
        "message": message,
    }
    if component_type:
        result.setdefault("details", {})["component_type"] = component_type
    if parameter:
        result.setdefault("details", {})["parameter"] = parameter
    if extra:
        result.setdefault("details", {}).update(extra)
    return result


def _component_error(code: str, message: str, **extra) -> dict:
    result: dict = {"success": False, "error_code": code, "message": message}
    if extra:
        result["details"] = extra
    return result


def _find_sim_components(project_path: str, component_type: str = "") -> list[dict]:
    """Local lookup of simulation components from saved project files."""
    reader = ProjectReader(project_path)
    results: list[dict] = []
    for sname in reader.list_schematics() or []:
        raw = reader.read_schematic(sname)
        if not raw:
            continue
        for comp in parse_components(raw):
            ct = comp.get("type", "")
            if ct not in _COMPONENT_TYPES:
                continue
            if component_type and ct != component_type:
                continue
            # Use parsed paramsinfo directly — don't double-parse
            params = comp.get("paramsinfo", {})
            results.append({
                "component_type": ct,
                "instance_name": comp.get("name", ""),
                "component_id": comp.get("component_id", ""),
                "schematic": sname,
                "parameters": _format_component_parameters(ct, params),
            })
    return results


# ═══════════════════════════════════════════════════════════
# 1. get_simulation_component_schema
# ═══════════════════════════════════════════════════════════

@mcp.tool()
def get_simulation_component_schema(
    component_type: str,
    parameter_name: str = "",
) -> dict[str, Any]:
    """查询仿真控件支持的参数、值类型、单位和创建/更新权限。

    创建或修改控件前优先调用，了解哪些参数可用、格式要求和权限限制。
    返回中包含 schema_version、protocol_version 和 parameter_patterns。

    Args:
        component_type: "SParameter" / "HarmonicBalance" / "XDB"。
        parameter_name: 指定参数名时只返回该参数，为空返回全部。
    """
    catalog = _load_catalog()
    if not catalog:
        return {"success": False,
                "error_code": "COMPONENT_SCHEMA_UNAVAILABLE",
                "message": "参数目录加载失败"}

    comp = _catalog_component(component_type)
    if not comp:
        return {"success": False,
                "error_code": "UNSUPPORTED_COMPONENT_TYPE",
                "message": f"不支持的控件类型: {component_type}",
                "supported_component_types": sorted(_COMPONENT_TYPES)}

    params = comp.get("parameters", {})
    if parameter_name:
        schema, _ = _resolve_parameter_schema(component_type, parameter_name)
        if schema is None:
            return {"success": False,
                    "error_code": "UNSUPPORTED_PARAMETER",
                    "message": f"{component_type} 不支持参数 {parameter_name}",
                    "supported_parameters": _supported_param_names(component_type)}
        params = {parameter_name: schema}

    return {
        "success": True,
        "component_type": component_type,
        "schema_version": catalog.get("schema_version", ""),
        "protocol_version": catalog.get("protocol_version", ""),
        "edi_version": catalog.get("edi_version", ""),
        "parameters": params,
        "parameter_patterns": comp.get("parameter_patterns", []),
        "example": comp.get("example", {}),
    }


# ═══════════════════════════════════════════════════════════
# 2. list_simulation_components
# ═══════════════════════════════════════════════════════════

@mcp.tool()
def list_simulation_components(
    project_path: str,
    component_type: str = "",
) -> dict[str, Any]:
    """查询工程中已有的仿真器件及其当前参数。

    适合以下场景：查看当前控件配置、确认实例名后再更新或删除、
    查找多音参数的实际值。

    Args:
        project_path: .epp 工程文件绝对路径。
        component_type: 按类型过滤（可选）。
    """
    if component_type and component_type not in _COMPONENT_TYPES:
        return {"success": False,
                "message": f"不支持的器件类型: {component_type}"}
    reader = ProjectReader(project_path)
    return {
        "success": True,
        "project_path": str(reader.epp_path.resolve()),
        "components": _find_sim_components(project_path, component_type),
    }


# ═══════════════════════════════════════════════════════════
# 3. create_simulation_component
# ═══════════════════════════════════════════════════════════

@mcp.tool()
def create_simulation_component(
    project_path: str,
    component_type: str,
    parameters: dict | None = None,
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    """新增一个仿真器件。每次调用都会创建新实例，服务端自动分配实例名。

    配置参数前建议先调用 get_simulation_component_schema 了解可用参数。
    未提供的参数使用 EDI 默认值。

    Args:
        project_path: .epp 工程文件绝对路径。
        component_type: "SParameter" / "HarmonicBalance" / "XDB"。
        parameters: 参数字典（可选，为空则全部使用默认值）。
        timeout_seconds: 最长等待秒数。
    """
    resolved = validate_project_path(project_path)

    if component_type not in _COMPONENT_TYPES:
        return {"success": False,
                "error_code": "UNSUPPORTED_COMPONENT_TYPE",
                "message": f"不支持的器件类型: {component_type}",
                "supported_component_types": sorted(_COMPONENT_TYPES)}

    params = {} if parameters is None else parameters
    wire_params, error = _prepare_parameters(
        component_type, params,
        operation="create",
        allow_empty=True,
    )
    if error:
        return error

    return call_grpc(
        ecserver_pb2.CREATE_SIMULATION_COMPONENT,
        {"project_path": resolved,
         "component_type": component_type,
         "parameters": wire_params},
        timeout_seconds,
        max_timeout_seconds=300,
    )


# ═══════════════════════════════════════════════════════════
# 4. update_simulation_component
# ═══════════════════════════════════════════════════════════

@mcp.tool()
def update_simulation_component(
    project_path: str,
    instance_name: str,
    parameters: dict,
    component_type: str = "",
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    """按实例名更新仿真器件参数。只更新传入的参数，其余保持原值。

    建议先调用 list_simulation_components 确认实例名和类型。
    如果提供 component_type，MCP 会进行参数校验和 wire 转换；
    如果不提供，MCP 会尝试从已保存工程自动识别。

    示例：
      {"project_path": "...", "instance_name": "HB1",
       "component_type": "HarmonicBalance",
       "parameters": {"Freq": {"value": "2", "unit": "GHz"}, "Order": {"value": "7"}}}

    Args:
        project_path: .epp 工程文件绝对路径。
        instance_name: 器件实例名（如 "HB1"、"SP2"）。
        parameters: 要更新的参数（非空对象）。
        component_type: 器件类型（可选），用于参数校验。
        timeout_seconds: 最长等待秒数。
    """
    resolved = validate_project_path(project_path)

    if not isinstance(parameters, dict) or not parameters:
        return {"success": False,
                "error_code": "INVALID_PARAMETERS",
                "message": "parameters 必须是非空对象"}

    # Determine component_type: explicit > disk inference > skip validation
    ct = component_type.strip() if component_type else ""

    if ct:
        # Explicit type provided — validate it
        if ct not in _COMPONENT_TYPES:
            return {"success": False,
                    "error_code": "UNSUPPORTED_COMPONENT_TYPE",
                    "message": f"不支持的控件类型: {ct}",
                    "supported_component_types": sorted(_COMPONENT_TYPES)}
    else:
        # Try disk inference (best-effort, non-blocking)
        component, _ = _find_component_by_instance(resolved, instance_name)
        if component and component.get("type", "") in _COMPONENT_TYPES:
            ct = component["type"]

    if ct:
        # We know the type — validate + wire-convert
        wire_params, prepare_error = _prepare_parameters(
            ct, parameters,
            operation="update",
            allow_empty=False,
        )
        if prepare_error:
            return prepare_error
    else:
        # Cannot determine type — send parameters as-is, EDI does validation
        # Convert only what we can (Freq→Freq[1] etc cannot be done without type)
        wire_params = parameters

    return call_grpc(
        ecserver_pb2.UPDATE_SIMULATION_COMPONENT,
        {"project_path": resolved,
         "instance_name": instance_name.strip(),
         "parameters": wire_params},
        timeout_seconds,
        max_timeout_seconds=300,
    )


# ═══════════════════════════════════════════════════════════
# 5. delete_simulation_component
# ═══════════════════════════════════════════════════════════

@mcp.tool()
def delete_simulation_component(
    project_path: str,
    instance_name: str,
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    """按实例名删除原理图器件及其连接线。

    这是通用删除工具，不限于仿真器件。删除直接由 EDI 按实例名执行，
    不做本地磁盘预检查，因此即使 EDI 中有未保存的更改也能正常工作。

    建议调用前先用 list_simulation_components 或 list_project_components
    确认目标实例名。

    Args:
        project_path: .epp 工程文件绝对路径。
        instance_name: 要删除的器件实例名（如 "R1"、"SP2"）。
        timeout_seconds: 最长等待秒数。
    """
    resolved = validate_project_path(project_path)

    if not instance_name.strip():
        return {"success": False,
                "error_code": "EMPTY_INSTANCE_NAME",
                "message": "instance_name 不能为空"}

    return call_grpc(
        ecserver_pb2.DELETE_SIMULATION_COMPONENT,
        {"project_path": resolved,
         "instance_name": instance_name.strip()},
        timeout_seconds,
        max_timeout_seconds=300,
    )


# ═══════════════════════════════════════════════════════════
# 6. set_component_active_state
# ═══════════════════════════════════════════════════════════

@mcp.tool()
def set_component_active_state(
    project_path: str,
    instance_name: str,
    state: str,
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    """确定性设置器件状态为 NORMAL、DISABLED 或 SHORTED。

    这不是状态切换，而是直接设置目标状态，因此重复调用具有幂等性：
    DISABLED → 再设置 DISABLED → 仍然是 DISABLED。

    Args:
        project_path: .epp 工程文件绝对路径。
        instance_name: 器件实例名。
        state: 目标状态，只接受 "NORMAL" / "DISABLED" / "SHORTED"（大小写不敏感）。
        timeout_seconds: 最长等待秒数。
    """
    resolved = validate_project_path(project_path)

    normalized = state.strip().upper()
    if normalized not in _ACTIVE_STATES:
        return {"success": False,
                "error_code": "INVALID_ACTIVE_STATE",
                "message": f"无效状态: {state}，仅支持 NORMAL / DISABLED / SHORTED",
                "allowed_states": sorted(_ACTIVE_STATES)}

    if not instance_name.strip():
        return {"success": False,
                "error_code": "EMPTY_INSTANCE_NAME",
                "message": "instance_name 不能为空"}

    return call_grpc(
        ecserver_pb2.SET_COMPONENT_ACTIVE_STATE,
        {"project_path": resolved,
         "instance_name": instance_name.strip(),
         "state": normalized},
        timeout_seconds,
        max_timeout_seconds=300,
    )


# ═══════════════════════════════════════════════════════════
# 7. generate_schematic_from_netlist
# ═══════════════════════════════════════════════════════════

@mcp.tool()
def generate_schematic_from_netlist(
    project_path: str,
    netlist_path: str,
    clear_before_import: bool = False,
    confirm_clear: bool = False,
    timeout_seconds: int = 300,
) -> dict[str, Any]:
    """将网表文件导入工程生成 main 原理图。

    默认追加到现有原理图。清空模式需要双重确认。

    Args:
        project_path: .epp 工程文件绝对路径。
        netlist_path: 网表文件路径（必须已存在）。
        clear_before_import: 是否在导入前清空 main 原理图（默认 False）。
        confirm_clear: 确认清空操作。clear_before_import=true 时必须同时为 true。
        timeout_seconds: 最长等待秒数，默认 300。
    """
    resolved = validate_project_path(project_path)

    netlist = Path(netlist_path).expanduser().resolve()
    if not netlist.is_file():
        return {"success": False,
                "error_code": "FILE_NOT_FOUND",
                "message": f"网表文件不存在: {netlist}"}

    # Clear-before-import safety gate
    if clear_before_import and not confirm_clear:
        # Count existing components in main schematic only (same as what gRPC clears)
        existing_count = 0
        try:
            reader = ProjectReader(project_path)
            raw = reader.read_schematic("main")
            if raw:
                existing_count = len(parse_components(raw))
        except Exception:
            pass

        return {"success": False,
                "error_code": "CLEAR_CONFIRMATION_REQUIRED",
                "message": ("clear_before_import=true 会清空 main 原理图的全部器件；"
                            "确认后请同时传 confirm_clear=true"),
                "existing_component_count": existing_count,
                "warning": "本操作将清空 main 原理图"}

    return call_grpc(
        ecserver_pb2.GENERATE_SCHEMATIC_FROM_NETLIST,
        {"project_path": resolved,
         "netlist_path": str(netlist),
         "clear_before_import": clear_before_import},
        timeout_seconds,
        max_timeout_seconds=600,
    )