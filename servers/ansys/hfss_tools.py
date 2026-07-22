r"""ANSYS HFSS 工具 — subprocess 启动 + COM 辅助。

open_hfss_project         启动 AEDT 并打开 .aedt 项目
close_hfss_project        关闭 AEDT 项目

注：仿真执行和项目查询需要 AEDT 脚本录制支持。
    在 AEDT 中 Tools > Record Script to File 可生成 IronPython 脚本，
    将脚本路径传入 run_hfss_script 执行。
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from servers.mcp_instance import mcp

load_dotenv()

AEDT_PATH = os.getenv("AEDT_PATH", r"C:\Program Files\AnsysEM\AnsysEM20.2\Win64\ansysedt.exe")


@mcp.tool()
def open_hfss_project(
    project_path: str,
    aedt_path: str = "",
    wait_timeout: int = 30,
) -> dict[str, Any]:
    """启动 AEDT 并打开指定的 .aedt 项目文件。

    先尝试通过 COM 连接已运行的 AEDT，失败则用 subprocess 启动。

    Args:
        project_path: .aedt 项目文件绝对路径。
        aedt_path: AEDT 可执行文件路径，默认从 AEDT_PATH 读取。
        wait_timeout: 等待 AEDT 启动的超时秒数，默认 30。
    """
    path = Path(project_path).expanduser()
    if not path.is_file():
        return {"success": False, "message": f"项目文件不存在: {path}"}
    if path.suffix.lower() not in (".aedt", ".aedtz"):
        return {"success": False, "message": "project_path 必须是 .aedt 或 .aedtz 文件"}

    exe = aedt_path or AEDT_PATH
    exe_path = Path(exe).expanduser()
    if not exe_path.is_file():
        return {"success": False, "message": f"AEDT 不存在: {exe_path}"}

    resolved = str(path.resolve())

    # 尝试 COM
    try:
        import pythoncom
        pythoncom.CoInitialize()
        from win32com.client import Dispatch
        com = Dispatch("Ansoft.ElectronicsDesktop")
        if com is not None:
            return {
                "success": True,
                "message": f"AEDT 已在运行，请手动打开: {path.name}",
                "project_path": resolved,
                "note": "2020R2 COM 不支持 OpenProject，请从 AEDT GUI 打开",
            }
    except Exception:
        pass

    # subprocess 启动
    try:
        subprocess.Popen(
            [str(exe_path), resolved],
            cwd=str(exe_path.parent),
        )
    except Exception as exc:
        return {"success": False, "message": f"启动 AEDT 失败: {exc}"}

    time.sleep(2)
    return {
        "success": True,
        "message": f"AEDT 已启动，项目: {path.name}",
        "project_path": resolved,
    }


@mcp.tool()
def close_hfss_project() -> dict[str, Any]:
    """关闭 AEDT 进程。"""
    try:
        subprocess.run(["taskkill", "-f", "-im", "ansysedt.exe"],
                       capture_output=True, timeout=10)
        return {"success": True, "message": "AEDT 已关闭"}
    except Exception as exc:
        return {"success": False, "message": f"关闭失败: {exc}"}


@mcp.tool()
def launch_aedt(
    aedt_path: str = "",
) -> dict[str, Any]:
    """启动 AEDT（不打开项目）。

    Args:
        aedt_path: AEDT 可执行文件路径，默认从 AEDT_PATH 读取。
    """
    exe = aedt_path or AEDT_PATH
    exe_path = Path(exe).expanduser()
    if not exe_path.is_file():
        return {"success": False, "message": f"AEDT 不存在: {exe_path}"}

    try:
        subprocess.Popen([str(exe_path)], cwd=str(exe_path.parent))
        return {"success": True, "message": "AEDT 已启动"}
    except Exception as exc:
        return {"success": False, "message": f"启动失败: {exc}"}


@mcp.tool()
def get_hfss_project_info() -> dict[str, Any]:
    """获取当前 AEDT 项目信息。

    注：2020R2 COM API 支持有限，此功能需新版 pyaedt 或 IronPython 脚本。
    """
    try:
        import pythoncom
        pythoncom.CoInitialize()
        from win32com.client import Dispatch
        com = Dispatch("Ansoft.ElectronicsDesktop")
        if com is None:
            return {"success": False, "message": "AEDT 未运行"}
        return {
            "success": True,
            "message": "AEDT 已连接",
            "note": "2020R2 COM API 不支持详细项目查询，请在 AEDT GUI 中查看",
        }
    except Exception:
        return {
            "success": False,
            "message": "AEDT 未运行或 COM 不可用，项目信息请在 AEDT GUI 中查看",
        }
