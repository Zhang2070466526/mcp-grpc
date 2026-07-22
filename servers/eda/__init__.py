r"""EDA gRPC MCP 工具包 -- 通过 ExternalCall gRPC 操作 EDA 工程。

project_manage.py  工程管理（6 个工具）
    list_epp_projects             扫描文件夹中的所有 .epp 工程文件
    open_eda_project              打开 .epp 工程
    close_eda_project             关闭已打开的工程
    list_project_components       列出工程中的元件
    get_component_parameters      查询单个元件的完整参数
    get_project_summary           工程概览（元数据/原理图/仿真）
    help: 帮我看看有哪些 .epp 工程 / 打开工程 / 查看元件 / 获取概览

simulation.py  仿真（2 个工具）
    simulate_project            对工程执行仿真
    simulate_netlist_with_ads   基于网表文件调用 ADS 仿真控制器
    help: 帮我对工程执行仿真 / 帮我对 netlist.log 执行 ADS 仿真

design_export.py  分析（2 个工具）
    export_project_netlist  查看/导出工程网表文件
    capture_schematic       截取原理图并保存为图片
    help: 帮我查看网表 / 帮我截取原理图

model_replace.py  模型替换（1 个工具）
    replace_models_from_csv  根据 CSV 文件批量替换元件模型
    help: 帮我用 replace_list.csv 替换工程中的模型

edi_launcher.py  启动 EDI（1 个工具）
    launch_edi  启动 EDI 客户端，自动等待 gRPC 就绪
    help: 帮我启动 EDI
"""

# -- 工程管理 --
from servers.eda.project_manage import (  # noqa: F401
    list_epp_projects,
    open_eda_project,
    close_eda_project,
    list_project_components,
    get_component_parameters,
    get_project_summary,
)

# -- 仿真 --
from servers.eda.simulation import (  # noqa: F401
    simulate_project,
    simulate_netlist_with_ads,
    start_simulation_async,
    get_simulation_async_status,
    get_simulation_async_result,
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
