r"""EDA 模型替换工具。

replace_models_from_csv     根据 CSV 文件内容，批量替换工程中的元件模型

自然语言使用示例：
  帮我用 C:\models\replace_list.csv 替换 EDA 工程 C:\...\EDI_TEST.epp 中的模型
  帮我按照这个 CSV 文件替换模型

CSV 格式参考：模型替换_LJ.csv（项目根目录）
  列：original_model_type, original_model_name, original_model_id,
       alternative_model_type, alternative_model_name, alternative_model_id

参数说明：
  project_path     EDA 服务所在机器上的 .epp 工程文件绝对路径
  csv_path         模型替换 CSV 文件绝对路径
  timeout_seconds  最长等待秒数，无上限，默认 60 秒
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from proto import ecserver_pb2
from servers.eda.grpc_client import call_grpc
from servers.eda.config import validate_project_path


def replace_models_from_csv(
    project_path: str,
    csv_path: str,
    timeout_seconds: int = 60,
) -> dict[str, Any]:
    """按 CSV 文件对 EDA 工程执行模型替换。

    Args:
        project_path: EDA 服务所在机器上的 .epp 工程文件绝对路径。
        csv_path: 模型替换 CSV 文件绝对路径。
        timeout_seconds: 最长等待时间，默认 60 秒。
    """
    resolved_path = validate_project_path(project_path)
    csv = Path(csv_path).expanduser()
    if not csv.is_file():
        raise FileNotFoundError(f"CSV 文件不存在: {csv}")
    return call_grpc(
        ecserver_pb2.MODEL_REPLACE,
        {"project_path": resolved_path, "csv_path": str(csv.resolve())},
        timeout_seconds,
        max_timeout_seconds=300,
    )
