r"""MCP Resources & Prompts — 协议 v2。

Resources（只读上下文，客户端主动获取）:
  edi://service/overview                 服务能力概览
  edi://reference/simulation-components  仿真器件参数目录
  edi://reference/operation-guide        操作规则

Prompts（可复用工作流，用户主动选择）:
  inspect_edi_project         检查 EDI 工程
  run_and_review_simulation   执行并检查仿真
  configure_simulation_component  配置仿真器件
"""

from __future__ import annotations

import os as _os
from typing import Any

from dotenv import load_dotenv

from servers.mcp_instance import mcp
from servers.eda.simulation_components import _load_catalog
from servers.eda.config import EDA_GRPC_SERVER

load_dotenv()

# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------
from servers import __version__ as SERVER_VERSION


# ═══════════════════════════════════════════════════════════
# Resources
# ═══════════════════════════════════════════════════════════

@mcp.resource(
    "edi://service/overview",
    name="Service Overview",
    title="EDI MCP 服务概览",
    description="当前 MCP 协议版本、服务能力、安全规则和 gRPC 目标。",
)
def resource_service_overview() -> dict[str, Any]:
    """返回服务能力概览。不包含密钥、路径或敏感信息。"""
    workspace_enabled = bool(
        _os.getenv("OPENCLAW_WORKSPACE", "").strip()
    )
    grpc_host = EDA_GRPC_SERVER or "127.0.0.1:50055"

    return {
        "server_name": "EDI MCP",
        "server_version": SERVER_VERSION,
        "protocol_version": "2",
        "mode": "local",
        "grpc_target": grpc_host,
        "workspace_copy_enabled": workspace_enabled,
        "simulation_components": ["SParameter", "HarmonicBalance", "XDB"],
        "safety_rules": {
            "do_not_retry_unknown_outcome": True,
            "clear_schematic_requires_confirmation": True,
            "workspace_copy_requires_explicit_user_request": True,
            "show_image_returns_imagecontent_only": True,
        },
    }


@mcp.resource(
    "edi://reference/simulation-components",
    name="Simulation Components Reference",
    title="仿真器件参数参考",
    description="仿真器件支持的公开参数名、gRPC 参数名、值类型、单位和创建/更新权限。",
)
def resource_simulation_components() -> dict[str, Any]:
    """直接复用参数目录，不维护两套定义。"""
    return _load_catalog()


@mcp.resource(
    "edi://reference/operation-guide",
    name="Operation Guide",
    title="EDI MCP 操作规则",
    description="创建、修改、删除仿真器件和网表导入的安全约束。",
)
def resource_operation_guide() -> str:
    """返回 Markdown 格式的操作规则。"""
    return (
        "# EDI MCP 操作规则\n\n"
        "- 查询工程时优先使用 `get_project_summary`。\n"
        "- 创建或修改仿真器件前先查询参数 Schema。\n"
        "- `create_simulation_component` 每次都会创建新实例。\n"
        "- `TIMEOUT` 或 `STREAM_DISCONNECTED` 后禁止自动重试创建或导入。\n"
        "- `delete_simulation_component` 按实例名精确删除，删除前先确认目标。\n"
        "- `set_component_active_state` 是确定性设置，不是状态切换。\n"
        "- `clear_before_import=true` 必须获得用户明确确认，同时传 `confirm_clear=true`。\n"
        "- `show_image` 只返回 ImageContent，不自动复制到工作区。\n"
        "- `copy_image_to_workspace` 只在 OPENCLAW_WORKSPACE 配置有效时注册。\n"
        "- 只有用户明确要求复制到工作区时才能调用 `copy_image_to_workspace`。\n"
        "- 不要检查或读取服务端环境变量。\n"
        "- 不要猜测工程文件路径，先通过 `list_epp_projects` 获取。\n"
    )


# ═══════════════════════════════════════════════════════════
# Prompts
# ═══════════════════════════════════════════════════════════

@mcp.prompt(
    name="inspect_edi_project",
    title="检查 EDI 工程",
    description="查看工程基本信息、器件统计、变量配置和仿真设置。不修改工程，不启动仿真。",
)
def prompt_inspect_edi_project(
    project_path: str,
    detail_level: str = "standard",
) -> list[dict[str, Any]]:
    """检查 EDI 工程的工作流模板。

    Args:
        project_path: .epp 工程文件绝对路径。
        detail_level: summary（概览）/ standard（标准）/ full（完整）。
    """
    detail = detail_level.lower().strip() or "standard"
    if detail not in ("summary", "standard", "full"):
        detail = "standard"

    depth = {
        "summary": "只输出基本信息，不展开器件列表",
        "standard": "包含器件统计和仿真配置",
        "full": "包含完整器件列表和参数",
    }

    return [
        {
            "role": "user",
            "content": (
                f"请检查 EDI 工程：{project_path}\n\n"
                f"检查深度：{detail}（{depth.get(detail, '')}）\n\n"
                "步骤：\n"
                "1. 调用 `get_project_summary` 获取工程概览。\n"
                "2. 调用 `analyze_variables` 查看变量定义和 Sweep 配置。\n"
                "3. standard/full 时调用 `list_project_components` 查看器件分布。\n"
                "4. 调用 `list_simulation_components` 查看仿真器件配置。\n"
                "5. 汇总输出：原理图数量、器件统计、变量与 Sweep、仿真配置、已有的问题。\n\n"
                "注意：只读操作，不修改工程，不启动仿真。"
            ),
        },
    ]


