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
from servers.mcp_instance import mcp


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
            if not isinstance(info, dict):
                continue
            if not include_hidden and info.get("Visible", "true") == "false":
                continue

            unit_field = info.get("Unit", "")
            available_units = unit_field.split(",") if unit_field else []

            parameters.append({
                "key": key,
                "value": info.get("Value", ""),
                "unit": info.get("CurrentUnit", info.get("DefaultUnit", "")),
                "default_unit": info.get("DefaultUnit", ""),
                "available_units": available_units,
                "tunable": info.get("Tunable", "false") == "true",
                "visible": info.get("Visible", "true") != "false",
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

    simulation_info: dict[str, Any] = {}
    # Read simulation config from SParameter component in schematic
    for sname in schematics:
        raw = reader.read_schematic(sname)
        if not raw:
            continue
        for comp in parse_components(raw):
            if comp["type"] == "SParameter":
                pi = comp.get("paramsinfo", {})
                sim_type = pi.get("CalcS", {}).get("Value", "")
                start = pi.get("Start", {})
                stop = pi.get("Stop", {})
                step = pi.get("Step", {})
                simulation_info = {
                    "type": "S_Param" if sim_type == "yes" else sim_type,
                    "start": f"{start.get('Value','')} {start.get('CurrentUnit','')}".strip(),
                    "stop": f"{stop.get('Value','')} {stop.get('CurrentUnit','')}".strip(),
                    "step": f"{step.get('Value','')} {step.get('CurrentUnit','')}".strip(),
                }
                break

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


# TODO: create_blank_epp 暂不可用，取消注释 @mcp.tool() 即可恢复注册
def create_blank_epp(
    folder_path: str,
    project_name: str,
) -> dict[str, Any]:
    """在指定文件夹中创建一个空白的 .epp 工程。

    生成结构：project_name/ 文件夹，内含与文件夹同名的 .epp 文件 +
    history/ + project/（空）+ schematics/main/（空）。
    不依赖 gRPC，纯本地文件操作。

    Args:
        folder_path: 目标父文件夹的绝对路径。
        project_name: 工程名称（不含 .epp 后缀）。
    """
    parent = Path(folder_path).expanduser()
    if not parent.is_dir():
        raise FileNotFoundError(f"文件夹不存在: {parent}")

    # 工程根目录
    root = parent / project_name
    if root.exists():
        raise FileExistsError(f"工程目录已存在: {root}")
    root.mkdir()

    # .epp 标记文件（名称与文件夹一致）
    epp_path = root / f"{project_name}.epp"
    epp_path.write_text("EDI-PROJECT", encoding="utf-8")

    # history/
    (root / "history").mkdir()

    # project/（空文件夹）
    (root / "project").mkdir()

    # schematics/ + schematics/main/（main 为空文件夹）
    (root / "schematics" / "main").mkdir(parents=True)

    return {
        "success": True,
        "project_path": str(epp_path.resolve()),
        "project_name": project_name,
    }