"""
知识库业务层 — 文本分块、MD5 去重、上传/检索。

依赖 VectorStoreService 做底层存储，本层只处理业务逻辑（分块、去重）。
"""
import os
from typing import List, Dict

from langchain_text_splitters import RecursiveCharacterTextSplitter

import servers.knowledge.config as config
from servers.knowledge.vector_store_service import VectorStoreService
from servers.knowledge.md5_utils import get_string_md5, check_md5, save_md5


class KnowledgeBaseService:
    """知识库业务服务 — 分块、去重、写入。"""

    def __init__(self):
        """初始化向量存储和文本分块器。"""
        # 底层向量存储（纯存储操作）
        self.vector_store_service = VectorStoreService()
        # 文本分块器：按配置的块大小、重叠、分隔符分割文本
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=config.chunk_size,        # 每块最大字符数
            chunk_overlap=config.chunk_overlap,  # 相邻块重叠字符数
            separators=config.separators,        # 分隔符优先级列表
            length_function=len,                 # 长度按字符数计算
        )

    # ── 上传 ──

    def upload_by_str(self, data: str, filename: str) -> Dict:
        """文本分块 → MD5 去重 → 写入向量库。"""
        # 计算内容 MD5，用于去重（相同内容不重复入库）
        content_md5 = get_string_md5(data)
        if check_md5(content_md5):
            # 该内容已处理过，跳过
            return {"success": False, "message": f'文件 "{filename}" 已存在，跳过'}

        # 分割文本为分块
        chunks = self.splitter.split_text(data)
        if not chunks:
            return {"success": False, "message": f'文件 "{filename}" 分割后为空'}

        # 生成分块 id（"{文件名}_{序号}"）和元数据（source 溯源、chunk_index 排序）
        ids = [f"{filename}_{i}" for i in range(len(chunks))]
        metadatas = [
            {"source": filename, "chunk_index": i, "total_chunks": len(chunks)}
            for i in range(len(chunks))
        ]

        try:
            # 写入向量库
            self.vector_store_service.add(chunks, ids, metadatas)
            # 记录 MD5，防止下次重复入库
            save_md5(content_md5)
            return {"success": True, "chunks_count": len(chunks),
                    "message": f'✅ 文件 "{filename}" 上传成功，{len(chunks)} 个分块'}
        except Exception as e:
            return {"success": False, "message": f"上传失败: {e}"}

    def upload_by_file(self, file_path: str) -> Dict:
        """从文件读取内容并上传。"""
        # 校验文件存在
        if not os.path.exists(file_path):
            return {"success": False, "message": f"文件不存在: {file_path}"}
        try:
            # 按 UTF-8 读取文件内容
            with open(file_path, "r", encoding="utf-8") as f:
                data = f.read()
        except Exception as e:
            return {"success": False, "message": f"读取失败: {e}"}
        # 用文件名作为 source 上传
        return self.upload_by_str(data, os.path.basename(file_path))

    # ── 检索（委托给向量存储层）──

    def search(self, query: str, top_k: int = 5) -> List[Dict]:
        """语义检索，返回 {content, metadata, score} 列表。"""
        # 直接委托给底层存储层的 search
        return self.vector_store_service.search(query, top_k)

    def get_retriever(self):
        """返回 LangChain 检索器，供 RagService 构建 RAG 链使用。"""
        return self.vector_store_service.get_retriever()

    # ── 管理 ──

    def count(self) -> int:
        """知识库中已入库的分块总数。"""
        return self.vector_store_service.count()

    def list_sources(self) -> List[str]:
        """列出所有已入库的文档来源名称。"""
        return self.vector_store_service.list_sources()

    def delete_by_filename(self, filename: str) -> bool:
        """按文件名删除对应的所有分块。"""
        return self.vector_store_service.delete_by_prefix(filename) > 0

    def clear_all(self) -> None:
        """清空整个知识库的所有数据。"""
        self.vector_store_service.clear()