@mcp.prompt(
    name="run_and_review_simulation",
    title="执行并检查仿真",
    description="对工程执行仿真并分析结果。默认异步执行，支持日志分析。",
)
def prompt_run_and_review_simulation(
    project_path: str,
    execution_mode: str = "async",
    analyze_log: bool = True,
) -> list[dict[str, Any]]:
    """仿真执行与分析工作流模板。

    Args:
        project_path: .epp 工程文件绝对路径。
        execution_mode: async（异步，推荐）或 sync（同步）。
        analyze_log: 是否分析 ads_output 日志。
    """
    mode = execution_mode.lower().strip() or "async"
    if mode not in ("async", "sync"):
        mode = "async"

    steps: list[str] = [
        "1. 调用 `get_project_summary` 确认工程中有仿真器件。",
    ]
    if mode == "async":
        steps += [
            "2. 调用 `start_simulation_async` 启动仿真，获取 task_id。",
            "3. 定期调用 `get_simulation_async_status` 查询进度。",
            "4. 完成后调用 `get_simulation_async_result` 获取完整结果和日志。",
        ]
    else:
        steps += [
            "2. 调用 `simulate_project` 等待仿真完成。",
        ]

    if analyze_log:
        steps += [
            "5. 分析 `ads_output` 日志：是否成功、有无 error/warning、result_path 是否生成、log_complete 是否为 true。",
            "6. 输出结论：成功/失败/未知，以及日志关键行。",
        ]
    else:
        steps += [
            "5. 输出结论：成功/失败/未知，result_path 路径。",
        ]

    steps += [
        "",
        "重要约束：",
        "- TIMEOUT 或 STREAM_DISCONNECTED 时：明确告知用户任务结果未知，禁止自动重试。",
        "- 不要为了查询日志而启动新的仿真任务。",
        "- 如用户需要图表，再调用 `turbocharts_convert` 或 `compare_simulation_results`。",
    ]

    return [
        {
            "role": "user",
            "content": (
                f"请对工程 {project_path} 执行仿真并分析结果。\n"
                f"执行方式：{mode}\n"
                f"分析日志：{'是' if analyze_log else '否'}\n\n"
                + "\n".join(steps)
            ),
        },
    ]


@mcp.prompt(
    name="configure_simulation_component",
    title="配置仿真器件",
    description="按用户需求配置 SP/HB/XDB 仿真器件参数。创建或修改前先查询 Schema 和现有配置。",
)
def prompt_configure_simulation_component(
    project_path: str,
    action: str,
    component_type: str,
    instance_name: str = "",
    requirements: str = "",
) -> list[dict[str, Any]]:
    """配置仿真器件的工作流模板。

    Args:
        project_path: .epp 工程文件绝对路径。
        action: create（创建）或 update（更新）。
        component_type: SParameter / HarmonicBalance / XDB。
        instance_name: update 时需要提供实例名。
        requirements: 用户对参数的自然语言描述。
    """
    act = action.lower().strip()
    if act not in ("create", "update"):
        act = "create"

    ct = component_type.strip()
    if ct not in ("SParameter", "HarmonicBalance", "XDB"):
        ct = "SParameter"

    steps: list[str] = [
        "1. 调用 `get_simulation_component_schema` 查询器件支持的参数、类型和单位。",
        "2. 读取 `edi://reference/simulation-components` Resource 了解权限约束。",
    ]

    if act == "update":
        inst = instance_name.strip() or "（请提供实例名）"
        steps += [
            f"3. 调用 `list_simulation_components` 查找 {inst} 的当前参数。",
            f"4. 把用户需求「{requirements or '修改参数'}」映射为合法的参数名、值和单位。",
            f"5. 在执行前向用户展示：目标器件 {inst}（{ct}）、参数名称、新的值、单位。",
            f"6. 用户确认后调用 `update_simulation_component`，传入 instance_name=\"{inst}\" 和 component_type=\"{ct}\"。",
        ]
    else:
        steps += [
            f"3. 把用户需求「{requirements or '使用默认参数'}」映射为合法的参数名、值和单位。",
            f"4. 在执行前向用户展示：器件类型 {ct}、参数名称、值、单位。",
            f"5. 用户确认后调用 `create_simulation_component`，传入 component_type=\"{ct}\"。",
        ]

    steps += [
        "",
        "重要约束：",
        "- 参数名必须与 `get_simulation_component_schema` 返回的一致。",
        "- 不要编造参数名、单位或 wire 字段。",
        "- 无单位参数不要传 unit 字段。",
        "- 每次 create 都会创建新实例，EDM 自动分配实例名。",
        "- TIMEOUT 或 STREAM_DISCONNECTED 后禁止自动重试。",
    ]

    return [
        {
            "role": "user",
            "content": "\n".join(steps),
        },
    ]
