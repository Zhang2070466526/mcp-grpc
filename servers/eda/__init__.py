r"""EDI gRPC MCP 工具包 -- 通过 ExternalCall gRPC 操作 EDI 工程。

project_manage.py  工程管理（7 个工具）
    list_epp_projects             扫描文件夹中的所有 .epp 工程文件
    open_edi_project              打开 .epp 工程
    close_edi_project             关闭已打开的工程
    list_project_components       列出工程中的元件
    get_component_parameters      查询单个元件的完整参数
    get_project_summary           工程概览（元数据/原理图/仿真）
    analyze_variables             分析变量定义和引用关系

simulation_components.py  仿真器件管理（7 个工具）
    get_simulation_component_schema  查询器件参数 schema
    list_simulation_components       列出工程中的仿真器件
    create_simulation_component      新增仿真器件
    update_simulation_component      按实例名更新参数
    delete_simulation_component      按实例名删除器件
    set_component_active_state       设置器件状态（NORMAL/DISABLED/SHORTED）
    generate_schematic_from_netlist  从网表生成原理图

simulation.py  仿真（7 个工具）
    simulate_project               对工程执行仿真
    start_simulation_async         启动异步仿真
    get_simulation_async_status    查询异步仿真状态
    get_simulation_async_result    获取异步仿真结果
    list_eda_tasks                 列出异步仿真任务
    simulate_netlist               仿真网表文件
    simulate_netlist_with_ads      ADS 仿真控制器

design_export.py  分析（2 个工具）
    export_project_netlist  查看/导出工程网表文件
    capture_schematic       截取原理图并保存为图片

model_replace.py  模型替换（1 个工具）
    replace_models_from_csv  根据 CSV 文件批量替换元件模型

edi_launcher.py  启动 EDI（1 个工具）
    launch_edi  启动 EDI 客户端，自动等待 gRPC 就绪
"""

# -- 工程管理 --
from servers.eda.project_manage import (  # noqa: F401
    list_epp_projects,
    open_edi_project,
    close_edi_project,
    list_project_components,
    get_component_parameters,
    get_project_summary,
    analyze_variables,
)

# -- 仿真 --
from servers.eda.simulation_components import (  # noqa: F401
    get_simulation_component_schema,
    list_simulation_components,
    create_simulation_component,
    update_simulation_component,
    delete_simulation_component,
    set_component_active_state,
    generate_schematic_from_netlist,
)

from servers.eda.simulation import (  # noqa: F401
    simulate_project,
    simulate_netlist,
    simulate_netlist_with_ads,
    start_simulation_async,
    get_simulation_async_status,
    get_simulation_async_result,
    list_eda_tasks,
)

# -- 分析 --
from servers.eda.design_export import (  # noqa: F401
    export_project_netlist,
    capture_schematic,
)

# -- 模型 --
from servers.eda.model_replace import (  # noqa: F401
    replace_models_from_csv,
)

# -- 启动 --
from servers.eda.edi_launcher import (  # noqa: F401
    launch_edi,
)
