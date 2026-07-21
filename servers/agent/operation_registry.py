"""操作注册表 — 将操作名称映射到现有工具函数。

Agent 只执行注册表中列出的操作，不执行任意代码。
"""

from __future__ import annotations

from typing import Any, Callable

# 操作名 → 函数映射
# 键为中央服务发送的操作名，值为本地工具函数
_REGISTRY: dict[str, Callable[..., Any]] = {}


def register(name: str, func: Callable[..., Any]) -> None:
    _REGISTRY[name] = func


def get(name: str) -> Callable[..., Any] | None:
    return _REGISTRY.get(name)


def list_operations() -> list[str]:
    return list(_REGISTRY.keys())


# ---------------------------------------------------------------------------
# 注册所有允许的操作
# ---------------------------------------------------------------------------

# -- 工程管理（只读，允许并发） --
from servers.eda.project_manage import (  # noqa: E402
    list_epp_projects,
    list_project_components,
    get_component_parameters,
    get_project_summary,
)
register("list_epp_projects", list_epp_projects)
register("list_project_components", list_project_components)
register("get_component_parameters", get_component_parameters)
register("get_project_summary", get_project_summary)

# -- EDA 操作（全局串行） --
from servers.eda.project_manage import (  # noqa: E402
    open_eda_project,
    close_eda_project,
)
from servers.eda.simulation import (  # noqa: E402
    simulate_project,
    simulate_netlist_with_ads,
)
from servers.eda.design_export import (  # noqa: E402
    export_project_netlist,
    capture_schematic,
)
from servers.eda.model_replace import (  # noqa: E402
    replace_models_from_csv,
)
from servers.eda.edi_launcher import (  # noqa: E402
    launch_edi,
)
register("open_eda_project", open_eda_project)
register("close_eda_project", close_eda_project)
register("simulate_project", simulate_project)
register("simulate_netlist_with_ads", simulate_netlist_with_ads)
register("export_project_netlist", export_project_netlist)
register("capture_schematic", capture_schematic)
register("replace_models_from_csv", replace_models_from_csv)
register("launch_edi", launch_edi)

# -- 图表（串行） --
from servers.eda.project_inspection import (  # noqa: E402
    compare_simulation_results,
)
from servers.turbocharts.server import (  # noqa: E402
    turbocharts_convert,
)
register("compare_simulation_results", compare_simulation_results)
register("turbocharts_convert", turbocharts_convert)

# ---------------------------------------------------------------------------
# 操作分类（决定进入哪个执行池）
# ---------------------------------------------------------------------------

READ_ONLY_OPS = {
    "list_epp_projects",
    "list_project_components",
    "get_component_parameters",
    "get_project_summary",
}

EDA_OPS = {
    "open_eda_project",
    "close_eda_project",
    "simulate_project",
    "simulate_netlist_with_ads",
    "export_project_netlist",
    "capture_schematic",
    "replace_models_from_csv",
    "launch_edi",
}

TURBOCHARTS_OPS = {
    "compare_simulation_results",
    "turbocharts_convert",
}


def pool_for(op_name: str) -> str:
    if op_name in EDA_OPS:
        return "eda"
    if op_name in TURBOCHARTS_OPS:
        return "turbocharts"
    return "file_read"
