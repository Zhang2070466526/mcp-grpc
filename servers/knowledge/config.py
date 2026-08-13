"""知识库配置 — 向量存储、文本分割、嵌入模型参数。

集中管理知识库模块的所有配置项，供向量存储层、业务层、RAG 链复用。
"""

import os
from servers.settings import get_settings

# 统一配置单例（复用主服务的 Settings）
_settings = get_settings()

# ── Chroma 向量数据库 ──
# 旧路径（保留记录）：原先把向量数据持久化在 data/chroma_db 子目录
# persist_directory = os.path.join(os.path.dirname(__file__), "data", "chroma_db")
# 当前向量持久化目录：直接放 data 目录下（ChromaDB 会在此建 chroma.sqlite3）
persist_directory = os.path.join(os.path.dirname(__file__), "data")
# 集合名称：同一 ChromaDB 实例下区分不同知识库
collection_name = "edi_knowledge"
# 检索时返回的相似文档数量（k 值）
similarity_threshold = 4

# ── MD5 去重记录 ──
# 已处理内容的 MD5 记录文件路径（一行一个 MD5）
md5_path = os.path.join(os.path.dirname(__file__), "data", "processed_md5.txt")

# ── 文本分割 ──
# 分块大小（字符数）：每块最多 100 字符
chunk_size = 100
# 相邻块重叠字符数：5 字符，保持上下文连贯
chunk_overlap = 5
# 分割优先级：先按段落、换行，再按中文标点，最后按空格和单字符兜底
separators = ["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""]

# ── 嵌入模型 API Key ──
# 复用视觉模型的 API Key 作为 DashScope Key（两者同一家阿里云 DashScope）
DASHSCOPE_API_KEY = _settings.vision_api_key or os.getenv("DASHSCOPE_API_KEY", "")
# 若 Key 来自 Settings 而非环境变量，则写回环境变量（langchain 底层也读它）
if DASHSCOPE_API_KEY and not os.getenv("DASHSCOPE_API_KEY"):
    os.environ["DASHSCOPE_API_KEY"] = DASHSCOPE_API_KEY

# ── RAG 模型配置 ──
# 嵌入模型：文本转向量的模型
embedding_model_name = "text-embedding-v4"
# 生成回答的聊天模型：复用主服务的 LLM 配置，未配置则用 qwen-plus
chat_model_name = _settings.llm_model or "qwen-plus"
