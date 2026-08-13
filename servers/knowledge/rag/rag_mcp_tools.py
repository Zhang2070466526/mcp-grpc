"""知识库 MCP 工具 — search / ask / add / list。

由 __init__.py 导入触发（这些工具不注册为 MCP 工具，仅 Chat 内部注入）。
单例由 __init__.py 创建并通过 setter 注入。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from servers.knowledge.knowledge_base_service import KnowledgeBaseService

# 由 __init__.py 注入的知识库单例
_kb: KnowledgeBaseService | None = None


def set_knowledge_base(kb: KnowledgeBaseService) -> None:
    """接收 __init__.py 创建的知识库单例，注入到 MCP 工具层。"""
    global _kb
    _kb = kb


def search_knowledge(query: str, top_k: int = 5) -> dict[str, Any]:
    """语义检索知识库，返回最相关的文档片段。

    Args:
        query: 查询文本（自然语言）。
        top_k: 返回结果数量，默认 5。
    """
    # 查询不能为空
    if not query or not query.strip():
        return {"success": False, "error_code": "INVALID_PARAMETERS",
                "message": "query 不能为空"}
    # top_k 限制在 1~20 之间
    top_k = max(1, min(top_k, 20))
    # 调知识库语义检索
    results = _kb.search(query.strip(), top_k=top_k)
    # 组装返回：content（片段正文）、source（来源）、score（相似度，保留 4 位小数）
    return {
        "success": True,
        "query": query,
        "count": len(results),
        "results": [
            {"content": r["content"], "source": r["metadata"]["source"],
             "score": round(r["score"], 4)}
            for r in results
        ],
    }


def add_knowledge(content: str = "", file_path: str = "", source_name: str = "") -> dict[str, Any]:
    """向知识库追加文档（支持文本或文件路径）。

    content 和 file_path 二选一即可；都提供时优先使用 content。

    Args:
        content: 要入库的文本内容。
        file_path: 要入库的文件路径（支持 txt/md 等）。
        source_name: 文档来源标识（用于检索结果溯源）。
    """
    # 优先用 content（直接文本入库）
    if content and content.strip():
        name = source_name or "inline_text"
        return _kb.upload_by_str(content.strip(), name)
    # 其次用 file_path（读文件内容入库）
    elif file_path and file_path.strip():
        # 规范化路径并校验文件存在
        fp = Path(file_path).expanduser().resolve()
        if not fp.is_file():
            return {"success": False, "error_code": "FILE_NOT_FOUND",
                    "message": f"文件不存在: {fp}"}
        try:
            # 按 UTF-8 读取文件内容
            data = fp.read_text(encoding="utf-8")
        except Exception as e:
            return {"success": False, "error_code": "READ_ERROR",
                    "message": f"读取文件失败: {e}"}
        # 用 source_name 或文件名作为来源
        name = source_name or fp.name
        return _kb.upload_by_str(data, name)
    # 都没提供则报错
    else:
        return {"success": False, "error_code": "INVALID_PARAMETERS",
                "message": "请提供 content 或 file_path"}


def list_knowledge_sources() -> dict[str, Any]:
    """列出知识库中已入库的文档来源和分块总数。"""
    sources = _kb.list_sources()
    return {
        "success": True,
        "total_chunks": _kb.count(),       # 总分块数
        "source_count": len(sources),      # 文档来源数量
        "sources": sources,                # 来源列表
    }


# RAG 服务单例（由 __init__.py 注入）
_rag = None


def set_rag_service(rag) -> None:
    """接收 __init__.py 创建的 RagService 单例，注入到 MCP 工具层。"""
    global _rag
    _rag = rag


def ask_knowledge(query: str) -> dict[str, Any]:
    """基于知识库内容生成回答（检索 + LLM 生成）。

    Args:
        query: 自然语言问题。
    """
    # RAG 服务未初始化（LLM 未配置）时报错
    if not _rag:
        return {"success": False, "error_code": "RAG_NOT_AVAILABLE",
                "message": "RAG 服务未初始化，请检查 LLM 配置"}
    if not query or not query.strip():
        return {"success": False, "error_code": "INVALID_PARAMETERS",
                "message": "query 不能为空"}
    try:
        # 调用 RAG 链生成回答
        answer = _rag.chain.invoke(query.strip())
        return {"success": True, "query": query, "answer": answer}
    except Exception as e:
        return {"success": False, "error_code": "RAG_ERROR",
                "message": f"生成回答失败: {e}"}
