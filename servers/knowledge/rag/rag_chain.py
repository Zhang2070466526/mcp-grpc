"""RAG 链 — 检索 + LLM 生成回答。"""

from langchain_core.output_parsers import StrOutputParser       # 输出解析：提取字符串
from langchain_core.runnables import RunnablePassthrough         # 原样传递输入
from langchain_core.prompts import ChatPromptTemplate            # 聊天提示模板
from langchain_core.documents import Document                   # 文档类型（类型标注）
from langchain_community.chat_models.tongyi import ChatTongyi   # 通义千问聊天模型

from servers.knowledge.knowledge_base_service import KnowledgeBaseService
import servers.knowledge.config as config


class RagService(object):
    """RAG（检索增强生成）服务类 — 查询重写 + 检索 + LLM 生成回答。

    LangChain 链结构：
      input（用户问题）
        ├── context: 查询重写 → retriever → format_docs（重写后检索 + 格式化）
        └── input: passthrough（原问题，原样传递）
        → prompt_template（填入 system + user 模板）
        → chat_model（LLM 生成）
        → StrOutputParser（提取字符串）
    """

    def __init__(self):
        """初始化知识库服务、提示模板、查询重写链和聊天模型，构建 RAG 链。"""
        # 知识库服务（提供检索器）
        self.kb = KnowledgeBaseService()

        # 定义提示模板：system 注入参考资料，user 放用户问题
        self.prompt_template = ChatPromptTemplate.from_messages(
            [
                ("system", "以我提供的已知参考资料为主，"
                           "简洁和专业的回答用户问题。参考资料:{context}。"),
                ("user", "请回答用户提问: {input}")
            ]
        )

        # 初始化聊天模型（通义千问，模型名来自配置）
        self.chat_model = ChatTongyi(model=config.chat_model_name)

        # 查询重写链：把口语化问题改写成更利于检索的查询（复用同一聊天模型）
        self.rewrite_chain = (
            ChatPromptTemplate.from_messages([
                ("system", "你是查询重写助手。把用户的口语化问题改写成更具体、更利于语义检索的查询语句。"
                           "可以补充关键同义词和关键词，但不要添加用户没有询问的内容。"
                           "只输出改写后的查询，不要任何解释。"),
                ("user", "原始问题：{query}\n改写后的查询："),
            ])
            | self.chat_model
            | StrOutputParser()
        )

        # 构建执行链
        self.chain = self._build_chain()

    def _format_docs(self, docs: list[Document]) -> str:
        """把检索到的文档列表格式化为字符串，供提示模板的 {context} 使用。

        Args:
            docs: 检索到的文档列表。

        Returns:
            格式化后的字符串（无文档时返回「无相关参考资料」）。
        """
        if not docs:
            # 没有检索到文档时的兜底文案
            return "无相关参考资料"

        formatted_str = ""
        for doc in docs:
            # 拼接每个文档的正文和元数据
            formatted_str += f"文档片段: {doc.page_content}\n文档元数据: {doc.metadata}\n\n"

        return formatted_str

    def _rewrite_query(self, query: str) -> str:
        """用 LLM 重写查询，让向量检索更准确；失败时回退到原问题。

        Args:
            query: 用户原始问题。

        Returns:
            改写后的查询字符串（重写失败或结果为空时返回原问题）。
        """
        try:
            rewritten = self.rewrite_chain.invoke({"query": query})
            return rewritten.strip() if rewritten and rewritten.strip() else query
        except Exception:
            # 重写失败（LLM 异常等）时回退原问题，保证 RAG 仍可用
            return query

    def _build_chain(self):
        """构建 LangChain RAG 执行链。

        Returns:
            构建好的 Runnable 链。
        """
        # 获取检索器（从知识库拿到）
        retriever = self.kb.get_retriever()

        # 构建 RAG 链：
        #   input 原样传递；context 走「检索器 → 格式化」管道
        #   然后依次经过 提示模板 → 聊天模型 → 字符串解析器
        chain = (
                {
                    "input": RunnablePassthrough(),          # 原问题（供 prompt 展示）
                    "context": RunnablePassthrough() | self._rewrite_query | retriever | self._format_docs  # 重写 → 检索 → 格式化
                }
                | self.prompt_template   # 应用提示模板
                | self.chat_model        # 调用大语言模型
                | StrOutputParser()      # 解析输出为字符串
        )

        return chain
