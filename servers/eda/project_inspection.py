"""仿真结果对比工具。

compare_simulation_results  多个 RAW 仿真结果同一条曲线对比叠图
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any


def compare_simulation_results(
    result_paths: list[str],
    curve: str,
    img_path: str,
    chart_type: str = "SP",
    labels: list[str] | None = None,
    dependency: str = "freq",
    csv_path: str = "",
    alignment: str = "intersection",
    reference_index: int = 0,
) -> dict[str, Any]:
    """比较多个 RAW 仿真结果文件中的同一条曲线并生成对比图。

    V1 实现：逐个 RAW 调用 turbocharts 导出 CSV，
    读取后按依赖轴对齐，生成对比图和指标。

    Args:
        result_paths: RAW 文件路径列表（2-8 个）。
        curve: 曲线名，如 "DB_S[2,1]"。
        img_path: 对比图输出路径。
        chart_type: 图表类型，默认 "SP"。
        labels: 每个结果文件的标签，默认使用文件名。
        dependency: 依赖轴名称，默认 "freq"。
        csv_path: 可选，对比数据 CSV 输出路径。
        alignment: 对齐方式，"intersection"(交集) 或 "interpolation"(插值)。
        reference_index: interpolation 模式下的参考文件索引。
    """
    turbocharts_path = os.getenv(
        "TURBOCHARTS_PATH", r"C:\Program Files (x86)\EDI\turbocharts_app.exe"
    )
    if not Path(turbocharts_path).is_file():
        return {
            "success": False,
            "message": f"turbocharts_app.exe 不存在: {turbocharts_path}",
        }

    n = len(result_paths)
    if n < 2 or n > 8:
        return {"success": False, "message": "result_paths 需要 2-8 个文件"}

    for rp in result_paths:
        if not Path(rp).is_file():
            return {"success": False, "message": f"RAW 文件不存在: {rp}"}

    if labels is None:
        labels = [Path(rp).stem for rp in result_paths]
    if len(labels) != n:
        return {"success": False, "message": "labels 数量与 result_paths 不一致"}

    # Step 1: export each RAW to temp CSV
    csv_data: list[dict[str, list[float]]] = []
    with tempfile.TemporaryDirectory() as tmpdir:
        for i, rp in enumerate(result_paths):
            tmp_csv = os.path.join(tmpdir, f"tmp_{i}.csv")
            cmd = [
                turbocharts_path,
                "--raw", rp,
                "--csv", tmp_csv,
                "--type", chart_type,
                "--linename", curve,
            ]
            if dependency:
                cmd.extend(["--dependcy", dependency])
            try:
                subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            except subprocess.TimeoutExpired:
                return {"success": False, "message": f"turbocharts 导出 {rp} 超时"}

            data = _read_curve_csv(tmp_csv)
            if not data:
                return {"success": False, "message": f"无法解析 {rp} 的 CSV 数据"}
            csv_data.append(data)

    # Step 2: align data
    dep_key = dependency
    series: list[dict[str, Any]] = []

    if alignment == "intersection":
        ref_dep_list = csv_data[reference_index].get(dep_key, [])
        common_deps = sorted(
            p for p in ref_dep_list
            if all(p in d.get(dep_key, []) for d in csv_data)
        )
        for i, d in enumerate(csv_data):
            curve_vals = d.get(curve, [])
            dep_vals = d.get(dep_key, [])
            aligned_count = 0
            for p in common_deps:
                if p in dep_vals:
                    aligned_count += 1
            series.append({"label": labels[i], "points": aligned_count})
        aligned_x = common_deps
    else:
        ref = csv_data[reference_index]
        aligned_x = ref.get(dep_key, [])
        for i, d in enumerate(csv_data):
            series.append({"label": labels[i], "points": len(aligned_x)})

    # Step 3: compute metrics (first two series)
    metrics: dict[str, float] = {}
    if len(csv_data) >= 2 and aligned_x:
        c0_vals = csv_data[0].get(curve, [])
        c1_vals = csv_data[1].get(curve, [])
        dep0 = csv_data[0].get(dep_key, [])
        dep1 = csv_data[1].get(dep_key, [])
        common_pts = [(p, dep0.index(p), dep1.index(p))
                      for p in aligned_x if p in dep0 and p in dep1]
        diffs = [abs(c0_vals[j] - c1_vals[k]) for _, j, k in common_pts]
        if diffs:
            metrics["max_absolute_difference"] = round(max(diffs), 4)
            metrics["mean_absolute_difference"] = round(sum(diffs) / len(diffs), 4)

    # Step 4: generate comparison image
    all_linenames = "&".join([curve] * n)
    cmd = [
        turbocharts_path,
        "--raw", result_paths[0],
        "--img", img_path,
        "--type", chart_type,
        "--linename", all_linenames,
    ]
    if dependency:
        cmd.extend(["--dependcy", dependency])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return {"success": False, "message": "生成对比图超时"}

    img_ok = Path(img_path).exists()

    csv_ok = False
    if csv_path:
        with open(csv_path, "w") as f:
            headers = [dep_key] + [f"{labels[i]}_{curve}" for i in range(n)]
            f.write(",".join(headers) + "\n")
            for j, x in enumerate(aligned_x):
                row = [str(x)]
                for ci in range(n):
                    cdata = csv_data[ci]
                    dep_vals = cdata.get(dep_key, [])
                    curve_vals = cdata.get(curve, [])
                    if x in dep_vals:
                        idx = dep_vals.index(x)
                        row.append(str(curve_vals[idx]))
                    else:
                        row.append("")
                f.write(",".join(row) + "\n")
        csv_ok = Path(csv_path).exists()

    return {
        "success": img_ok,
        "return_code": result.returncode,
        "image_path": img_path,
        "csv_path": csv_path if csv_ok else "",
        "curve": curve,
        "series": series,
        "metrics": metrics,
    }


def _read_curve_csv(path: str) -> dict[str, list[float]]:
    """Read a turbocharts CSV and return column dict."""
    try:
        with open(path) as f:
            lines = f.readlines()
    except OSError:
        return {}
    if len(lines) < 2:
        return {}
    headers = lines[0].strip().split(",")
    data: dict[str, list[float]] = {h.strip(): [] for h in headers}
    for line in lines[1:]:
        if not line.strip():
            continue
        vals = line.strip().split(",")
        for i, h in enumerate(headers):
            try:
                data[h.strip()].append(float(vals[i]))
            except (ValueError, IndexError):
                pass
    return data
