"""测试聊天服务 — 参数校验、会话隔离、循环保护、工具白名单。"""
import sys, time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestParameterValidation:
    """参数校验测试。"""

    def test_list_epp_projects_rejects_empty_folder(self):
        from servers.eda.project_manage import list_epp_projects
        try:
            list_epp_projects("")
            assert False, "should raise"
        except ValueError as e:
            assert "不能为空" in str(e)

    def test_list_epp_projects_rejects_whitespace_folder(self):
        from servers.eda.project_manage import list_epp_projects
        try:
            list_epp_projects("   ")
            assert False, "should raise"
        except ValueError as e:
            assert "不能为空" in str(e)

    def test_list_epp_projects_rejects_nonexistent_folder(self):
        from servers.eda.project_manage import list_epp_projects
        try:
            list_epp_projects("C:/__nonexistent_folder_12345__")
            assert False, "should raise"
        except FileNotFoundError:
            pass


class TestSessionIsolation:
    """会话隔离测试。"""

    def test_different_sessions_have_separate_context(self):
        from servers.chat.service import ChatService
        svc = ChatService.instance()
        s1 = svc._get_or_create("session-a")
        s2 = svc._get_or_create("session-b")
        s1.current_project_path = "C:/a.epp"
        s2.current_project_path = "C:/b.epp"
        assert s1.current_project_path != s2.current_project_path

    def test_reopen_same_session_keeps_context(self):
        from servers.chat.service import ChatService
        svc = ChatService.instance()
        s1 = svc._get_or_create("session-keep")
        s1.current_project_path = "C:/keep.epp"
        s2 = svc._get_or_create("session-keep")
        assert s2.current_project_path == "C:/keep.epp"

    def test_open_close_clears_project(self):
        from servers.chat.service import ChatService
        svc = ChatService.instance()
        s = svc._get_or_create("session-close")
        s.current_project_path = "C:/proj.epp"
        s.current_project_name = "proj"
        # close clears
        svc._update_context(s, "close_edi_project",
                            {"project_path": "C:/proj.epp"},
                            {"success": True})
        assert s.current_project_path is None
        assert s.current_project_name is None


class TestToolWhitelist:
    """工具白名单测试。"""

    def test_simulate_project_not_in_chat(self):
        from servers.chat.service import CHAT_TOOL_MAP
        assert "simulate_project" not in CHAT_TOOL_MAP, \
            "同步仿真不应出现在聊天工具中"

    def test_async_simulation_in_chat(self):
        from servers.chat.service import CHAT_TOOL_MAP
        assert "start_simulation_async" in CHAT_TOOL_MAP
        assert "get_simulation_async_status" in CHAT_TOOL_MAP
        assert "get_simulation_async_result" in CHAT_TOOL_MAP

    def test_show_image_in_chat(self):
        from servers.chat.service import CHAT_TOOL_MAP
        assert "show_image" in CHAT_TOOL_MAP

    def test_tool_map_and_schema_count_match(self):
        from servers.chat.service import CHAT_TOOL_MAP, CHAT_TOOLS_SCHEMA
        assert len(CHAT_TOOL_MAP) == len(CHAT_TOOLS_SCHEMA), \
            f"map={len(CHAT_TOOL_MAP)}, schema={len(CHAT_TOOLS_SCHEMA)}"


class TestDuplicateProtection:
    """重复调用保护测试。"""

    def test_same_fingerprint_detected(self):
        import json
        a1 = {"project_path": "C:/a.epp", "timeout_seconds": 60}
        a2 = {"timeout_seconds": 60, "project_path": "C:/a.epp"}
        fp1 = f"open_edi_project:{json.dumps(a1, sort_keys=True, ensure_ascii=False)}"
        fp2 = f"open_edi_project:{json.dumps(a2, sort_keys=True, ensure_ascii=False)}"
        assert fp1 == fp2, "参数顺序不应影响指纹"


class TestContextUpdate:
    """上下文更新测试。"""

    def test_list_epp_projects_updates_last_projects(self):
        from servers.chat.service import ChatService
        svc = ChatService.instance()
        s = svc._get_or_create("session-ctx-list")
        svc._update_context(s, "list_epp_projects",
                            {"folder_path": "C:/proj"},
                            {"success": True, "projects": [{"name": "a", "path": "C:/a.epp"}]})
        assert s.last_folder_path == "C:/proj"
        assert len(s.last_projects) == 1

    def test_start_simulation_saves_task_id(self):
        from servers.chat.service import ChatService
        svc = ChatService.instance()
        s = svc._get_or_create("session-ctx-sim")
        svc._update_context(s, "start_simulation_async",
                            {"project_path": "C:/p.epp"},
                            {"success": True, "task_id": "task-123"})
        assert s.last_simulation_task_id == "task-123"

    def test_no_current_project_prevents_simulation(self):
        from servers.chat.service import ChatService
        svc = ChatService.instance()
        s = svc._get_or_create("session-no-proj")
        s.current_project_path = None
        ok, result = svc._validate("start_simulation_async", {}, s)
        assert not ok
        assert result.get("error", {}).get("code") == "NO_CURRENT_PROJECT"


class TestSessionPrune:
    """会话清理测试。"""

    def test_expired_sessions_cleaned(self):
        from servers.chat.service import ChatService
        svc = ChatService.instance()
        s = svc._get_or_create("session-old")
        s.updated_at = 0  # force expired
        svc._last_prune = 0
        svc._prune()
        s2 = svc._get_or_create("session-old")
        assert s2.updated_at > 0  # new session created


