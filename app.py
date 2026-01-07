import streamlit as st
import google.generativeai as genai
import tempfile
import os

# ================= 配置区 =================
st.set_page_config(page_title="Burton CS Copilot", page_icon="🏂", layout="wide")

# --- 核心修改点：API Key 从后台读取，不再让用户输入 ---
try:
    # 尝试从 Streamlit Secrets 读取 Key
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
    api_status = "✅ 系统核心已连接 (管理员配置)"
except FileNotFoundError:
    # 本地调试时的 fallback (如果没有 secrets 文件)
    api_status = "⚠️ 未检测到密钥配置，请在 .streamlit/secrets.toml 中设置"
    api_key = None
except Exception as e:
    api_status = f"⚠️ 配置错误: {str(e)}"
    api_key = None

# ================= 侧边栏 =================
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/3/3b/Burton_Snowboards_logo.svg/2560px-Burton_Snowboards_logo.svg.png", width=150)
    st.title("⚙️ 系统状态")
    
    # 显示连接状态，但不显示 Key
    if api_key:
        st.success(api_status)
    else:
        st.error(api_status)
    
    st.divider()
    
    # 模型选择器
    model_choice = st.radio(
        "🧠 选择大脑引擎:",
        ("⚡ 极速模式 (Flash)", "🐢 深度思考模式 (Pro)"),
        index=0,
        help="极速模式适合日常快速问答；深度模式适合处理极度复杂的纠纷或分析。"
    )
    selected_model_name = "gemini-1.5-flash" if "Flash" in model_choice else "gemini-1.5-pro"
    
    st.info("💡 说明：价格数据已启用高亮校验机制。")

# ================= 核心逻辑 =================
def upload_to_gemini(uploaded_file):
    with tempfile.NamedTemporaryFile(delete=False, suffix='.' + uploaded_file.name.split('.')[-1]) as tmp_file:
        tmp_file.write(uploaded_file.getvalue())
        tmp_path = tmp_file.name
    try:
        file_ref = genai.upload_file(path=tmp_path, display_name=uploaded_file.name)
        while file_ref.state.name == "PROCESSING":
            import time
            time.sleep(1)
            file_ref = genai.get_file(file_ref.name)
        return file_ref
    finally:
        os.remove(tmp_path)

# ================= 界面布局 =================
st.title("🏂 Burton China 客服智能副驾 (Pilot v1.2)")
st.caption("🚀 Powered by Gemini 1.5 | Native RAG Technology")
st.divider()

col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("📂 知识库加载")
    st.markdown("请上传 **W26新品手册** 及 **客服培训SOP**：")
    uploaded_files = st.file_uploader("", type=['pdf'], accept_multiple_files=True, label_visibility="collapsed")
    
    if uploaded_files and api_key:
        if "gemini_files" not in st.session_state:
            st.session_state.gemini_files = []
            
        if st.button("🔌 激活并连接知识库", type="primary", use_container_width=True):
            progress_bar = st.progress(0)
            for i, up_file in enumerate(uploaded_files):
                file_ref = upload_to_gemini(up_file)
                st.session_state.gemini_files.append(file_ref)
                progress_bar.progress((i + 1) / len(uploaded_files))
            st.success(f"✅ {len(uploaded_files)} 份核心文档已挂载！")

    if "gemini_files" in st.session_state and st.session_state.gemini_files:
        with st.expander("📚 已挂载文档列表", expanded=True):
            for f in st.session_state.gemini_files:
                st.text(f"📄 {f.display_name}")

with col2:
    st.subheader("💬 客服工作台")
    
    # --- 核心修改点：Prompt 中增加 Streamlit 颜色语法 ---
    system_instruction = """
    你不是直接面对消费者的聊天机器人，你是 **Burton China 客服团队的智能副驾 (CS Copilot)**。
    你的目标是辅助客服人员（User），基于用户上传的文件，提供精准的产品参数、价格核验、销售话术和关联推荐。
    
    # 核心原则
    1. **原生理解**：你拥有阅读整份文档的能力。请综合上下文理解。
    2. **价格核验与高亮**：
       - 涉及价格时，必须在文档中找到视觉锚点（如表格行、列标题）确认。
       - **强制高亮格式**：输出价格时，必须使用 Streamlit 颜色语法 `:orange[**¥价格**]`。例如：:orange[**¥4298**]。
       - 如果无法100%确定，请标注"(需人工核对)"。
    3. **输出格式**：请严格按照 Markdown 格式输出【控制台视图】。

    # 输出视图结构
    ---
    ### 1️⃣ 🧠 客户画像分析
    * **客户类型**: 
    * **关键缺项**: 
    * **情绪指数**: 

    ### 2️⃣ 📚 核心知识胶囊
    * **推荐产品**: 
    * **参考价格**: :orange[**¥xxxx**] (源自 PDF P.xx)
    * **核心科技**: 
    * **技术解释**: 

    ### 3️⃣ 💬 建议回复话术
    > **请复制以下内容发送给客户：**
    > "[建议回复内容]"

    ### 4️⃣ 🎯 关联销售机会
    * **推荐搭配**: 
    * **种草理由**: 
    ---
    """

    user_query = st.text_area("在此粘贴客户咨询内容：", height=150, placeholder="例如：我想买一套 Step On，平时穿42码鞋，配什么板子？")

    if st.button("✨ 生成专家建议", type="primary"):
        if not api_key:
            st.error("🔒 系统未授权：请管理员在后台配置 API Key")
        elif "gemini_files" not in st.session_state or not st.session_state.gemini_files:
            st.warning("👈 请先在左侧上传并激活知识库 PDF")
        else:
            try:
                model = genai.GenerativeModel(
                    model_name=selected_model_name,
                    system_instruction=system_instruction
                )
                request_content = st.session_state.gemini_files + [user_query]
                
                with st.spinner("🤖 正在调用 Burton 大脑进行分析..."):
                    response = model.generate_content(request_content)
                    st.markdown(response.text)
            except Exception as e:
                st.error(f"连接中断，请重试: {e}")