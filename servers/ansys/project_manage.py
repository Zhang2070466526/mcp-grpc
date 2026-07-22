"""ANSYS 工程管理工具 — 打开/关闭/启动 AEDT。"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

import pythoncom
from win32com.client import GetActiveObject

from servers.ansys.config import (
    AEDT_PATH, _AEDT_LOCK, _LAST_PID,
    aedt_is_running, get_aedt_pids, query_desktop_state,
    logger,
)
from servers.eda.config import validate_file
from servers.mcp_instance import mcp


def _com_open_project(project_path: str) -> dict[str, Any]:
    """在现有 AEDT 中通过 COM 打开工程。"""
    pythoncom.CoInitialize()
    try:
        app = GetActiveObject("Ansoft.ElectronicsDesktop")
        desktop = app.GetAppDesktop()
        project_name = Path(project_path).stem

        if project_name in list(desktop.GetProjectList()):
            desktop.SetActiveProject(project_name)
            return {"status": "already_open", "project_name": project_name}

        result = desktop.OpenProject(project_path)
        if result is not None or project_name in list(desktop.GetProjectList()):
            return {"status": "opened", "project_name": project_name}

        return {"status": "com_open_failed", "project_name": project_name,
                "error": "OpenProject returned None and project not in list"}
    except Exception as exc:
        logger.exception("COM OpenProject failed")
        return {"status": "com_open_failed", "project_name": Path(project_path).stem,
                "error": repr(exc)}
    finally:
        pythoncom.CoUninitialize()


@mcp.tool()
def open_hfss_project(
    project_path: str,
    aedt_path: str = "",
    wait_timeout: int = 30,
) -> dict[str, Any]:
    """启动 AEDT 并打开 .aedt 项目（COM 附着，subprocess 单启动）。

    Args:
        project_path: .aedt/.aedtz 项目文件绝对路径。
        aedt_path: AEDT 可执行文件路径，默认自动查找。
        wait_timeout: 超时秒数（1-120）。
    """
    t0 = time.monotonic()
    wait_timeout = max(1, min(wait_timeout, 120))

    try:
        resolved = validate_file(project_path, (".aedt", ".aedtz"))
    except (FileNotFoundError, ValueError) as exc:
        return {"success": False, "status": "invalid_path", "message": str(exc)}

    exe = aedt_path or AEDT_PATH
    exe_path = Path(exe).expanduser()
    if not exe_path.is_file():
        return {"success": False, "status": "aedt_not_found", "message": str(exe_path)}
    if exe_path.name.lower() != "ansysedt.exe":
        return {"success": False, "status": "invalid_aedt_path", "message": "必须以 ansysedt.exe 结尾"}

    project_name = Path(resolved).stem
    global _LAST_PID

    with _AEDT_LOCK:
        aedt_was_running = aedt_is_running()

        if aedt_was_running:
            state = query_desktop_state()
            if not state["connected"]:
                logger.warning("AEDT running but COM attach failed: %s", state.get("error"))
                return {
                    "success": False, "status": "existing_instance_com_unavailable",
                    "aedt_running": True, "project_opened": False,
                    "message": "AEDT 已运行但无法附着 COM，未创建第二个实例",
                }

            if project_name in state["projects"]:
                pythoncom.CoInitialize()
                try:
                    app = GetActiveObject("Ansoft.ElectronicsDesktop")
                    app.GetAppDesktop().SetActiveProject(project_name)
                except Exception:
                    pass
                finally:
                    pythoncom.CoUninitialize()
                return {
                    "success": True, "status": "already_open",
                    "aedt_running": True, "project_opened": True, "verified": True,
                    "project_name": project_name, "project_path": resolved,
                    "method": "com", "duration_s": round(time.monotonic() - t0, 1),
                    "message": f"工程已打开并激活: {project_name}",
                }

            result = _com_open_project(resolved)
            if result["status"] in ("opened", "already_open"):
                return {
                    "success": True, "status": result["status"],
                    "aedt_running": True, "project_opened": True, "verified": True,
                    "project_name": project_name, "project_path": resolved,
                    "method": "com", "duration_s": round(time.monotonic() - t0, 1),
                    "message": f"HFSS 工程已打开: {project_name}",
                }

            logger.error("COM open failed: %s", result.get("error"))
            return {
                "success": False, "status": "com_open_failed",
                "aedt_running": True, "project_opened": False, "verified": True,
                "project_name": project_name, "project_path": resolved,
                "method": "com", "com_error": result.get("error"),
                "message": "AEDT 已运行，但打开工程失败",
            }

        # AEDT 未运行，单次启动
        try:
            proc = subprocess.Popen([str(exe_path), resolved], cwd=str(exe_path.parent))
            _LAST_PID = proc.pid
            logger.info("Launched AEDT PID=%d for %s", proc.pid, project_name)
        except Exception as exc:
            logger.exception("AEDT launch failed")
            return {"success": False, "status": "launch_failed", "message": str(exc)}

        deadline = time.monotonic() + wait_timeout
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                return {
                    "success": False, "status": "process_exited",
                    "aedt_running": False, "project_opened": False,
                    "message": f"AEDT 进程已退出，退出码: {proc.returncode}",
                }
            state = query_desktop_state()
            if state["connected"] and project_name in state["projects"]:
                return {
                    "success": True, "status": "opened",
                    "aedt_running": True, "project_opened": True, "verified": True,
                    "project_name": project_name, "project_path": resolved,
                    "method": "subprocess", "pid": proc.pid,
                    "duration_s": round(time.monotonic() - t0, 1),
                    "message": f"AEDT 已启动，工程已打开: {project_name}",
                }
            time.sleep(1)

        return {
            "success": True, "status": "launch_requested",
            "aedt_running": aedt_is_running(),
            "project_opened": None, "verified": False,
            "project_name": project_name, "project_path": resolved,
            "method": "subprocess", "pid": proc.pid,
            "duration_s": round(time.monotonic() - t0, 1),
            "message": "AEDT 启动命令已发送，COM 暂未验证到工程打开",
        }


@mcp.tool()
def close_hfss_project(
    project_name: str = "",
    save_before_close: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """关闭 AEDT 项目（COM 优先，force 仅结束 MCP 最后启动的 PID）。"""
    global _LAST_PID

    if force and _LAST_PID is not None:
        try:
            subprocess.run(["taskkill", "-f", "-pid", str(_LAST_PID)],
                           capture_output=True, timeout=10)
            pid = _LAST_PID
            _LAST_PID = None
            return {"success": True, "method": "taskkill", "message": f"已终止 PID {pid}"}
        except Exception as exc:
            return {"success": False, "message": str(exc)}

    if not aedt_is_running():
        return {"success": False, "message": "AEDT 未运行"}

    pythoncom.CoInitialize()
    try:
        app = GetActiveObject("Ansoft.ElectronicsDesktop")
        desktop = app.GetAppDesktop()
        names = list(desktop.GetProjectList())

        target = project_name.strip() if project_name else (names[0] if names else "")
        if not target:
            return {"success": False, "message": "没有可关闭的项目"}

        if save_before_close:
            try:
                proj = desktop.SetActiveProject(target)
                if proj is not None:
                    proj.Save()
            except Exception:
                pass

        desktop.CloseProject(target)
        names_after = list(desktop.GetProjectList())
        closed = target not in names_after
        return {
            "success": closed, "method": "com", "project_closed": closed,
            "message": f"已关闭: {target}" if closed else f"未能确认关闭: {target}",
        }
    except Exception as exc:
        logger.exception("COM close failed")
        return {"success": False, "message": f"关闭失败: {exc}"}
    finally:
        pythoncom.CoUninitialize()


@mcp.tool()
def launch_aedt(
    aedt_path: str = "",
    wait_timeout: int = 30,
) -> dict[str, Any]:
    """启动 AEDT（不打开项目）。已运行时仅返回状态。"""
    wait_timeout = max(1, min(wait_timeout, 120))
    global _LAST_PID

    exe = aedt_path or AEDT_PATH
    exe_path = Path(exe).expanduser()
    if not exe_path.is_file():
        return {"success": False, "message": str(exe_path)}
    if exe_path.name.lower() != "ansysedt.exe":
        return {"success": False, "message": "必须以 ansysedt.exe 结尾"}

    with _AEDT_LOCK:
        if aedt_is_running():
            state = query_desktop_state()
            return {"success": True, "status": "already_running",
                    "com_ready": state["connected"], "message": "AEDT 已在运行"}

        try:
            proc = subprocess.Popen([str(exe_path)], cwd=str(exe_path.parent))
            _LAST_PID = proc.pid
        except Exception as exc:
            return {"success": False, "status": "launch_failed", "message": str(exc)}

        deadline = time.monotonic() + wait_timeout
        while time.monotonic() < deadline:
            if query_desktop_state()["connected"]:
                return {"success": True, "status": "started", "com_ready": True,
                        "pid": proc.pid, "message": "AEDT 已启动，COM 就绪"}
            time.sleep(1)

        return {"success": True, "status": "started", "com_ready": False,
                "pid": proc.pid, "message": "AEDT 已启动，COM 未在时间内就绪"}


@mcp.tool()
def get_hfss_project_info() -> dict[str, Any]:
    """查询当前 AEDT 项目信息（纯查询，不启动 AEDT）。"""
    if not aedt_is_running():
        return {"success": True, "aedt_running": False, "message": "AEDT 未运行", "pids": []}

    pids = get_aedt_pids()
    state = query_desktop_state()

    return {
        "success": True,
        "aedt_running": True,
        "pids": pids,
        "com_available": state["connected"],
        "open_projects": state.get("projects", []),
        "active_project": state.get("active_project", ""),
        "active_design": state.get("active_design", ""),
    }
