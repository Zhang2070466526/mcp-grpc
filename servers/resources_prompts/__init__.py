"""MCP Resources & Prompts — 3 个 Resource + 4 个 Prompt。"""

from servers.resources_prompts.resources import (  # noqa: F401 — 触发 @mcp.resource() 注册
    resource_service_overview,
    resource_simulation_components,
    resource_operation_guide,
)
from servers.resources_prompts.prompts import (  # noqa: F401 — 触发 @mcp.prompt() 注册
    prompt_inspect_edi_project,
    prompt_run_and_review_simulation,
    prompt_configure_simulation_component,
    prompt_create_simulation_report,
)
