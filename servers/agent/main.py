r"""Agent 启动入口。

启动本地 Agent，主动连接公共服务（或本地测试模式），
领取任务、调用本机 EDA/工具、上报结果。

用法：
    uv run python -m servers.agent.main
    uv run python -m servers.agent.main --mode local
"""

from __future__ import annotations

import argparse
import time

from dotenv import load_dotenv

load_dotenv()


def run_local() -> None:
    """本地测试模式 — 交互式提交任务。"""
    from servers.agent.client import client
    from servers.agent.operation_registry import list_operations

    ops = list_operations()
    print(f"Agent 本地测试模式 — 已注册 {len(ops)} 个操作:")
    for op in sorted(ops):
        print(f"  {op}")
    print()

    # 交互测试：逐个提交任务
    tests = [
        ("list_epp_projects", {"folder_path": "C:/Users/JGL/EDI-Workspace"}),
        ("get_project_summary", {"project_path": "C:/Users/JGL/EDI-Workspace/EDI_TEST/EDI_TEST.epp"}),
        ("list_project_components", {"project_path": "C:/Users/JGL/EDI-Workspace/EDI_TEST/EDI_TEST.epp"}),
    ]

    for op, params in tests:
        print(f"\n>>> {op}({params})")
        job_id = client.submit_job(op, params)
        print(f"    job_id = {job_id}")

        # 等待完成
        for _ in range(60):
            status = client.get_status(job_id)
            if status["status"] in ("SUCCEEDED", "FAILED", "CANCELLED"):
                break
            time.sleep(1)

        result = client.get_result(job_id)
        if result:
            if result["status"] == "SUCCEEDED":
                r = result["result"]
                if isinstance(r, dict) and "count" in r:
                    print(f"    OK: {r.get('count', '?')} .epp projects found")
                elif isinstance(r, dict) and "components" in r:
                    comps = r["components"]
                    cnt = comps.get("total") if isinstance(comps, dict) else len(comps)
                    print(f"    OK: {cnt} components")
                elif isinstance(r, dict) and "project" in r:
                    print(f"    OK: project '{r['project'].get('name', '?')}'")
                else:
                    print(f"    OK: {list(r.keys())[:3] if isinstance(r, dict) else str(r)[:100]}")
            else:
                print(f"    FAILED: {result.get('error', '?')[:200]}")

    print("\n全部测试完成")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EDA MCP Agent")
    parser.add_argument("--mode", choices=["local", "remote"], default="remote")
    args = parser.parse_args()

    if args.mode == "remote":
        print("远程模式尚未实现。使用 --mode local 进入本地测试模式。")
        import sys
        sys.exit(1)
    else:
        run_local()
