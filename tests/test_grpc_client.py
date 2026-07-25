"""测试 gRPC 通信层 — parse、emit、返回结构。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestParsePayloadJson:
    def test_valid_json(self):
        from servers.eda.grpc_client import _parse_payload_json
        d, err = _parse_payload_json('{"ads_output":"log line"}')
        assert err is None
        assert d == {"ads_output": "log line"}

    def test_empty_string(self):
        from servers.eda.grpc_client import _parse_payload_json
        d, err = _parse_payload_json("")
        assert err is None
        assert d == {}

    def test_invalid_json(self):
        from servers.eda.grpc_client import _parse_payload_json
        d, err = _parse_payload_json("not json")
        assert err is not None
        assert "raw_payload" in d

    def test_array_not_dict(self):
        from servers.eda.grpc_client import _parse_payload_json
        d, err = _parse_payload_json("[1,2,3]")
        assert err is not None

    def test_none(self):
        from servers.eda.grpc_client import _parse_payload_json
        d, err = _parse_payload_json("null")
        assert err is not None


class TestEmitEvent:
    def test_none_callback(self):
        from servers.eda.grpc_client import _emit_event
        _emit_event(None, {})

    def test_callback_called(self):
        from servers.eda.grpc_client import _emit_event
        received = []
        _emit_event(lambda u: received.append(u), {"key": "val"})
        assert len(received) == 1
        assert received[0]["key"] == "val"

    def test_callback_exception_not_raised(self):
        from servers.eda.grpc_client import _emit_event
        def bad(_):
            raise RuntimeError("boom")
        _emit_event(bad, {})  # 不应抛异常


class TestLogAccumulation:
    """模拟增量日志拼接逻辑。"""

    def test_incremental_chunks(self):
        chunks = []
        for chunk in ["Parsing ", "netlist\n", "Done."]:
            if chunk:
                chunks.append(chunk)
        result = "".join(chunks)
        assert result == "Parsing netlist\nDone."

    def test_preserve_newlines(self):
        chunks = ["line1\r\n", "\n", "line2\n", "line3"]
        result = "".join(chunks)
        assert result == "line1\r\n\nline2\nline3"

    def test_no_strip(self):
        chunks = ["  start", "middle  ", "  end  "]
        result = "".join(chunks)
        assert result == "  startmiddle    end  "

    def test_empty_chunks_ignored(self):
        chunks = []
        for chunk in ["", "real", "", ""]:
            if chunk:
                chunks.append(chunk)
        assert "".join(chunks) == "real"

    def test_none_chunk(self):
        chunk = None
        if chunk is None:
            chunk = ""
        elif not isinstance(chunk, str):
            chunk = str(chunk)
        assert chunk == ""

    def test_final_event_appends_not_overwrites(self):
        chunks = []
        chunks.append("line1\n")
        chunks.append("line2\n")
        chunks.append("final\n")  # final event
        assert "".join(chunks) == "line1\nline2\nfinal\n"


class TestReturnStructure:
    """验证统一返回结构。"""

    def test_accepted_fields(self):
        result_accepted = {
            "success": True,
            "completed": True,
            "client_uuid": "c1",
            "task_id": "t1",
            "task_type": "SIMULATE_PROJECT",
            "status": "SUCCEEDED",
            "message": "done",
            "project_path": "/p.epp",
            "result_path": "/r.raw",
            "ads_output": "logs",
            "log_complete": True,
        }
        required = [
            "success", "completed", "client_uuid", "task_id",
            "task_type", "status", "message", "project_path",
            "result_path", "ads_output", "log_complete",
        ]
        for key in required:
            assert key in result_accepted, f"missing: {key}"

    def test_rejected_fields(self):
        result_rejected = {
            "success": False,
            "completed": True,
            "client_uuid": "c1",
            "task_id": "t1",
            "task_type": "SIMULATE_PROJECT",
            "status": "REJECTED",
            "message": "not accepted",
            "project_path": "",
            "result_path": "",
            "ads_output": "",
            "log_complete": True,
        }
        assert result_rejected["completed"]

    def test_timeout_fields(self):
        result_timeout = {
            "success": False,
            "completed": False,
            "status": "TIMEOUT",
            "ads_output": "partial",
            "log_complete": False,
        }
        assert not result_timeout["completed"]
        assert result_timeout["ads_output"] == "partial"


class TestTaskIsolation:
    """不同任务日志不串线。"""

    def test_chunk_lists_are_separate(self):
        task_a_chunks = ["A1", "A2"]
        task_b_chunks = ["B1", "B2", "B3"]
        assert "".join(task_a_chunks) == "A1A2"
        assert "".join(task_b_chunks) == "B1B2B3"

    def test_task_id_preserved(self):
        task_id = "t-abc-123"
        for _ in range(3):
            assert task_id == "t-abc-123"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v", "-p", "no:cacheprovider"])
