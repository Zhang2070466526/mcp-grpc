"""节点注册和设备令牌管理。"""

from __future__ import annotations

import json
import os
import secrets
import socket
import uuid
from pathlib import Path

TOKEN_FILE = Path(__file__).resolve().parent.parent.parent / ".agent_token"


def get_or_create_node() -> dict[str, str]:
    """返回 node_id / node_token / device_name，首次自动生成并持久化。"""
    if TOKEN_FILE.exists():
        return json.loads(TOKEN_FILE.read_text(encoding="utf-8"))

    node = {
        "node_id": f"node-{secrets.token_hex(3)}",
        "device_name": socket.gethostname(),
        "node_token": f"nt-{uuid.uuid4().hex}",
    }
    TOKEN_FILE.write_text(json.dumps(node, indent=2), encoding="utf-8")
    return node


def get_node_id() -> str:
    return get_or_create_node()["node_id"]


def get_node_token() -> str:
    return get_or_create_node()["node_token"]
