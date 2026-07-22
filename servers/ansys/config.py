"""ANSYS 公共工具 — 进程检测、COM 附着、Setup 模块。"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
import winreg
from pathlib import Path
from typing import Any

import pythoncom
from dotenv import load_dotenv
from win32com.client import GetActiveObject

load_dotenv()

logger = logging.getLogger(__name__)

_AEDT_LOCK = threading.RLock()
_LAST_PID: int | None = None

# -- 路径 --
def _find_aedt() -> str:
    from_env = os.getenv("AEDT_PATH")
    if from_env and Path(from_env).is_file():
        return from_env
    try:
        for reg_path in [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
            r"SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
        ]:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path)
            for j in range(winreg.QueryInfoKey(key)[0]):
                try:
                    sub = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, f"{reg_path}\\{winreg.EnumKey(key, j)}")
                    name = winreg.QueryValueEx(sub, "DisplayName")[0]
                    if "ANSYS" in name and ("Electromagnetics" in name or "Electronics" in name):
                        loc = winreg.QueryValueEx(sub, "InstallLocation")[0]
                        exe = Path(loc) / "ansysedt.exe"
                        if exe.is_file():
                            return str(exe)
                except OSError:
                    pass
    except Exception:
        pass
    for base in [r"C:\Program Files\AnsysEM", r"C:\Program Files (x86)\AnsysEM"]:
        for sub in sorted(Path(base).iterdir(), reverse=True) if Path(base).is_dir() else []:
            exe = sub / "Win64" / "ansysedt.exe"
            if exe.is_file():
                return str(exe)
    return ""


AEDT_PATH = _find_aedt()


# -- 进程 --
def get_aedt_pids() -> list[int]:
    try:
        import psutil
        return [p.pid for p in psutil.process_iter(["name"]) if p.info["name"] == "ansysedt.exe"]
    except Exception:
        return []


def aedt_is_running() -> bool:
    return len(get_aedt_pids()) > 0


# -- COM --
def query_desktop_state() -> dict[str, Any]:
    """附着现有 AEDT，返回纯字典。绝不创建新实例。"""
    pythoncom.CoInitialize()
    try:
        app = GetActiveObject("Ansoft.ElectronicsDesktop")
        desktop = app.GetAppDesktop()
        projects = list(desktop.GetProjectList())
        active = desktop.GetActiveProject()
        active_name = active.GetName() if active is not None else ""
        active_design = ""
        if active is not None:
            try:
                d = active.GetActiveDesign()
                if d is not None:
                    active_design = d.GetName()
            except Exception:
                pass
        return {
            "connected": True,
            "projects": projects,
            "active_project": active_name,
            "active_design": active_design,
        }
    except Exception as exc:
        return {"connected": False, "error": repr(exc)}
    finally:
        pythoncom.CoUninitialize()


def get_setup_module(design):
    """统一获取 AnalysisSetup 或 SolveSetups 模块。"""
    for mod_name in ("AnalysisSetup", "SolveSetups"):
        try:
            return design.GetModule(mod_name), mod_name
        except Exception:
            continue
    raise RuntimeError("No AnalysisSetup or SolveSetups module found")