class TestRepeatDetection:
    """Bug 修复：重复调用仅限本轮。"""

    def test_same_round_blocks(self):
        from servers.chat.service import _is_duplicate_tool_call
        called: set[str] = set()
        args = {"project_path": "/p.epp"}
        assert not _is_duplicate_tool_call(called, "open_edi_project", args)
        assert _is_duplicate_tool_call(called, "open_edi_project", args)

    def test_next_round_allows(self):
        from servers.chat.service import _is_duplicate_tool_call
        called1: set[str] = set()
        called2: set[str] = set()
        args = {"task_id": "t1"}
        assert not _is_duplicate_tool_call(called1, "get_simulation_async_status", args)
        assert not _is_duplicate_tool_call(called2, "get_simulation_async_status", args)


class TestMessageTrim:
    """Bug 修复：按 user 消息边界裁剪，调用实际生产代码。"""

    def test_trim_starts_at_user(self, monkeypatch):
        import servers.chat.service as svc_module
        from servers.chat.service import ChatService, ChatSession

        monkeypatch.setattr(svc_module, "_MAX_MESSAGES", 2)

        session = ChatSession(session_id="trim-test-1")
        session.messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "q1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "q2"},
            {"role": "assistant", "content": "a2"},
        ]

        svc = ChatService.instance()
        svc._trim_messages(session)

        assert session.messages[0]["role"] == "system"
        assert session.messages[1]["role"] == "user"
        assert "q2" in session.messages[1]["content"]

    def test_system_preserved(self, monkeypatch):
        import servers.chat.service as svc_module
        from servers.chat.service import ChatService, ChatSession

        monkeypatch.setattr(svc_module, "_MAX_MESSAGES", 2)

        session = ChatSession(session_id="trim-test-2")
        session.messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "q"},
            {"role": "assistant", "content": "a"},
        ]

        svc = ChatService.instance()
        svc._trim_messages(session)

        assert session.messages[0]["role"] == "system"



class TestShowImage:
    """show_image — 纯 ImageContent，不复制文件。"""

    def test_returns_imagecontent(self, tmp_path):
        from PIL import Image
        img = Image.new("RGB", (10, 10), color="red")
        src = tmp_path / "test.png"
        img.save(str(src))
        from servers.image_tools import show_image
        result = show_image(str(src))
        assert len(result) == 2
        assert getattr(result[1], "type") == "image"

    def test_no_workspace_needed(self, tmp_path, monkeypatch):
        monkeypatch.delenv("OPENCLAW_WORKSPACE", raising=False)
        from PIL import Image
        img = Image.new("RGB", (10, 10), color="red")
        src = tmp_path / "img.png"
        img.save(str(src))
        from servers.image_tools import show_image
        result = show_image(str(src))
        assert len(result) == 2

    def test_rejects_invalid_extension(self, tmp_path):
        from servers.image_tools import show_image
        txt = tmp_path / "t.txt"
        txt.write_text("x")
        try:
            show_image(str(txt))
            assert False
        except ValueError:
            pass

    def test_oversized_text_only(self, tmp_path, monkeypatch):
        import servers.image_tools as it
        monkeypatch.setattr(it, "_MAX_NATIVE_IMAGE_SIZE", 10)
        big = tmp_path / "big.png"
        big.write_bytes(b"\x00" * 100)
        result = it.show_image(str(big))
        assert len(result) == 1



class TestCopyToWorkspace:
    """copy_image_to_workspace 测试。"""

    def test_with_workspace(self, tmp_path, monkeypatch):
        from servers import image_tools as it
        ws = tmp_path / "ws"; ws.mkdir()
        monkeypatch.setattr(it, "OPENCLAW_WORKSPACE_PATH", ws)
        from PIL import Image
        img = Image.new("RGB", (10, 10), color="red")
        src = tmp_path / "img.png"; img.save(str(src))
        r = it.copy_image_to_workspace(str(src))
        assert r["copied"] and "mcp-cache" in r["image_path"].replace("\\", "/")

    def test_no_workspace_copied_false(self, tmp_path, monkeypatch):
        from servers import image_tools as it
        monkeypatch.setattr(it, "OPENCLAW_WORKSPACE_PATH", None)
        from PIL import Image
        img = Image.new("RGB", (10, 10), color="red")
        src = tmp_path / "img.png"; img.save(str(src))
        r = it.copy_image_to_workspace(str(src))
        assert r["success"] and not r["copied"]

    def test_same_source_overwrites(self, tmp_path, monkeypatch):
        from servers import image_tools as it
        ws = tmp_path / "ws"; ws.mkdir()
        monkeypatch.setattr(it, "OPENCLAW_WORKSPACE_PATH", ws)
        from PIL import Image
        img = Image.new("RGB", (10, 10), color="red")
        src = tmp_path / "img.png"; img.save(str(src))
        r1 = it.copy_image_to_workspace(str(src))
        r2 = it.copy_image_to_workspace(str(src))
        assert r1["image_path"] == r2["image_path"]

    def test_different_dirs_no_conflict(self, tmp_path, monkeypatch):
        from servers import image_tools as it
        ws = tmp_path / "ws"; ws.mkdir()
        monkeypatch.setattr(it, "OPENCLAW_WORKSPACE_PATH", ws)
        d1 = tmp_path / "d1"; d1.mkdir()
        d2 = tmp_path / "d2"; d2.mkdir()
        from PIL import Image
        img = Image.new("RGB", (10, 10), color="red")
        s1 = d1 / "img.png"; img.save(str(s1))
        s2 = d2 / "img.png"; img.save(str(s2))
        r1 = it.copy_image_to_workspace(str(s1))
        r2 = it.copy_image_to_workspace(str(s2))
        assert r1["image_path"] != r2["image_path"]


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v", "-p", "no:cacheprovider"])
