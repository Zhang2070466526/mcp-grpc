r"""Turbocharts MCP 工具 — ADS RAW 文件转曲线图与 CSV。


turbocharts_convert   将 ADS 仿真 RAW 结果转为 PNG 曲线图和 CSV


自然语言调用示例：
    帮我把 D:\results\result_tr.raw 转成 S 参数增益曲线图，
    输出到 D:\results\gain.png，曲线 DB_S[2,1]，依赖轴 freq

    帮我把 D:\results\result.raw 转成噪声系数图，输出 noise.png，
    曲线 real_nf(1)，同时导出 CSV 到 noise.csv

参数说明：
    raw_path    ADS RAW 结果文件路径（必填）
    img_path    输出图片路径，支持 PNG/JPG 等（必填）
    chart_type  转换类型："SP"（S参数）、"HB"（谐波平衡）、"XDB"（必填）

    可选参数：
    csv_path    同时导出的 CSV 文件路径
    linename    曲线名，格式 单位_曲线名[端口]，多条用 & 分隔
              DB_S[2,1]（增益）  DB_S[1,2]（反向增益）
              real_nf(1)（噪声） VSWR_S[1,1]（驻波）
              real_delayS[2,1]（时延） APS_S[2,1]（附加相移）
    dependency  依赖轴，通常为 "freq"
    ac_config   精度配置，格式 ac_type#bit#data#nv_type#nv_value
              例 "phase#3#S[2,1]#fv#0.1"
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()

# -- 配置 --
TURBOCHARTS_PATH = os.getenv(
    "TURBOCHARTS_PATH", r"C:\Program Files (x86)\EDI\turbocharts_app.exe"
)
MCP_TRANSPORT = os.getenv("MCP_TRANSPORT", "stdio")

# ---------------------------------------------------------------------------
# MCP 实例
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "RawConverter",
    instructions="使用 RawConverter 将 ADS RAW 仿真结果转换为曲线图和 CSV 数据。",
)


# ---------------------------------------------------------------------------
# 内部工具函数
# ---------------------------------------------------------------------------

def _validate_file(path: str, description: str) -> str:
    """校验文件存在，返回规范化路径。"""
    p = Path(path).expanduser()
    if not p.is_file():
        raise FileNotFoundError(f"{description} 不存在: {p}")
    return str(p.resolve())


# ---------------------------------------------------------------------------
# MCP 工具
# ---------------------------------------------------------------------------

@mcp.tool()
def turbocharts_convert(
    raw_path: str,
    img_path: str,
    chart_type: str,
    csv_path: str = "",
    linename: str = "",
    dependency: str = "",
    ac_config: str = "",
) -> dict[str, Any]:
    """将 ADS RAW 仿真结果文件转换为曲线图和可选的 CSV 数据。

    支持的转换类型（--type）:
        SP  - S 参数分析（增益、驻波、时延、噪声等）
        HB  - 谐波平衡分析
        XDB - XDB 分析

    曲线名格式（--linename）:
        格式为 单位_曲线名[端口]，多条曲线用 & 分隔。

        常用单位前缀: DB（dB值）、real（实数）、VSWR（驻波）、
                     APS（附加相移）、MAS（衰减态幅度）、
                     MV（幅度波动）、PSS（移相态）

        常用曲线示例:
        ├─ DB_S[2,1]          S参数输出增益
        ├─ DB_S[1,2]          S参数反向增益
        ├─ real_nf(1)         噪声系数
        ├─ VSWR_S[1,1]        输入驻波
        ├─ real_delayS[2,1]   群时延
        ├─ APS_S[2,1]         数控衰减器附加相移
        ├─ MAS_S[2,1]         数控移相器衰减态
        ├─ MV_S[2,1]          数控移相器幅度波动
        └─ PSS_S[2,1]         数控移相器移相态

    精度配置（--ac）:
        格式: ac_type#bit#data#nv_type#nv_value
        ac_type: phase（相位精度）或 att（衰减精度）
        bit:     精度位数（正整数）
        data:    曲线名称（多条用 & 分隔）
        nv_type: fv（固定间隔）或 cl（完整列表）
        nv_value: 间隔值（fv）或用逗号分隔的值列表（cl）
        示例: "phase#3#S[2,1]#fv#0.1"

    Args:
        raw_path: 输入的 ADS RAW 文件路径（必填）。
        img_path: 输出的图像文件路径，支持 PNG/JPG 等（必填）。
        chart_type: 转换类型，如 "SP"、"HB"、"XDB"（必填）。
        csv_path: 可选，同时导出的 CSV 文件路径。
        linename: 可选，曲线名，格式为 单位_曲线名[端口]。
        dependency: 可选，依赖轴名称，通常为 "freq"。
        ac_config: 可选，精度配置，格式 ac_type#bit#data#nv_type#nv_value。

    Returns:
        包含 success / return_code / output_paths / img_generated / csv_generated 的结果字典。
    """
    _validate_file(raw_path, "RAW 文件")
    _validate_file(TURBOCHARTS_PATH, "RawConverter")

    cmd = [TURBOCHARTS_PATH, "--raw", raw_path, "--img", img_path, "--type", chart_type]

    if csv_path:
        cmd.extend(["--csv", csv_path])
    if linename:
        cmd.extend(["--linename", linename])
    if dependency:
        cmd.extend(["--dependcy", dependency])
    if ac_config:
        cmd.extend(["--ac", ac_config])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        raise RuntimeError("RawConverter 执行超时（120秒）")

    img_generated = Path(img_path).exists()
    csv_generated = bool(csv_path) and Path(csv_path).exists()

    return {
        "success": result.returncode == 0,
        "return_code": result.returncode,
        "command": " ".join(cmd),
        "stdout": result.stdout.strip() or "",
        "stderr": result.stderr.strip() or "",
        "img_generated": img_generated,
        "csv_generated": csv_generated,
        "output_paths": {"img": img_path} | ({"csv": csv_path} if csv_path else {}),
    }


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport=MCP_TRANSPORT)
