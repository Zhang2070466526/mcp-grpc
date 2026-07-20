"""EDA 工具公用函数与配置。

导出的配置常量：
  EDA_GRPC_SERVER       gRPC 服务地址，默认 localhost:50055
  EDI_PATH              EDI 客户端可执行文件路径
  MCP_TRANSPORT         MCP 传输方式（stdio / streamable-http）

导出的公共函数：
  validate_project_path(path)  校验 .epp 工程路径，返回规范化绝对路径

使用方式：
  from servers.eda.config import EDA_GRPC_SERVER, validate_project_path
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

EDA_GRPC_SERVER = os.getenv("EDA_GRPC_SERVER", "localhost:50055")
EDI_PATH = os.getenv("EDI_PATH", r"C:\Program Files (x86)\EDI\EDI.exe")
MCP_TRANSPORT = os.getenv("MCP_TRANSPORT", "stdio")


def validate_project_path(project_path: str) -> str:
    """校验工程路径，返回规范化后的绝对路径。"""
    path = Path(project_path).expanduser()
    if path.suffix.lower() != ".epp":
        raise ValueError("project_path 必须指向 .epp 工程文件")
    if not path.is_file():
        raise FileNotFoundError(f"工程文件不存在: {path}")
    return str(path.resolve())
