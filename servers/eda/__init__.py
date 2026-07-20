r"""EDA gRPC MCP 工具包 — 通过 ExternalCall gRPC 操作 EDA 工程。


project_manage.py  工程管理
    list_epp_projects   扫描文件夹中的所有 .epp 工程文件
    open_eda_project    打开 .epp 工程，等待 EDA 返回成功或失败
    close_eda_project   关闭已打开的工程
    ├─ 帮我看看 C:\Users\JGL\EDI-Workspace 下面有哪些 .epp 工程
    ├─ 帮我打开 EDA 工程 C:\...\EDI_TEST.epp
    └─ 帮我保存并关闭这个工程

simulation.py    仿真
    simulate_project            对工程执行仿真，等待结果返回
    simulate_netlist_with_ads   基于网表文件调用 ADS 仿真控制器
    ├─ 帮我对 EDA 工程 C:\...\EDI_TEST.epp 执行仿真
    └─ 帮我对 C:\...\netlist.log 执行 ADS 仿真

design_export.py  分析
    export_project_netlist  查看/导出工程网表文件
    capture_schematic       截取原理图并保存为图片
    ├─ 帮我查看这个工程的网表
    └─ 帮我截取原理图，保存到 C:\screenshots\circuit.png

model_replace.py    模型替换
    replace_models_from_csv  根据 CSV 文件批量替换元件模型
    └─ 帮我用 C:\models\replace_list.csv 替换工程中的模型

edi_launcher.py     启动 EDI
    launch_edi  启动 EDI 客户端，自动等待 gRPC 就绪
    └─ 帮我启动 EDI

"""

# -- 工程管理 --
from servers.eda.project_manage import (  # noqa: F401
    list_epp_projects,
    open_eda_project,
    close_eda_project,
)

# -- 仿真 --
from servers.eda.simulation import (  # noqa: F401
    simulate_project,
    simulate_netlist_with_ads,
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
