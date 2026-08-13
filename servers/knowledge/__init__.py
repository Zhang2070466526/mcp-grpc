"""知识库模块 — 基于 ChromaDB + DashScope 嵌入的完整 RAG 系统。

MCP 工具：
  search_knowledge         语义检索（返回原文片段）
  ask_knowledge            检索 + LLM 生成回答
  add_knowledge            追加文档到知识库
  list_knowledge_sources   列出已入库文档来源
"""

from servers.knowledge.knowledge_base_service import KnowledgeBaseService
from servers.knowledge.rag.rag_mcp_tools import set_knowledge_base, set_rag_service
from servers.knowledge.rag.rag_chain import RagService

# 创建知识库服务单例，注入到 MCP 工具层
_knowledge_base = KnowledgeBaseService()
set_knowledge_base(_knowledge_base)

# 创建 RAG 服务单例，注入到 MCP 工具层
_rag_service = RagService()
set_rag_service(_rag_service)

# RAG 工具通过 Chat 内部注入，不注册为 MCP 工具
# import servers.knowledge.rag.rag_mcp_tools  # noqa: F401
