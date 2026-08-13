# 知识库 (RAG) 模块

基于 ChromaDB + DashScope 嵌入的本地 RAG 系统。可选模块，不影响主服务运行。

## 架构

```
用户上传（Streamlit / Chat /upload / CLI）
        │
        ▼
  KnowledgeBaseService          ← 业务层：分块、MD5 去重
        │
        ▼
  VectorStoreService            ← 存储层：ChromaDB 读写
        │
        ├── search_knowledge    → 语义检索，返回原文片段
        ├── ask_knowledge       → 查询重写 → 检索 → LLM 生成回答（RagService 链）
        ├── add_knowledge       → 文档入库
        └── list_knowledge_sources → 已入库文档列表
```

> `ask_knowledge` 的完整链路：**查询重写 → 向量检索 → LLM 生成回答**。查询重写会把口语化问题（如「张三是谁」）改写成更利于检索的查询（如「张三的基本信息、生平简介」），召回更准确；重写失败时自动回退原问题，保证可用。

## 模块结构

```
servers/knowledge/
  __init__.py                   模块入口，创建单例，触发 MCP 注册
  config.py                     配置（分块、嵌入模型、API Key）
  md5_utils.py                  MD5 去重工具
  vector_store_service.py       存储层（纯 ChromaDB 操作）
  knowledge_base_service.py     业务层（分块、去重、上传/检索）
  knowledge_web.py              Streamlit 界面（上传 + RAG 对话）
  rag/
    __init__.py                 子模块入口
    rag_chain.py                RAG 链路（检索 + LLM 生成）
    rag_mcp_tools.py            4 个 MCP 工具
```

## 安装

```powershell
pip install chromadb langchain langchain-community langchain-text-splitters dashscope streamlit
```

不安装也不影响 MCP 主服务（条件导入）。

## MCP 工具

| 工具 | 参数 | 说明 |
|---|---|---|
| `search_knowledge` | query, top_k=5 | 语义检索，返回 top_k 个最相关片段 |
| `ask_knowledge` | query | 检索 + LLM 生成回答（完整 RAG 链路） |
| `add_knowledge` | content / file_path, source_name | 文本或文件入库 |
| `list_knowledge_sources` | — | 列出已入库文档来源和分块数 |

## 使用方式

### 1. Streamlit 界面

```powershell
streamlit run servers/knowledge/knowledge_web.py
```

上传文件 → 自动分块入库 → 对话窗口用 RagService 生成回答。

### 2. Chat 聊天上传

Chat 中点击 📎 → 自动上传到 `%TEMP%/mcp/uploads/` → LLM 调用 `add_knowledge` 入库。

### 3. MCP 工具直接调用

```
search_knowledge("VSWR CSV 怎么导出")
ask_knowledge("当前工程 S 参数仿真失败怎么办")
add_knowledge(content="...", source_name="使用说明")
```

### 4. Python 调用

```python
from servers.knowledge import _kb, _rag
results = _kb.search("VSWR")
answer = _rag.chain.invoke("解释 S 参数")
```

## 三层架构

| 层 | 文件 | 职责 |
|---|---|---|
| 存储层 | `vector_store_service.py` | ChromaDB 连接、读写、检索、删除 |
| 业务层 | `knowledge_base_service.py` | 文本分块、MD5 去重、上传/检索 |
| 应用层 | `rag/rag_chain.py` | RAG 链（查询重写 + 检索 + LLM 生成） |
| 工具层 | `rag/rag_mcp_tools.py` | MCP 工具注册 |

## 存储路径

```
servers/knowledge/data/
  sources/              ← 原始文件
  chroma_db/            ← ChromaDB 向量索引
  processed_md5.txt     ← 去重记录
```

## 配置

| 参数 | 默认值 | 说明 |
|---|---|---|
| `chunk_size` | 100 | 分块大小 |
| `chunk_overlap` | 5 | 重叠字符数 |
| `collection_name` | `edi_knowledge` | ChromaDB 集合名 |
| `persist_directory` | `data/chroma_db/` | 向量持久化目录 |
| `similarity_threshold` | 4 | 检索返回数量 |
| 嵌入模型 | `text-embedding-v4` | DashScope |
| 聊天模型 | 复用 `LLM_MODEL` | `.env` 配置 |
| API Key | 复用 `VISION_API_KEY` | DashScope |
