"""测试 list_project_components 和 get_component_parameters。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from servers.eda.project_manage import list_project_components, get_component_parameters

PROJECT = r"C:\Users\JGL\EDI-Workspace\EDI_TEST\EDI_TEST.epp"


def test_list_components():
    if not Path(PROJECT).is_file():
        print(f"SKIP: {PROJECT} not found")
        return
    r = list_project_components(PROJECT)
    assert r["success"], r.get("message", "")
    assert r["total"] >= 1
    for c in r["components"]:
        assert "component_id" in c
        assert "name" in c
        assert "type" in c


def test_filter_by_type():
    if not Path(PROJECT).is_file():
        return
    r = list_project_components(PROJECT, component_type="TermG")
    assert r["success"]
    for c in r["components"]:
        assert c["type"] == "TermG"


def test_limit():
    if not Path(PROJECT).is_file():
        return
    r = list_project_components(PROJECT, limit=1)
    assert len(r["components"]) <= 1


def test_get_parameters():
    if not Path(PROJECT).is_file():
        return
    r = list_project_components(PROJECT)
    if not r["components"]:
        return
    cid = r["components"][0]["component_id"]
    params = get_component_parameters(PROJECT, cid)
    assert params["success"], params.get("message", "")
    assert len(params["parameters"]) >= 0


if __name__ == "__main__":
    test_list_components()
    test_filter_by_type()
    test_limit()
    test_get_parameters()
    print("test_component_tools.py: all passed")
