import streamlit as st
import google.generativeai as genai
import tempfile
import os

# ================= 配置区 =================
st.set_page_config(page_title="Burton CS Co-pilot", page_icon="🏂", layout="wide")

# --- 1. 读取 Secrets (保持不变) ---
try:
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
    api_status = "✅ 系统核心已连接"
except Exception as e:
    api_status = f"⚠️ 配置错误: {str(e)}"
    api_key = None

# --- 2. 初始化 Session State (记忆库) ---
if "chat_history" not in st.session_state:
    st.session_state.chat_history = [] # 存储对话历史
if "gemini_files" not in st.session_state:
    st.session_state.gemini_files = [] # 存储文件引用

# ================= 侧边栏：控制中心 =================
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/3/3b/Burton_Snowboards_logo.svg/2560px-Burton_Snowboards_logo.svg.png", width=150)
    st.title("⚙️ 控制台")
    
    if api_key:
        st.success(api_status)
    else:
        st.error(api_status)
    
    st.divider()

    # 模型选择
    model_choice = st.radio(
        "🧠 大脑引擎:",
        ("⚡ 极速模式 (Flash)", "🐢 深度思考 (Pro)"),
        index=0
    )
    selected_model_name = "gemini-3-flash-preview" if "Flash" in model_choice else "gemini-3-pro-preview"

    st.divider()

    # --- 🆕 新功能：接待下一位 (清空记忆) ---
    st.markdown("### 🧹 场景切换")
    if st.button("接待新客户 (清空记忆)", type="primary", use_container_width=True):
        st.session_state.chat_history = [] # 清空历史
        st.rerun() # 强制刷新页面
    st.caption("💡 提示：每当切换不同的客户咨询时，请点击此按钮防止信息混淆。")

# ================= 核心逻辑：文件上传 =================
# 使用 cache_resource 防止每次点击都重新加载函数
@st.cache_resource
def process_uploaded_file(uploaded_file):
    """处理上传文件并返回 Gemini 文件对象"""
    with tempfile.NamedTemporaryFile(delete=False, suffix='.' + uploaded_file.name.split('.')[-1]) as tmp_file:
        tmp_file.write(uploaded_file.getvalue())
        tmp_path = tmp_file.name
    try:
        file_ref = genai.upload_file(path=tmp_path, display_name=uploaded_file.name)
        # 等待处理完成
        while file_ref.state.name == "PROCESSING":
            import time
            time.sleep(1)
            file_ref = genai.get_file(file_ref.name)
        return file_ref
    finally:
        os.remove(tmp_path)

# ================= 主界面布局 =================
st.title("🏂 Burton China CS CO-Pilot")
st.caption("🚀 Powered by YZ-Shield | Native RAG Technology")
st.divider()

col1, col2 = st.columns([1, 2])

# --- 左侧：知识库 (上传一次即可) ---
with col1:
    st.subheader("📂 知识库状态")
    uploaded_files = st.file_uploader("上传资料 (PDF)", type=['pdf'], accept_multiple_files=True, label_visibility="collapsed")
    
    if uploaded_files and api_key:
        # 只有当文件列表为空，或者用户上传了新文件时才处理
        # 这里做一个简单的去重检查，防止页面刷新导致的重复上传
        if not st.session_state.gemini_files: 
            if st.button("🔌 激活知识库", type="secondary", use_container_width=True):
                progress_bar = st.progress(0)
                for i, up_file in enumerate(uploaded_files):
                    file_ref = process_uploaded_file(up_file) # 使用缓存函数
                    st.session_state.gemini_files.append(file_ref)
                    progress_bar.progress((i + 1) / len(uploaded_files))
                st.success(f"✅ {len(uploaded_files)} 份文档已挂载！")
                st.rerun()

    # 显示当前挂载的文件
    if st.session_state.gemini_files:
        with st.expander("📚 当前生效的文档", expanded=True):
            for f in st.session_state.gemini_files:
                st.text(f"📄 {f.display_name}")
            st.caption("✅ 机器人已记住这些内容，直到您刷新页面。")

