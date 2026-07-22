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

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

EDA_GRPC_SERVER = os.getenv("EDA_GRPC_SERVER")
EDI_PATH = os.getenv("EDI_PATH")
MCP_TRANSPORT = os.getenv("MCP_TRANSPORT")


def validate_project_path(project_path: str) -> str:
    """校验工程路径，返回规范化后的绝对路径。"""
    path = Path(project_path).expanduser()
    if path.suffix.lower() != ".epp":
        raise ValueError("project_path 必须指向 .epp 工程文件")
    if not path.is_file():
        raise FileNotFoundError(f"工程文件不存在: {path}")
    return str(path.resolve())


# === S-expression parser & project reader ===

class ProjectReader:
    """读取 EDA 工作空间中的工程文件。"""

    def __init__(self, project_path: str) -> None:
        self.epp_path = Path(project_path).expanduser()
        if not self.epp_path.is_file():
            raise FileNotFoundError(f"工程文件不存在: {self.epp_path}")
        if self.epp_path.suffix.lower() != ".epp":
            raise ValueError("project_path 必须指向 .epp 工程文件")
        self.workspace = self.epp_path.parent

    def read_text(self, relative_path: str) -> str | None:
        p = self.workspace / relative_path
        if not p.is_file():
            return None
        return p.read_text(encoding="utf-8")

    def read_metadata(self) -> dict[str, Any]:
        raw = self.read_text("project/metadata.ep") or ""
        items = list(parse_sexp(raw))
        if not items:
            return {}
        meta = items[0] if isinstance(items[0], list) else []
        return {
            "project_id": meta[1] if len(meta) > 1 else "",
            "name": _kv(meta, "name"),
            "author": _kv(meta, "author"),
            "version": _kv(meta, "version"),
            "created": _kv(meta, "created"),
        }

    def list_schematics(self) -> list[str]:
        """列出原理图名称（如 'main'），去掉了路径前缀。"""
        raw = self.read_text("schematics/schematics.ep") or ""
        items = list(parse_sexp(raw))
        names: list[str] = []
        schematic_entries = _walk_find(items, "schematic")
        for entry in schematic_entries:
            if len(entry) >= 2:
                path = entry[1].strip('"')
                # "schematics/main/schematic.ep" -> "main"
                name = Path(path).parent.name if "/" in path else path
                names.append(name)
        return names

    def read_schematic(self, name: str = "main") -> str | None:
        if ".." in name or "/" in name or "\\" in name:
            return None
        return self.read_text(f"schematics/{name}/schematic.ep")

    def read_netlist(self) -> str | None:
        return self.read_text("netlist.log")

    def file_exists(self, relative_path: str) -> bool:
        return (self.workspace / relative_path).is_file()

    def file_size(self, relative_path: str) -> int:
        p = self.workspace / relative_path
        return p.stat().st_size if p.is_file() else 0


# ---------------------------------------------------------------------------
# S-expression parser
# ---------------------------------------------------------------------------

def parse_sexp(text: str) -> Any:
    """Parse EDA S-expression format, yielding top-level expressions.

    Handles nested parens, quoted strings with escaped quotes,
    and barewords.
    """
    text = text.strip()
    pos = 0

    def peek():
        return text[pos] if pos < len(text) else ""

    def skip_ws():
        nonlocal pos
        while pos < len(text) and text[pos] in " \t\n\r":
            pos += 1

    _escape_map = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"'}

    def read_string():
        nonlocal pos
        result = []
        pos += 1  # skip opening "
        while pos < len(text):
            ch = text[pos]
            if ch == "\\" and pos + 1 < len(text):
                next_ch = text[pos + 1]
                result.append(_escape_map.get(next_ch, next_ch))
                pos += 2
            elif ch == '"':
                pos += 1
                return "".join(result)
            else:
                result.append(ch)
                pos += 1
        return "".join(result)

    def read_bare():
        nonlocal pos
        start = pos
        while pos < len(text) and text[pos] not in " \t\n\r()":
            pos += 1
        return text[start:pos]

    def parse_one():
        nonlocal pos
        skip_ws()
        if pos >= len(text):
            return None
        ch = peek()
        if ch == "(":
            pos += 1
            items = []
            while True:
                skip_ws()
                if pos >= len(text):
                    break
                if peek() == ")":
                    pos += 1
                    break
                item = parse_one()
                if item is not None:
                    items.append(item)
            return items
        elif ch == '"':
            return read_string()
        else:
            return read_bare()

    while True:
        skip_ws()
        if pos >= len(text):
            break
        result = parse_one()
        if result is not None:
            yield result


def _walk_find(items: list[Any], tag: str) -> list[list[Any]]:
    """Recursively find all sublists starting with tag."""
    results: list[list[Any]] = []
    for item in items:
        if isinstance(item, list) and len(item) >= 1 and item[0] == tag:
            results.append(item)
        elif isinstance(item, list):
            results.extend(_walk_find(item, tag))
    return results


def _kv(items, key):
    """Extract (key "value") from S-expression list, recursive into sublists."""
    for i, item in enumerate(items):
        if isinstance(item, str) and item == key and i + 1 < len(items):
            val = items[i + 1]
            if isinstance(val, str):
                return val.strip('"')
    for item in items:
        if isinstance(item, list):
            result = _kv(item, key)
            if result:
                return result
    return ""


def parse_paramsinfo(raw):
    """Parse component paramsinfo JSON string."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def parse_components(schematic_text):
    """Extract all components from a schematic.ep S-expression."""
    items = list(parse_sexp(schematic_text))
    comps = []
    for comp in _walk_find(items, "component"):
        if len(comp) < 3:
            continue

        comp_id = comp[1] if isinstance(comp[1], str) else ""
        comp_type = _kv(comp, "type")
        name = _kv(comp, "name")
        model_id = _kv(comp, "component_uuid")

        pin_count = len(_walk_find(comp, "pin"))

        params_raw = ""
        psi_entries = _walk_find(comp, "paramsinfo")
        if psi_entries and len(psi_entries[0]) >= 2:
            params_raw = psi_entries[0][1]

        params = parse_paramsinfo(params_raw) if params_raw else {}
        param_count = len(params) - 1 if "BasicParameters" in params else len(params)

        comps.append({
            "component_id": comp_id,
            "name": name,
            "type": comp_type,
            "model_id": model_id,
            "pin_count": pin_count,
            "parameter_count": max(0, param_count),
            "paramsinfo": params,
        })

    return comps
