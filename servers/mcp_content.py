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
from servers.multimodal_vision import OPENCLAW_WORKSPACE_PATH

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
    mime_type="application/json",
)
def resource_service_overview() -> dict[str, Any]:
    """返回服务能力概览。不包含密钥、路径或敏感信息。"""
    workspace_enabled = OPENCLAW_WORKSPACE_PATH is not None
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
            "show_image_uses_native_imagecontent": True,
        },
    }


@mcp.resource(
    "edi://reference/simulation-components",
    name="Simulation Components Reference",
    title="仿真器件参数参考",
    description="仿真器件支持的公开参数名、gRPC 参数名、值类型、单位和创建/更新权限。",
    mime_type="application/json",
)
def resource_simulation_components() -> dict[str, Any]:
    """直接复用参数目录，不维护两套定义。"""
    return _load_catalog()


@mcp.resource(
    "edi://reference/operation-guide",
    name="Operation Guide",
    title="EDI MCP 操作规则",
    description="创建、修改、删除仿真器件和网表导入的安全约束。",
    mime_type="text/markdown",
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
        "- `show_image` 使用原生 MCP ImageContent 返回图片，不复制文件，不输出 MEDIA 文本。\n"
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
            "3. 启动后最多立即查询一次 `get_simulation_async_status`。如果仍在运行，返回 task_id 告知用户稍后查询。不要紧密轮询（间隔不少于 10 秒），单次对话最多自动查询 3 次。",
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
        return [{"role": "user", "content": (
            f"错误：action 必须是 'create' 或 'update'，收到 '{action}'。"
        )}]

    ct = component_type.strip()
    if ct not in ("SParameter", "HarmonicBalance", "XDB"):
        return [{"role": "user", "content": (
            f"错误：component_type 必须是 SParameter / HarmonicBalance / XDB，收到 '{component_type}'。"
        )}]

    if act == "update" and not instance_name.strip():
        return [{"role": "user", "content": (
            "错误：action=update 时必须提供 instance_name。"
        )}]

    steps: list[str] = [
        "1. 调用 `get_simulation_component_schema` 查询器件支持的参数、类型和单位。",
        "   （如果客户端支持 Resource，也可读取 edi://reference/simulation-components）",
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
        "- 每次 create 都会创建新实例，EDI 自动分配实例名。",
        "- TIMEOUT 或 STREAM_DISCONNECTED 后禁止自动重试。",
    ]

    return [
        {
            "role": "user",
            "content": "\n".join(steps),
        },
    ]


@mcp.prompt(
    name="create_simulation_report",
    title="生成仿真报告",
    description="协调多个工具完成仿真报告：查询工程→确认结果→生成曲线→整理数据→渲染 PDF/DOCX。",
)
def prompt_create_simulation_report(
    project_path: str,
    output_path: str,
    overwrite: bool = False,
) -> list[dict[str, Any]]:
    """生成仿真报告的完整工作流模板。

    Args:
        project_path: .epp 工程文件绝对路径。
        output_path: 输出文件绝对路径（.pdf 或 .docx）。
        overwrite: 输出文件已存在时是否覆盖。
    """
    from pathlib import Path as _Path
    ext = _Path(output_path).suffix.lower() if output_path else ".pdf"
    file_type = ext.lstrip(".")

    steps = [
        f"1. 确认输出路径：`{output_path or '（请提供）'}`（{file_type.upper()} 格式）。",
        "2. 调用 `get_project_summary` 获取工程基本信息作为报告封面和简介素材。",
        "3. 查询已有仿真结果（`get_simulation_async_result` 或 `list_eda_tasks`），不自动重新仿真。",
        "   没有结果时询问用户是否执行仿真。",
        "4. 调用 `list_result_curves` 获取 RAW 中实际可用的曲线名。",
        "5. 根据用户需求选择关键曲线，调用 `turbocharts_convert` 生成曲线图片。",
        "6. 如需拓扑图，调用 `capture_schematic` 截取原理图。",
        "7. 整理电参数表（spec_table）：只填入有真实测量值的指标，无要求值时结果列填'未判定'。",
        "8. 整理器件选型表（components）：type/model/manufacturer/specs 四项均为字符串，不得猜测。",
        "9. 收集 description（产品简介）和 conclusion（结论文字）。",
        f"10. 调用 `generate_simulation_report` 渲染报告：output_path=\"{output_path or '（请提供）'}\"，overwrite={'true' if overwrite else 'false'}",
        "",
        "重要约束：",
        "- 不要自动启动新的仿真，除非用户明确要求。",
        "- log_complete=false 时不能断言日志完整。",
        "- TIMEOUT/STREAM_DISCONNECTED 时禁止自动重试，也不写成功结论。",
        "- 器件厂家和规格不得根据型号名称猜测。",
        "- 只有同时具备测量值和判定要求时才能写'合格/不合格'。",
    ]

    return [{"role": "user", "content": "\n".join(steps)}]
