r"""EDA 工程管理工具。

list_epp_projects             扫描文件夹中的所有 .epp 工程文件
open_edi_project              打开 .epp 工程，等待返回成功或失败
close_edi_project             关闭已打开的工程，可选择是否保存
list_project_components       列出工程中的元件（不含完整参数）
get_component_parameters      查询单个元件的完整参数列表
get_project_summary           工程概览（元数据、原理图、仿真配置）

自然语言使用示例：
  帮我看看 C:/Users/JGL/EDI-Workspace 下面有哪些 .epp 工程
  帮我打开 EDA 工程 C:/.../EDI_TEST.epp
  帮我关闭这个工程
  帮我看看这个工程有哪些元件
  帮我查看 TermG1 元件的参数
  帮我获取这个工程的概览信息

参数说明：
  project_path     EDA 服务所在机器上的 .epp 工程文件绝对路径
  folder_path      要扫描的文件夹绝对路径（list_epp_projects）
  component_id     元件 UUID（get_component_parameters）
  schematic_name   原理图名称，默认 main
  timeout_seconds  最长等待秒数，默认 60 秒
  need_save        关闭前是否保存工程（close_edi_project），默认 False
"""

from __future__ import annotations

from itertools import islice
from pathlib import Path
from typing import Any

from proto import ecserver_pb2
from servers.eda.grpc_client import call_grpc
from servers.eda.config import ProjectReader, parse_components, validate_project_path
from servers import mcp


@mcp.tool()
def list_epp_projects(folder_path: str) -> dict[str, Any]:
    """扫描指定文件夹，列出其中所有 .epp 工程文件（最多 1000 个）。"""
    if not folder_path or not folder_path.strip():
        raise ValueError("folder_path 不能为空，请提供要扫描的目录")
    root = Path(folder_path).expanduser()
    if not root.is_dir():
        raise FileNotFoundError(f"文件夹不存在: {folder_path}")

    projects = []
    for epp in sorted(islice(root.rglob("*.epp"), 1000)):
        projects.append({
            "name": epp.stem,
            "path": str(epp.resolve()),
            "size": epp.stat().st_size,
        })

    return {
        "success": True,
        "folder": str(root.resolve()),
        "count": len(projects),
        "projects": projects,
    }


@mcp.tool()
def open_edi_project(
        project_path: str,
        timeout_seconds: int = 60,
) -> dict[str, Any]:
    """
    打开一个.epp 工程，例如C:\\Users\\JGL\\EDI-Workspace\\projects\\1\\1.epp

    Args:
        project_path: EDA 服务所在机器上的 .epp 工程文件绝对路径。
        timeout_seconds: 最长等待时间，默认 60 秒。
    """
    resolved_path = validate_project_path(project_path)
    return call_grpc(
        ecserver_pb2.OPEN_PROJECT,
        {"project_path": resolved_path},
        timeout_seconds,
        max_timeout_seconds=300,
    )


@mcp.tool()
def close_edi_project(
        project_path: str,
        need_save: bool = False,
        timeout_seconds: int = 60,
) -> dict[str, Any]:
    """关闭一个.epp 工程。

    Args:
        project_path: EDA 服务所在机器上的 .epp 工程文件绝对路径。
        need_save: 关闭前是否保存工程，默认 False。
        timeout_seconds: 最长等待时间，默认 60 秒。
    """
    resolved_path = validate_project_path(project_path)
    return call_grpc(
        ecserver_pb2.CLOSE_PROJECT,
        {"project_path": resolved_path, "need_save": need_save},
        timeout_seconds,
        max_timeout_seconds=300,
    )


