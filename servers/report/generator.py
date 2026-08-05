"""仿真报告渲染工具 — 调用本地报告渲染服务生成 PDF/DOCX。"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

from servers.mcp_instance import mcp

load_dotenv()
_logger = logging.getLogger("report.generator")

# ── 配置 ──
_REPORT_URL = os.getenv("REPORT_RENDER_URL", "http://127.0.0.1:17867/api/v1/reports/render")

_ALLOWED_EXTENSIONS = {".pdf", ".docx"}
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
_EXPECTED_SPEC_COLUMNS = 7
_MAX_CELL_LENGTH = 10_000
_MAX_FIELD_LENGTHS = {"description": 50_000, "conclusion": 50_000}


def _read_int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return max(minimum, min(int(raw), maximum))
    except ValueError:
        _logger.warning("%s is invalid; using %d", name, default)
        return default


_REPORT_TIMEOUT = _read_int_env("REPORT_RENDER_TIMEOUT_SECONDS", 45, 5, 120)


# ═══════════════════════════════════════════════════════════
# 校验
# ═══════════════════════════════════════════════════════════

def _validate_output(path: str, overwrite: bool) -> tuple[str, str] | tuple[None, dict]:
    if not isinstance(path, str) or not path.strip():
        return None, _error("INVALID_OUTPUT_PATH", "output_path 不能为空")
    p = Path(path)
    if not p.is_absolute():
        return None, _error("INVALID_OUTPUT_PATH", "output_path 必须是绝对路径")
    if str(p).startswith(r"\\") or str(p).startswith("//"):
        return None, _error("INVALID_OUTPUT_PATH", "禁止网络路径")
    ext = p.suffix.lower()
    if ext not in _ALLOWED_EXTENSIONS:
        return None, _error("INVALID_OUTPUT_PATH", f"后缀必须是 .pdf 或 .docx")
    if not p.parent.is_dir():
        return None, _error("OUTPUT_DIRECTORY_NOT_FOUND", f"输出目录不存在: {p.parent}")
    if p.exists() and not overwrite:
        return None, _error("OUTPUT_ALREADY_EXISTS",
                             f"输出文件已存在: {p.name}。如需覆盖，请设置 overwrite=true")
    return ext.lstrip("."), None


def _validate_spec_table(table: list | None) -> dict | None:
    if table is None:
        return None
    if not isinstance(table, list):
        return _error("INVALID_REPORT_PARAMETERS", "spec_table 必须是数组")
    if not table:
        return None
    if not all(isinstance(row, list) for row in table):
        return _error("INVALID_REPORT_PARAMETERS", "spec_table 必须是二维数组")
    if len(table) > 1000:
        return _error("INVALID_REPORT_PARAMETERS", "spec_table 最多 1000 行")
    if len(table[0]) != _EXPECTED_SPEC_COLUMNS:
        return _error("INVALID_REPORT_PARAMETERS",
                       f"spec_table 必须固定为 {_EXPECTED_SPEC_COLUMNS} 列")
    for i, row in enumerate(table):
        if len(row) != _EXPECTED_SPEC_COLUMNS:
            return _error("INVALID_REPORT_PARAMETERS",
                           f"spec_table 第 {i+1} 行列数({len(row)})与表头({_EXPECTED_SPEC_COLUMNS})不一致")
        for cell in row:
            if cell is None or isinstance(cell, bool) or not isinstance(cell, (str, int, float)):
                return _error("INVALID_REPORT_PARAMETERS",
                               "spec_table 单元格仅允许字符串、整数、浮点数")
            if isinstance(cell, str) and len(cell) > _MAX_CELL_LENGTH:
                return _error("INVALID_REPORT_PARAMETERS",
                               f"spec_table 单元格过长（最大 {_MAX_CELL_LENGTH} 字符）")
    return None


def _validate_charts(charts: list | None) -> tuple[list | None, list[str], dict | None]:
    warnings: list[str] = []
    if charts is None:
        return None, warnings, None
    if not isinstance(charts, list):
        return None, warnings, _error("INVALID_REPORT_PARAMETERS", "charts 必须是数组")
    if not charts:
        return None, warnings, None
    if len(charts) > 50:
        return None, warnings, _error("INVALID_REPORT_PARAMETERS", "charts 最多 50 张")
    validated: list[dict] = []
    for i, c in enumerate(charts):
        if not isinstance(c, dict):
            return None, warnings, _error("INVALID_REPORT_PARAMETERS", f"charts[{i}] 必须是对象")
        path = c.get("path", "")
        title = c.get("title", "")
        if not isinstance(path, str) or not isinstance(title, str):
            return None, warnings, _error("INVALID_REPORT_PARAMETERS",
                                           f"charts[{i}].path 和 title 必须是字符串")
        if len(title) > 500:
            return None, warnings, _error("INVALID_REPORT_PARAMETERS",
                                           f"charts[{i}].title 最长 500 字符")
        p = Path(path)
        if not p.is_absolute():
            return None, warnings, _error("INVALID_CHART_PATH", f"charts[{i}].path 必须是绝对路径")
        if str(p).startswith(r"\\") or str(p).startswith("//"):
            return None, warnings, _error("INVALID_CHART_PATH", "禁止网络路径")
        if p.suffix.lower() not in _IMAGE_EXTENSIONS:
            return None, warnings, _error("INVALID_CHART_PATH",
                                           f"charts[{i}].path 后缀必须是 PNG/JPG/JPEG")
        if not p.is_file():
            warnings.append(f"图片未找到: {p.name}")
        validated.append({"path": str(p.resolve()), "title": title})
    return validated, warnings, None


def _validate_components(comps: list | None) -> dict | None:
    if comps is None:
        return None
    if not isinstance(comps, list):
        return _error("INVALID_REPORT_PARAMETERS", "components 必须是数组")
    if not comps:
        return None
    if len(comps) > 500:
        return _error("INVALID_REPORT_PARAMETERS", "components 最多 500 条")
    for i, c in enumerate(comps):
        if not isinstance(c, dict):
            return _error("INVALID_REPORT_PARAMETERS", f"components[{i}] 必须是对象")
        for field in ("type", "model", "manufacturer", "specs"):
            val = c.get(field, "")
            if not isinstance(val, str):
                return _error("INVALID_REPORT_PARAMETERS", f"components[{i}].{field} 必须是字符串")
            if len(val) > 2000:
                return _error("INVALID_REPORT_PARAMETERS",
                               f"components[{i}].{field} 最长 2000 字符")
    return None


def _validate_schematic(path: str) -> tuple[str | None, bool, dict | None]:
    if not path or not isinstance(path, str) or not path.strip():
        return None, False, None
    p = Path(path)
    if not p.is_absolute():
        return None, False, _error("INVALID_REPORT_PARAMETERS", "schematic 必须是绝对路径")
    if str(p).startswith(r"\\") or str(p).startswith("//"):
        return None, False, _error("INVALID_REPORT_PARAMETERS", "禁止网络路径")
    if p.suffix.lower() not in _IMAGE_EXTENSIONS:
        return None, False, _error("INVALID_REPORT_PARAMETERS",
                                   "schematic 后缀必须是 PNG/JPG/JPEG")
    missing = not p.is_file()
    return str(p.resolve()), missing, None


# ═══════════════════════════════════════════════════════════
# 工具
# ═══════════════════════════════════════════════════════════

@mcp.tool()
def generate_simulation_report(
    output_path: str,
    model_name: str,
    description: str = "",
    conclusion: str = "",
    spec_table: list | None = None,
    charts: list | None = None,
    components: list | None = None,
    schematic: str = "",
    overwrite: bool = False,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    """生成本地仿真报告（PDF/DOCX），调用本地报告渲染服务。"""

    # 1. output_path
    file_type, err = _validate_output(output_path, overwrite)
    if err:
        return err

    # 2. model_name
    if not isinstance(model_name, str):
        return _error("INVALID_REPORT_PARAMETERS", "model_name 必须是字符串")
    mn = model_name.strip()
    if not mn:
        return _error("INVALID_REPORT_PARAMETERS", "model_name 不能为空")
    if len(mn) > 200:
        return _error("INVALID_REPORT_PARAMETERS", "model_name 最长 200 字符")

    # 3. type checks + length limits
    for field, max_len in _MAX_FIELD_LENGTHS.items():
        val = locals().get(field, "")
        if not isinstance(val, str):
            return _error("INVALID_REPORT_PARAMETERS", f"{field} 必须是字符串")
        if len(val) > max_len:
            return _error("INVALID_REPORT_PARAMETERS", f"{field} 最长 {max_len} 字符")
    if not isinstance(overwrite, bool):
        return _error("INVALID_REPORT_PARAMETERS", "overwrite 必须是布尔值")

    # 4. spec_table
    err = _validate_spec_table(spec_table)
    if err:
        return err

    # 5. charts
    valid_charts, chart_warnings, chart_error = _validate_charts(charts)
    if chart_error:
        return chart_error

    # 6. components
    err = _validate_components(components)
    if err:
        return err

    # 7. schematic
    schematic_path, schematic_missing, s_err = _validate_schematic(schematic)
    if s_err:
        return s_err

    # 8. Resolve timeout
    effective_timeout = _REPORT_TIMEOUT
    if timeout_seconds is not None:
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int):
            return _error("INVALID_REPORT_PARAMETERS", "timeout_seconds 必须是整数")
        effective_timeout = max(5, min(timeout_seconds, 120))

    # 9. Build payload
    expected_output = Path(output_path).expanduser().resolve()
    payload = {
        "output_path": str(expected_output),
        "file_type": file_type,
        "overwrite": overwrite,
        "report": {
            "model_name": mn,
            "description": description,
            "conclusion": conclusion,
            "spec_table": spec_table or [],
            "charts": valid_charts or [],
            "components": components or [],
            "schematic": schematic_path or "",
        },
    }

    # 10. Call report service
    t0 = time.monotonic()
    try:
        with httpx.Client(timeout=effective_timeout) as client:
            resp = client.post(
                _REPORT_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
    except httpx.ConnectError:
        return _error("REPORT_SERVICE_UNAVAILABLE",
                       "无法连接本地报告渲染服务，请确认服务已启动。", retryable=True)
    except httpx.TimeoutException:
        return _error("REPORT_RENDER_TIMEOUT",
                       f"报告渲染超时（{effective_timeout}s）", retryable=True)
    except httpx.RequestError as e:
        return _error("REPORT_SERVICE_UNAVAILABLE",
                       f"报告渲染请求失败: {e}", retryable=True)

    elapsed = round(time.monotonic() - t0, 1)
    _logger.info("report_render status=%d file_type=%s elapsed=%s",
                 resp.status_code, file_type, elapsed)

    # 11. Map HTTP errors
    if resp.status_code == 400:
        return _error("REPORT_VALIDATION_FAILED",
                       f"报告数据校验失败: {_safe_json_text(resp)}")
    if resp.status_code == 409:
        return _error("OUTPUT_FILE_BUSY",
                       "输出文件无法写入（可能被占用）", retryable=True)
    if resp.status_code != 200:
        return _error("REPORT_RENDER_FAILED",
                       f"报告渲染失败 (HTTP {resp.status_code}): {_safe_json_text(resp)}")

    # 12. Parse response
    try:
        data = resp.json()
    except Exception:
        return _error("INVALID_REPORT_RESPONSE", "报告服务返回无法解析")

    if not isinstance(data, dict):
        return _error("INVALID_REPORT_RESPONSE", "报告服务返回格式异常")
    if not data.get("success"):
        return _error("REPORT_RENDER_FAILED", data.get("error", "报告渲染失败"))

    # 13. Verify returned path matches request
    returned_raw = data.get("file_path")
    if not isinstance(returned_raw, str) or not returned_raw.strip():
        return _error("INVALID_REPORT_RESPONSE", "报告服务未返回有效 file_path")
    returned_path = Path(returned_raw).expanduser().resolve()
    if returned_path != expected_output:
        return _error("REPORT_OUTPUT_PATH_MISMATCH",
                       f"报告服务返回的文件路径与请求不一致")

    # 14. Self-verify output file
    if not expected_output.is_file():
        return _error("REPORT_OUTPUT_NOT_FOUND", "报告服务返回成功，但未找到生成的文件")
    actual_size = expected_output.stat().st_size
    if actual_size <= 0:
        return _error("REPORT_OUTPUT_EMPTY", "生成的报告文件为空")

    # 15. Build response
    warnings: list[str] = list(chart_warnings)
    if schematic_missing:
        warnings.append("原理图文件未找到，已跳过链路拓扑章节")

    return {
        "success": True,
        "file_path": str(expected_output),
        "file_type": data.get("file_type", file_type),
        "file_size": actual_size,
        "sections": data.get("sections", []),
        "chart_count": data.get("chart_count", 0),
        "component_count": data.get("component_count", 0),
        "spec_row_count": data.get("spec_row_count", 0),
        "created_at": data.get("created_at", ""),
        "warnings": warnings,
        "output_verified": True,
    }


# ═══════════════════════════════════════════════════════════
# 辅助
# ═══════════════════════════════════════════════════════════

def _error(code: str, message: str, retryable: bool = False) -> dict:
    result: dict = {"success": False, "error_code": code, "message": message}
    if retryable:
        result["retryable"] = True
    return result


def _safe_json_text(resp) -> str:
    try:
        data = resp.json()
        return data.get("error", resp.text[:200])
    except Exception:
        return resp.text[:200]
