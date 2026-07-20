r"""EDA gRPC MCP 工具 — 通过 ExternalCall gRPC 操作 EDA 工程。

list_epp_projects     扫描文件夹，列出所有 .epp 工程
open_eda_project      打开 .epp 工程
view_project_netlist  查看/导出工程网表
simulate_project      执行工程仿真
launch_edi            启动 EDI 客户端，等待 gRPC 就绪


自然语言调用示例：
  帮我看看 C:\Users\JGL\EDI-Workspace 下面有哪些 .epp 工程
  帮我启动 EDI
  帮我打开 EDA 工程 C:\Users\JGL\EDI-Workspace\EDI_TEST\EDI_TEST.epp
  帮我查看 EDA 工程 C:\Users\JGL\EDI-Workspace\EDI_TEST\EDI_TEST.epp 的网表
  帮我对 EDA 工程 C:\Users\JGL\EDI-Workspace\EDI_TEST\EDI_TEST.epp 执行仿真

参数说明：
  folder_path      要扫描的文件夹绝对路径（list_epp_projects）
  project_path     EDA 服务所在机器上的 .epp 工程文件绝对路径（必填）
  timeout_seconds  最长等待秒数，默认 60（open/view）或 120（simulate），范围 1-600
  log_source       simulate_project 的调用方标识，默认 "mcp_client"
  wait_for_grpc    launch_edi 是否等待 gRPC 就绪，默认 True
  wait_timeout     launch_edi 等待 gRPC 就绪的超时秒数，默认 30
"""

from __future__ import annotations

import os
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from proto import ecserver_pb2
from servers.eda.grpc_client import call_grpc

load_dotenv()

# -- 配置 --
EDA_GRPC_SERVER = os.getenv("EDA_GRPC_SERVER", "localhost:50055")
EDI_PATH = os.getenv("EDI_PATH", r"C:\Program Files (x86)\EDI\EDI.exe")
MCP_TRANSPORT = os.getenv("MCP_TRANSPORT", "stdio")

# ---------------------------------------------------------------------------
# MCP 实例
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "EDA ExternalCall",
    instructions="通过 EDA-PMDS/EDI 的 gRPC 接口操作 EDA 工程。",
)


# ---------------------------------------------------------------------------
# 内部工具函数
# ---------------------------------------------------------------------------

def _validate_project_path(project_path: str) -> str:
    """校验工程路径，返回规范化后的绝对路径。"""
    path = Path(project_path).expanduser()
    if path.suffix.lower() != ".epp":
        raise ValueError("project_path 必须指向 .epp 工程文件")
    if not path.is_file():
        raise FileNotFoundError(f"工程文件不存在: {path}")
    return str(path.resolve())


# ---------------------------------------------------------------------------
# MCP 工具
# ---------------------------------------------------------------------------

@mcp.tool()
def list_epp_projects(
    folder_path: str,
) -> dict[str, Any]:
    """扫描指定文件夹，列出其中所有 .epp 工程文件。

    Args:
        folder_path: 要扫描的文件夹绝对路径。
    """
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


@mcp.tool(description="打开一个 EDA .epp 工程，例如C:\\Users\\JGL\\EDI-Workspace\\projects\\1\\1.epp")
def open_eda_project(
    project_path: str,
    timeout_seconds: int = 60,

) -> dict[str, Any]:
    """打开一个 EDA .epp 工程，等待返回成功或失败结果。

    Args:
        project_path: EDA 服务所在机器上的 .epp 工程文件绝对路径。
        timeout_seconds: 最长等待时间，默认 60 秒，范围 1-600 秒。
    """
    resolved_path = _validate_project_path(project_path)
    return call_grpc(
        ecserver_pb2.OPEN_PROJECT,
        {"project_path": resolved_path},
        timeout_seconds,
    )


@mcp.tool()
def view_project_netlist(
    project_path: str,
    timeout_seconds: int = 60,
) -> dict[str, Any]:
    """查看 EDA .epp 工程的网表，返回网表文件路径。

    Args:
        project_path: EDA 服务所在机器上的 .epp 工程文件绝对路径。
        timeout_seconds: 最长等待时间，默认 60 秒，范围 1-600 秒。
    """
    resolved_path = _validate_project_path(project_path)
    return call_grpc(
        ecserver_pb2.VIEW_PROJECT_NETLIST,
        {"project_path": resolved_path},
        timeout_seconds,
    )


@mcp.tool()
def simulate_project(
    project_path: str,
    log_source: str = "mcp_client",
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    """对 EDA .epp 工程执行仿真，等待仿真完成并返回结果。

    Args:
        project_path: EDA 服务所在机器上的 .epp 工程文件绝对路径。
        log_source: 调用方日志标识。
        timeout_seconds: 最长等待时间，默认 120 秒，范围 1-600 秒。
    """
    resolved_path = _validate_project_path(project_path)
    return call_grpc(
        ecserver_pb2.SIMULATE_PROJECT,
        {
            "project_path": resolved_path,
            "log_source": log_source,
        },
        timeout_seconds,
    )


@mcp.tool()
def launch_edi(
    edi_path: str = "",
    wait_for_grpc: bool = True,
    wait_timeout: int = 30,
) -> dict[str, Any]:
    """启动 EDI 客户端应用程序。

    启动后会等待 EDI 的 gRPC 服务就绪，确保后续操作可直接使用。

    Args:
        edi_path: EDI.exe 路径，默认使用配置的 EDI_PATH。
        wait_for_grpc: 是否等待 gRPC 服务端口就绪，默认 True。
        wait_timeout: 等待 gRPC 就绪的超时秒数，默认 30 秒。
    """
    exe = edi_path or EDI_PATH
    exe_path = Path(exe).expanduser()
    if not exe_path.is_file():
        raise FileNotFoundError(f"EDI.exe 不存在: {exe_path}")

    # 检查是否已经在运行
    host, port_str = EDA_GRPC_SERVER.rsplit(":", 1)
    port = int(port_str)
    already_running = False
    try:
        with socket.create_connection((host, port), timeout=1):
            already_running = True
    except OSError:
        pass

    if already_running:
        return {
            "success": True,
            "message": f"EDI 已在运行（gRPC {EDA_GRPC_SERVER} 已就绪）",
            "edi_path": str(exe_path),
            "grpc_server": EDA_GRPC_SERVER,
        }

    # 启动 EDI
    try:
        subprocess.Popen(
            [str(exe_path)],
            cwd=str(exe_path.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        raise RuntimeError(f"无法启动 EDI.exe: {exc}") from exc

    result: dict[str, Any] = {
        "success": True,
        "message": "EDI 已启动",
        "edi_path": str(exe_path),
        "grpc_server": EDA_GRPC_SERVER,
    }

    # 等待 gRPC 就绪
    if wait_for_grpc:
        started = time.monotonic()
        while time.monotonic() - started < wait_timeout:
            try:
                with socket.create_connection((host, port), timeout=1):
                    result["grpc_ready"] = True
                    result["message"] += (
                        f"，gRPC 服务已就绪（{time.monotonic() - started:.1f}s）"
                    )
                    return result
            except OSError:
                time.sleep(1)

        result["grpc_ready"] = False
        result["message"] += "，gRPC 服务未在规定时间内就绪"

    return result


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport=MCP_TRANSPORT)