@mcp.tool()
def list_project_components(
    project_path: str,
    schematic_name: str = "main",
    component_type: str = "",
    name_contains: str = "",
    offset: int = 0,
    limit: int = 100,
) -> dict[str, Any]:
    """列出工程原理图中的元件（不含完整参数，避免响应过大）。

    Args:
        project_path: .epp 工程文件绝对路径。
        schematic_name: 原理图名称，默认 "main"。
        component_type: 按类型过滤，如 "TermG"、"VIA2"。
        name_contains: 按名称模糊匹配。
        offset: 分页偏移。
        limit: 每页数量上限，默认 100，最大 500。
    """
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    reader = ProjectReader(project_path)
    raw = reader.read_schematic(schematic_name)
    if not raw:
        return {"success": False, "message": f"原理图 {schematic_name} 不存在"}

    all_comps = parse_components(raw)

    filtered = []
    for c in all_comps:
        if component_type and c["type"] != component_type:
            continue
        if name_contains and name_contains.lower() not in c["name"].lower():
            continue
        filtered.append({
            "component_id": c["component_id"],
            "name": c["name"],
            "type": c["type"],
            "model_id": c["model_id"],
            "pin_count": c["pin_count"],
            "parameter_count": c["parameter_count"],
        })

    total = len(filtered)
    page = filtered[offset:offset + limit]

    return {
        "success": True,
        "project_path": str(reader.epp_path.resolve()),
        "schematic": schematic_name,
        "total": total,
        "offset": offset,
        "limit": limit,
        "components": page,
    }


@mcp.tool()
def get_component_parameters(
    project_path: str,
    component_id: str,
    schematic_name: str = "main",
    include_hidden: bool = False,
) -> dict[str, Any]:
    """查询单个元件的完整参数列表。

    Args:
        project_path: .epp 工程文件绝对路径。
        component_id: 元件 UUID（从 list_project_components 获取）。
        schematic_name: 原理图名称。
        include_hidden: 是否包含 Visible=false 的隐藏参数。
    """
    reader = ProjectReader(project_path)
    raw = reader.read_schematic(schematic_name)
    if not raw:
        return {"success": False, "message": f"原理图 {schematic_name} 不存在"}

    for comp in parse_components(raw):
        if comp["component_id"] != component_id:
            continue

        params_info = comp.get("paramsinfo", {})
        parameters = []
        for key, info in params_info.items():
            if key == "BasicParameters":
                continue
            if not include_hidden and str(info.get("visible", "true")).lower() == "false":
                continue
            parameters.append({
                "key": key,
                "value": info.get("value", ""),
                "unit": info.get("unit", ""),
                "default_unit": info.get("default_unit", ""),
                "tunable": info.get("tunable", False),
                "visible": info.get("visible", True),
                "initial": info.get("initial", ""),
                "max": info.get("max", ""),
                "min": info.get("min", ""),
                "status": info.get("status", ""),
            })

        return {
            "success": True,
            "component": {
                "component_id": comp["component_id"],
                "name": comp["name"],
                "type": comp["type"],
            },
            "parameters": parameters,
        }

    return {"success": False, "message": f"未找到元件 {component_id}"}


