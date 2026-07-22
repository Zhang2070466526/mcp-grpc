"""测试工具注册完整性。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_all_tools_registered():
    from start_servers import mcp
    tools = list(mcp._tool_manager._tools.keys())
    assert len(tools) == 17, f"expected 17 tools, got {len(tools)}"
    required = [
        "list_epp_projects", "open_eda_project", "close_eda_project",
        "list_project_components", "get_component_parameters", "get_project_summary",
        "simulate_project", "simulate_netlist_with_ads", "compare_simulation_results",
        "export_project_netlist", "capture_schematic",
        "replace_models_from_csv", "launch_edi", "turbocharts_convert",
    ]
    for name in required:
        assert name in tools, f"missing tool: {name}"


def test_grpc_timeout_limits():
    from servers.eda.grpc_client import call_grpc
    try:
        call_grpc(1, {}, 99999, max_timeout_seconds=300)
        assert False
    except ValueError:
        pass


def test_single_instance_check():
    import socket
    s = socket.socket()
    try:
        result = s.connect_ex(("127.0.0.1", 19998))
        assert result != 0  # should not be listening
    finally:
        s.close()


if __name__ == "__main__":
    test_all_tools_registered()
    test_grpc_timeout_limits()
    test_single_instance_check()
    print("test_tool_registry.py: all passed")