# --- 右侧：多轮对话工作台 ---
with col2:
    st.subheader("💬 对话工作台")

    # 1. 显示历史对话 (让客服看到上下文)
    # 我们只显示最近的几轮，避免太长
    if st.session_state.chat_history:
        with st.expander("🕒 历史对话记录", expanded=False):
            for role, text in st.session_state.chat_history:
                if role == "user":
                    st.markdown(f"**客户**: {text}")
                else:
                    st.markdown(f"**Burton助手**: *[已生成建议]*")

    # 2. 核心 Prompt (包含记忆逻辑)
    system_instruction = """
    你不是直接面对消费者的聊天机器人，你是 **Burton China 客服团队的智能副驾 (CS Copilot)**。
    你的目标是辅助客服人员（User），基于用户上传的文件，提供精准的产品参数、价格核验、销售话术和关联推荐。
    
    # 核心原则 (必须严格遵守)
    1. **原生理解与记忆**：你拥有阅读整份文档的能力，并且**记得**我们刚才聊过的内容（如客户的体重、偏好）。请结合上下文回答。
    2. **价格核验与高亮**：
       - 涉及价格时，必须在文档中找到视觉锚点（如表格行、列标题）确认。
       - **强制高亮格式**：输出价格时，必须使用 Streamlit 颜色语法 `:orange[**¥价格**]`。例如：:orange[**¥4298**]。
       - 如果无法100%确定，请标注"(需人工核对)"。
    3. **硬性销售逻辑 (Critical)**：
       - **选板必问体重**：当客户咨询雪板时，如果【当前问题】和【历史对话】中都没有包含**体重**和**鞋码**，建议回复话术的**最后一句必须是反问句**，索要这些信息。
       - **Step On必问鞋码**：推荐固定器时，必须核对鞋码。
    4. **输出格式**：请严格按照 Markdown 格式输出【控制台视图】。

    # 输出视图结构
    ---
    ### 1️⃣ 🧠 客户画像分析
    * **客户类型**: [结合历史对话判断]
    * **关键缺项**: [⚠️ 高亮显示缺失信息]
    * **情绪指数**: [⭐⭐⭐⭐⭐]

    ### 2️⃣ 📚 核心知识胶囊
    * **推荐产品**: 
    * **参考价格**: :orange[**¥xxxx**] (源自 PDF P.xx)
    * **技术解释**: 

    ### 3️⃣ 💬 建议回复话术
    > **请复制以下内容发送给客户：**
    > "[建议回复内容。策略：1. 承接上一轮对话 2. 解答当前问题 3. **如果信息缺失，必须反问**]"

    ### 4️⃣ 🎯 关联销售机会
    * **推荐搭配**: 
    * **种草理由**: 
    ---
    """

    # 3. 输入框 (使用 form 防止回车自动提交，增加稳定性)
    with st.form(key="chat_form", clear_on_submit=True):
        user_query = st.text_area("在此粘贴客户咨询内容：", height=100, placeholder="例如：我想买个板子... (按Ctrl+Enter发送)")
        submit_button = st.form_submit_button("✨ 发送 / 生成建议")

    # 4. 处理逻辑
    if submit_button and user_query:
        if not api_key or not st.session_state.gemini_files:
            st.error("请先配置 API Key 并激活知识库")
        else:
            try:
                # 构造 ChatSession (带记忆的对话)
                model = genai.GenerativeModel(
                    model_name=selected_model_name,
                    system_instruction=system_instruction
                )
                
                # 手动构建 history 列表传给 Gemini
                # Gemini 的 history 格式是 [{'role': 'user', 'parts': [...]}, {'role': 'model', 'parts': [...]}]
                gemini_history = []
                for role, text in st.session_state.chat_history:
                    gemini_role = "user" if role == "user" else "model"
                    gemini_history.append({"role": gemini_role, "parts": [text]})

                # 启动聊天会话 (带上文件 + 历史)
                # 注意：文件只需要在 system instruction 或者第一次消息里给，
                # 但为了简单，我们把文件作为本次请求的一部分，Gemini 会自动处理 context
                
                chat = model.start_chat(history=gemini_history)
                
                with st.spinner("🤖 正在结合上下文思考..."):
                    # 发送包含文件的请求 (Gemini API 支持 list 包含 file 和 text)
                    response = chat.send_message(st.session_state.gemini_files + [user_query])
                    
                    # 显示结果
                    st.markdown(response.text)
                    
                    # 更新历史 (存入 session state)
                    st.session_state.chat_history.append(("user", user_query))
                    st.session_state.chat_history.append(("assistant", response.text))
                    
            except Exception as e:
                st.error(f"生成失败: {e}")
                if "404" in str(e):
                    st.warning("提示：请检查所选模型是否可用，尝试切换回 Pro 模式。")
