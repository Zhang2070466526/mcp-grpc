"""
EDI 知识库管理 — Streamlit 界面。

启动方式：
    streamlit run servers/knowledge/knowledge_web.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st
import servers.knowledge.config as config
from servers.knowledge.knowledge_base_service import KnowledgeBaseService
from servers.knowledge.rag.rag_chain import RagService

st.set_page_config(page_title="知识库", page_icon="📚", layout="wide")

# ── 自定义样式 ──
st.markdown("""
<style>
    .main-header { font-size: 24px; font-weight: 700; margin-bottom: 4px; }
    .main-sub { color: #888; font-size: 13px; margin-bottom: 24px; }
    .stat-card { background: linear-gradient(135deg, #1a1b26, #24283b);
        border: 1px solid #3b4261; border-radius: 12px; padding: 16px 20px; text-align: center; }
    .stat-card .value { font-size: 28px; font-weight: 700; color: #7aa2f7; }
    .stat-card .label { font-size: 11px; color: #888; margin-top: 4px; }
    .search-result { background: #24283b; border: 1px solid #3b4261;
        border-radius: 10px; padding: 14px 16px; margin: 8px 0; }
    .search-result .score { font-size: 11px; color: #9ece6a; }
    .search-result .source { font-size: 11px; color: #565f89; }
    .search-result .content { font-size: 13px; line-height: 1.6; color: #c0caf5; margin-top: 6px; }
    .stChatMessage { background: transparent !important; }
</style>
""", unsafe_allow_html=True)

# ── 初始化 ──
kb = KnowledgeBaseService()
rag = RagService()

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# ── 顶部标题 + 统计卡片 ──
st.markdown('<div class="main-header">📚 EDI 知识库</div>', unsafe_allow_html=True)
st.markdown('<div class="main-sub">基于 ChromaDB + DashScope 嵌入的本地 RAG 系统</div>',
            unsafe_allow_html=True)

total = kb.count()
source_count = len(kb.list_sources())

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown(f'<div class="stat-card"><div class="value">{total}</div><div class="label">总分块数</div></div>',
                unsafe_allow_html=True)
with c2:
    st.markdown(f'<div class="stat-card"><div class="value">{source_count}</div><div class="label">文档数</div></div>',
                unsafe_allow_html=True)
with c3:
    st.markdown(f'<div class="stat-card"><div class="value">{config.chunk_size}</div><div class="label">分块大小</div></div>',
                unsafe_allow_html=True)
with c4:
    st.markdown(f'<div class="stat-card"><div class="value">text-embedding-v4</div><div class="label">嵌入模型</div></div>',
                unsafe_allow_html=True)

st.divider()

# ── Tab 切换 ──
tab_upload, tab_chat, tab_sources = st.tabs(["📤 上传文档", "💬 检索对话", "📋 文档列表"])

# ── Tab 1: 上传 ──
with tab_upload:
    col_left, col_right = st.columns([3, 2])

    with col_left:
        uploaded_file = st.file_uploader(
            "选择文件上传到知识库",
            type=["txt", "md", "csv", "log", "py"],
            accept_multiple_files=False,
        )

        if uploaded_file is not None:
            file_name = uploaded_file.name
            file_size = uploaded_file.size / 1024
            try:
                text = uploaded_file.getvalue().decode("utf-8")
                st.info(f"已选择：{file_name}（{file_size:.1f} KB）")

                with st.expander("📄 文件内容预览", expanded=False):
                    st.text_area("文件内容", text, height=250, label_visibility="collapsed")

                if st.button("🚀 录入知识库", type="primary", use_container_width=True):
                    # 保存原始文件
                    sources_dir = Path(__file__).parent / "data" / "sources"
                    sources_dir.mkdir(parents=True, exist_ok=True)
                    saved_path = sources_dir / file_name
                    saved_path.write_bytes(uploaded_file.getvalue())
                    with st.spinner("正在分块、向量化..."):
                        result = kb.upload_by_str(text, file_name)
                    if result["success"]:
                        st.success(result["message"])
                        st.caption(f"原始文件：{saved_path}")
                        st.balloons()
                        st.rerun()
                    else:
                        st.warning(result["message"])

            except UnicodeDecodeError:
                st.error("文件编码不是 UTF-8，请转换后重试")

    with col_right:
        st.markdown("##### 📌 支持格式")
        st.markdown("- `.txt` 纯文本\n- `.md` Markdown\n- `.csv` 数据表\n- `.log` 日志\n- `.py` 代码")
        st.markdown("##### 🔧 处理流程")
        st.markdown(f"1. 分块：{config.chunk_size} 字/块，{config.chunk_overlap} 字重叠\n2. 嵌入：DashScope text-embedding-v4\n3. 存储：ChromaDB 本地持久化\n4. 去重：MD5 避免重复入库")
        st.markdown("##### 💡 提示")
        st.markdown("上传后可在「检索对话」中提问，已入库文档在「文档列表」查看。")

# ── Tab 2: 对话 ──
with tab_chat:
    if not st.session_state.chat_history and total == 0:
        st.info("👋 知识库还是空的，先去「上传文档」加一些内容吧。")
    elif not st.session_state.chat_history:
        st.info(f"👋 知识库有 {total} 个分块，输入问题开始检索。")

    # 对话历史
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            if msg["role"] == "assistant":
                st.markdown(msg["content"], unsafe_allow_html=True)
            else:
                st.write(msg["content"])

    # 输入
    query = st.chat_input("输入问题，检索知识库...")
    if query:
        st.session_state.chat_history.append({"role": "user", "content": query})

        with st.chat_message("user"):
            st.write(query)

        with st.chat_message("assistant"):
            with st.spinner("思考中..."):
                try:
                    answer = rag.chain.invoke(query.strip())
                except Exception as e:
                    answer = f"生成回答失败: {e}"

            st.markdown(answer, unsafe_allow_html=True)
            st.session_state.chat_history.append({"role": "assistant", "content": answer})

        if len(st.session_state.chat_history) > 10:
            st.caption("💡 对话较长，可点侧边栏「清空对话」重置。")

# ── Tab 3: 文档列表 ──
with tab_sources:
    if source_count == 0:
        st.info("暂无已入库文档。")
    else:
        for source in kb.list_sources():
            st.markdown(f"📄 **{source}**")

# ── 侧边栏 ──
with st.sidebar:
    st.header("⚙️ 设置")
    if st.button("🗑 清空对话", use_container_width=True):
        st.session_state.chat_history = []
        st.rerun()

    st.divider()
    st.caption(f"向量数据：`servers/knowledge/data/chroma_db/`")
    st.caption(f"原始文件：`servers/knowledge/data/sources/`")
    st.caption(f"集合名称：`edi_knowledge`")
