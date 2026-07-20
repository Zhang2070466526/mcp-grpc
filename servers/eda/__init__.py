r"""EDA gRPC MCP 工具包 — 通过 ExternalCall gRPC 操作 EDA 工程。

════════════════════════════════════════════════════════════════
  工具清单（共 9 个）：
    list_epp_projects             扫描 .epp 工程
    open_eda_project              打开工程
    close_project                 关闭工程
    simulate_project              执行仿真
    call_simulation_controller    调用 ADS 仿真控制器
    view_project_netlist          查看/导出网表
    capture_schematic             截取原理图
    model_replace                 按 CSV 替换模型
    launch_edi                    启动 EDI 客户端

  内部模块：
    config.py         公用函数（validate_project_path）+ 配置常量
    grpc_client.py    gRPC 通信层（call_grpc）
    project_service.py      工程管理
    simulation_service.py   仿真
    analysis_service.py     网表/截图分析
    model_service.py        模型替换
    edi_launcher.py         启动 EDI
════════════════════════════════════════════════════════════════

使用方式：
    from servers.eda import open_eda_project, launch_edi
    from servers.eda.config import EDA_GRPC_SERVER, validate_project_path
"""

# -- 工程管理 --
from servers.eda.project_service import (  # noqa: F401
    list_epp_projects,
    open_eda_project,
    close_project,
)

# -- 仿真 --
from servers.eda.simulation_service import (  # noqa: F401
    simulate_project,
    call_simulation_controller,
)

# -- 分析 --
from servers.eda.analysis_service import (  # noqa: F401
    view_project_netlist,
    capture_schematic,
)

# -- 模型 --
from servers.eda.model_service import (  # noqa: F401
    model_replace,
)

# -- 启动 --
from servers.eda.edi_launcher import (  # noqa: F401
    launch_edi,
)
