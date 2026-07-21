"""仿真结果对比工具。

compare_simulation_results  多个 RAW 仿真结果同一条曲线对比叠图
"""

from __future__ import annotations

import math
import os
import tempfile
from pathlib import Path
from typing import Any

from servers.turbocharts.runner import run_turbocharts


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

    逐 RAW 调用 turbocharts 导出 CSV 后，读取真实列名，
    按依赖轴对齐，用 Matplotlib 生成叠图并计算差异指标。

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

    # Step 1: export each RAW to temp CSV (serialized via runner)
    dep_key = dependency
    raw_curves: list[tuple[list[float], list[float]]] = []

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

            result_proc = run_turbocharts(cmd, timeout_seconds=60)
            if result_proc.returncode != 0:
                return {
                    "success": False,
                    "message": f"turbocharts 导出 {rp} 失败: {result_proc.stderr[:200]}",
                }

            x_vals, y_vals = _read_curve_csv_xy(tmp_csv)
            if not x_vals:
                return {"success": False, "message": f"无法解析 {rp} 的 CSV 数据"}
            raw_curves.append((x_vals, y_vals))

    # Step 2: align data (preserve original index order)
    curves_aligned: list[list[float] | None] = [None] * n
    common_x: list[float] = []

    if alignment == "intersection":
        x_sets = [set(xv) for xv, _ in raw_curves]
        common_x = sorted(x_sets[reference_index] & set.intersection(*x_sets))
        if not common_x:
            return {"success": False, "message": "所有 RAW 文件没有共同的依赖轴数据点"}
        for i, (xv, yv) in enumerate(raw_curves):
            x_to_y = dict(zip(xv, yv))
            curves_aligned[i] = [x_to_y.get(p, 0.0) for p in common_x]
    else:
        # interpolation
        import numpy as np
        ref_x, ref_y = raw_curves[reference_index]
        common_x = ref_x
        curves_aligned[reference_index] = ref_y
        for i, (xv, yv) in enumerate(raw_curves):
            if i == reference_index:
                continue
            interp_y = np.interp(ref_x, xv, yv)
            curves_aligned[i] = interp_y.tolist()

    aligned = [c for c in curves_aligned if c is not None]
    series = [
        {"label": labels[i], "points": len(aligned[i])}
        for i in range(n)
    ]

    # Step 3: compute metrics (each vs reference)
    metrics = []
    ref_curve = aligned[reference_index]
    for i in range(n):
        if i == reference_index:
            continue
        diffs = [
            abs(ref_curve[j] - aligned[i][j])
            for j in range(len(common_x))
        ]
        if diffs:
            metrics.append({
                "label": labels[i],
                "reference": labels[reference_index],
                "max_absolute_difference": round(max(diffs), 4),
                "mean_absolute_difference": round(sum(diffs) / len(diffs), 4),
                "rms_difference": round(math.sqrt(sum(d * d for d in diffs) / len(diffs)), 4),
            })

    # Step 4: generate comparison image with Matplotlib
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 6))
    for i, yv in enumerate(aligned):
        ax.plot(common_x, yv, label=labels[i], linewidth=1.5)
    ax.set_xlabel(dependency)
    ax.set_ylabel(curve)
    ax.set_title(f"Comparison: {curve}")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(img_path, dpi=150)
    plt.close(fig)
    img_ok = Path(img_path).exists()

    # Step 5: write comparison CSV
    csv_ok = False
    if csv_path:
        with open(csv_path, "w", encoding="utf-8") as f:
            headers = [dep_key] + [f"{labels[i]}_{curve}" for i in range(n)]
            f.write(",".join(headers) + "\n")
            for j, x in enumerate(common_x):
                row = [str(x)] + [str(aligned[i][j]) for i in range(n)]
                f.write(",".join(row) + "\n")
        csv_ok = Path(csv_path).exists()

    return {
        "success": img_ok,
        "image_path": img_path,
        "csv_path": csv_path if csv_ok else "",
        "curve": curve,
        "alignment": alignment,
        "series": series,
        "metrics": metrics,
    }


def _read_curve_csv_xy(path: str) -> tuple[list[float], list[float]]:
    """Read turbocharts CSV — returns (x_values, y_values) from first two columns."""
    try:
        with open(path) as f:
            lines = f.readlines()
    except OSError:
        return [], []
    if len(lines) < 2:
        return [], []
    headers = lines[0].strip().split(",")
    if len(headers) < 2:
        return [], []
    x_vals: list[float] = []
    y_vals: list[float] = []
    for line in lines[1:]:
        if not line.strip():
            continue
        vals = line.strip().split(",")
        if len(vals) < 2:
            continue
        try:
            x_vals.append(float(vals[0]))
            y_vals.append(float(vals[1]))
        except ValueError:
            continue
    return x_vals, y_vals