@mcp.tool()
def get_project_summary(
    project_path: str,
    include_component_types: bool = True,
    include_latest_result: bool = True,
) -> dict[str, Any]:
    """获取 .epp 工程的完整概览。

    Args:
        project_path: .epp 工程文件绝对路径。
        include_component_types: 是否统计元件类型分布。
        include_latest_result: 是否包含最近仿真结果信息。
    """
    reader = ProjectReader(project_path)
    metadata = reader.read_metadata()

    schematics = reader.list_schematics()
    schematics_info = {"count": len(schematics), "names": schematics}

    components_info: dict[str, Any] = {"total": 0, "by_type": {}}
    for sname in schematics:
        raw = reader.read_schematic(sname)
        if not raw:
            continue
        comps = parse_components(raw)
        components_info["total"] += len(comps)
        if include_component_types:
            for c in comps:
                ct = c["type"]
                components_info["by_type"][ct] = (
                    components_info["by_type"].get(ct, 0) + 1
                )

    simulation_info: list[dict] = []
    _SIM_TYPES = {"SParameter", "HarmonicBalance", "XDB"}
    for sname in schematics:
        raw = reader.read_schematic(sname)
        if not raw:
            continue
        for comp in parse_components(raw):
            ct = comp.get("type", "")
            if ct in _SIM_TYPES:
                pi = comp.get("paramsinfo", {})
                entry: dict[str, Any] = {"component_type": ct, "instance_name": comp.get("name", "")}
                for key, info in pi.items():
                    if key == "BasicParameters" or not isinstance(info, dict):
                        continue
                    entry[key] = f"{info.get('Value', info.get('Initial',''))} {info.get('CurrentUnit', info.get('DefaultUnit',''))}".strip()
                simulation_info.append(entry)

    latest_result: dict[str, Any] = {}
    if include_latest_result:
        result_paths = list(reader.workspace.rglob("*.raw"))
        if result_paths:
            rp = sorted(
                result_paths, key=lambda x: x.stat().st_mtime, reverse=True
            )[0]
            latest_result = {
                "path": str(rp.resolve()),
                "exists": True,
                "size": rp.stat().st_size,
            }

    warnings: list[str] = []
    if not schematics:
        warnings.append("未找到原理图")

    return {
        "success": True,
        "project": metadata,
        "schematics": schematics_info,
        "components": components_info,
        "simulation": simulation_info,
        "latest_result": latest_result,
        "warnings": warnings,
    }


@mcp.tool()
def analyze_variables(project_path: str) -> dict[str, Any]:
    """分析工程中的变量定义和引用关系。

    识别 Var 元件定义的变量、其他元件中对这些变量的引用、
    以及 Sweep 的扫描配置。

    Args:
        project_path: .epp 工程文件绝对路径。
    """
    reader = ProjectReader(project_path)
    variables: list[dict] = []
    references: list[dict] = []
    sweeps: list[dict] = []

    for sname in reader.list_schematics() or []:
        raw = reader.read_schematic(sname)
        if not raw:
            continue
        for comp in parse_components(raw):
            ct = comp.get("type", "")
            params = comp.get("paramsinfo", {})

            # Var 元件：变量定义
            if ct == "Var":
                for pkey, pinfo in params.items():
                    if pinfo.get("initial"):
                        variables.append({
                            "name": comp.get("name", ""),
                            "parameter": pkey,
                            "initial": pinfo["initial"],
                            "min": pinfo.get("min", ""),
                            "max": pinfo.get("max", ""),
                            "tunable": pinfo.get("tunable", False),
                            "status": pinfo.get("status", ""),
                        })

            # Sweep 元件：扫描配置
            if ct == "Sweep":
                sweep_var = params.get("SweepVar", {}).get("value", "")
                targets = [
                    params.get(f"SimInstanceName[{i}]", {}).get("value", "")
                    for i in range(1, 10)
                    if params.get(f"SimInstanceName[{i}]", {}).get("value")
                ]
                sweeps.append({
                    "sweep": comp.get("name", ""),
                    "variable": sweep_var,
                    "start": params.get("Start", {}).get("value", ""),
                    "stop": params.get("Stop", {}).get("value", ""),
                    "step": params.get("Step", {}).get("value", ""),
                    "targets": targets,
                })

        # 查找参数值引用了变量的元件
        # 兼容两种引用方式：Var 实例名 和 Var 参数名
        var_names = {
            value
            for v in variables
            for value in (v["name"], v["parameter"])
            if value
        }
        for comp in parse_components(raw):
            params = comp.get("paramsinfo", {})
            for pkey, pinfo in params.items():
                val = pinfo.get("value", "")
                if val and val in var_names:
                    references.append({
                        "variable": val,
                        "component": comp.get("name", ""),
                        "component_type": comp.get("type", ""),
                        "parameter": pkey,
                    })

    return {
        "success": True,
        "project_path": str(reader.epp_path.resolve()),
        "variables": variables,
        "references": references,
        "sweeps": sweeps,
    }
