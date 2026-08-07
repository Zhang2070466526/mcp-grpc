"""MCP Resources — 只读上下文，客户端主动获取。

  edi://service/overview                 服务能力概览
  edi://reference/simulation-components  仿真器件参数目录
  edi://reference/operation-guide        操作规则
"""

from __future__ import annotations

from typing import Any

from servers import mcp, __version__ as SERVER_VERSION
from servers.eda.simulation_components import _load_catalog
from servers.eda.config import EDA_GRPC_SERVER
from servers.multimodal_vision import OPENCLAW_WORKSPACE_PATH


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
        "protocol_version": "2",     # gRPC 协议版本
        "tool_api_version": "3",    # 仿真器件工具 API 版本
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
