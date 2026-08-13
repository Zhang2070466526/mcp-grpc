"""
向量存储层 — 封装 ChromaDB 的底层操作。

职责：连接、写入、检索、删除。不包含分块、去重等业务逻辑。
业务逻辑（分块、MD5 去重）在 knowledge_base_service.py。
"""
import logging
import os
from typing import List, Dict

from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import DashScopeEmbeddings

import servers.knowledge.config as config

logger = logging.getLogger(__name__)


class VectorStoreService:
    """ChromaDB 向量存储 — 纯存储操作，无业务逻辑。"""

    def __init__(self):
        """初始化 ChromaDB 向量存储（DashScope 嵌入 + 本地持久化）。"""
        # 确保持久化目录存在（ChromaDB 需要目录已创建）
        os.makedirs(config.persist_directory, exist_ok=True)
        # 初始化 ChromaDB 客户端
        self.chroma = Chroma(
            collection_name=config.collection_name,          # 集合名（区分不同知识库）
            embedding_function=DashScopeEmbeddings(          # 嵌入函数（文本→向量）
                model="text-embedding-v4",                    # DashScope 嵌入模型
                dashscope_api_key=config.DASHSCOPE_API_KEY,   # 嵌入 API Key
            ),
            persist_directory=config.persist_directory,      # 持久化目录
        )

    # ── 写入 ──

    def add(self, texts: List[str], ids: List[str], metadatas: List[dict]) -> None:
        """写入分块文本到向量数据库。"""
        # 写入文本（ChromaDB 内部会调嵌入函数转成向量再存）
        self.chroma.add_texts(texts=texts, ids=ids, metadatas=metadatas)
        # 持久化到磁盘（ChromaDB 默认惰性写入，需手动 persist）
        self.chroma.persist()

    # ── 检索 ──

    def search(self, query: str, top_k: int = 5) -> List[Dict]:
        """语义检索，返回 {content, metadata, score} 列表。"""
        try:
            # 相似度检索：返回 top_k 个最相似文档及相似度分数
            results = self.chroma.similarity_search_with_score(query, k=top_k)
            # 组装成 {content, metadata, score} 结构返回
            return [
                {"content": doc.page_content, "metadata": doc.metadata, "score": score}
                for doc, score in results
            ]
        except Exception as e:
            logger.error("检索失败: %s", e)
            return []

    def get_retriever(self):
        """返回 LangChain 检索器，用于 RAG chain。"""
        # 转成 LangChain retriever 对象，供 RAG 链的 context 分支使用
        return self.chroma.as_retriever(search_kwargs={"k": config.similarity_threshold})

    # ── 管理 ──

    def count(self) -> int:
        """返回已入库的分块总数，异常时返回 0。"""
        try:
            # 直接读 ChromaDB 底层集合数量（_collection 是内部 API）
            return self.chroma._collection.count()
        except Exception:
            return 0

    def list_sources(self) -> List[str]:
        """列出所有已入库的文档来源。"""
        try:
            # 取出集合中全部数据（含 metadatas）
            all_data = self.chroma.get()
            # 从元数据里提取 source 字段，去重排序后返回
            if all_data and "metadatas" in all_data and all_data["metadatas"]:
                return sorted(set(
                    m["source"] for m in all_data["metadatas"]
                    if m and "source" in m
                ))
        except Exception:
            pass
        return []

    def delete_by_prefix(self, filename: str) -> int:
        """删除指定文件名前缀的所有分块，返回删除数量。"""
        try:
            # 取所有分块 id
            all_ids = self.chroma.get()["ids"]
            # 找出以 "{filename}_" 为前缀的分块（分块 id 格式见 knowledge_base_service）
            targets = [i for i in all_ids if i.startswith(f"{filename}_")]
            if targets:
                # 批量删除并持久化
                self.chroma.delete(ids=targets)
                self.chroma.persist()
            return len(targets)
        except Exception as e:
            logger.error("删除失败: %s", e)
            return 0

    def clear(self) -> None:
        """清空所有数据。"""
        try:
            # 取所有分块 id
            all_ids = self.chroma.get().get("ids", [])
            if all_ids:
                # 批量删除全部并持久化
                self.chroma.delete(ids=all_ids)
                self.chroma.persist()
                logger.info("已清空 %d 个分块", len(all_ids))
        except Exception as e:
            logger.error("清空失败: %s", e)
