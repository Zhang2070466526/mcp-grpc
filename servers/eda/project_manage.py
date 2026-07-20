r"""EDA 工程管理工具。

list_epp_projects     扫描文件夹中的所有 .epp 工程文件
open_eda_project      打开 .epp 工程，等待 EDA 返回成功或失败
close_eda_project         关闭已打开的工程，可选择是否保存

自然语言使用示例：
  帮我看看 C:\Users\JGL\EDI-Workspace 下面有哪些 .epp 工程
  帮我打开 EDA 工程 C:\...\EDI_TEST.epp
  帮我关闭这个工程（不保存）
  帮我保存并关闭 EDA 工程 C:\...\EDI_TEST.epp

参数说明：
  project_path     EDA 服务所在机器上的 .epp 工程文件绝对路径
  folder_path      要扫描的文件夹绝对路径（list_epp_projects）
  timeout_seconds  最长等待秒数，默认 60 秒
  need_save        关闭前是否保存工程（close_eda_project），默认 False
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from proto import ecserver_pb2
from servers.eda.grpc_client import call_grpc
from servers.eda.config import validate_project_path


def list_epp_projects(folder_path: str) -> dict[str, Any]:
    """扫描指定文件夹，列出其中所有 .epp 工程文件。"""
    root = Path(folder_path).expanduser()
    if not root.is_dir():
        raise FileNotFoundError(f"文件夹不存在: {folder_path}")

    projects = []
    for epp in sorted(root.rglob("*.epp")):
        projects.append({
            "name": epp.stem,
            "path": str(epp.resolve()),
            "size": epp.stat().st_size,
        })

    return {
        "success": True,
        "folder": str(root.resolve()),
        "count": len(projects),
        "projects": projects,
    }


def open_eda_project(
        project_path: str,
        timeout_seconds: int = 60,
) -> dict[str, Any]:
    """
    打开一个 EDA .epp 工程，例如C:\\Users\\JGL\\EDI-Workspace\\projects\\1\\1.epp

    Args:
        project_path: EDA 服务所在机器上的 .epp 工程文件绝对路径。
        timeout_seconds: 最长等待时间，默认 60 秒。
    """
    resolved_path = validate_project_path(project_path)
    return call_grpc(
        ecserver_pb2.OPEN_PROJECT,
        {"project_path": resolved_path},
        timeout_seconds,
    )


def close_eda_project(
        project_path: str,
        need_save: bool = False,
        timeout_seconds: int = 60,
) -> dict[str, Any]:
    """关闭 EDA .epp 工程。

    Args:
        project_path: EDA 服务所在机器上的 .epp 工程文件绝对路径。
        need_save: 关闭前是否保存工程，默认 False。
        timeout_seconds: 最长等待时间，默认 60 秒。
    """
    resolved_path = validate_project_path(project_path)
    return call_grpc(
        ecserver_pb2.CLOSE_PROJECT,
        {"project_path": resolved_path, "need_save": need_save},
        timeout_seconds,
    )
