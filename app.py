import streamlit as st
import google.generativeai as genai
import tempfile
import os
import pandas as pd
import re

# ================= 配置区 =================
st.set_page_config(page_title="Burton CS Co-pilot", page_icon="🏂", layout="wide")

# --- 1. 读取 Secrets ---
try:
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
    api_status = "✅ 系统核心已连接"
except Exception as e:
    api_status = f"⚠️ 配置错误: {str(e)}"
    api_key = None

# --- 2. 初始化 Session State ---
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "gemini_files" not in st.session_state:
    st.session_state.gemini_files = []
if "banned_words" not in st.session_state:
    st.session_state.banned_words = set()

# ================= 核心逻辑：合规性检查 (硬逻辑) =================
@st.cache_resource
def load_banned_words():
    """读取本地的极限词清单文件，构建违禁词库"""
    banned_set = set()
    try:
        # 尝试读取同目录下的 banned_words.txt
        # 如果文件里是逗号分隔的字符串，如 '第一', '销量王'
        with open("banned_words.txt", "r", encoding='utf-8') as f:
            content = f.read()
            # 使用正则清洗数据：去掉引号、方括号、换行，只留纯文本
            # 假设文件内容格式比较杂乱，我们统一按逗号或换行分割
            raw_words = re.split(r"[,\n\s']+", content)
            for w in raw_words:
                clean_w = w.strip('"').strip("'").strip()
                if len(clean_w) > 1: # 忽略单个字的误杀
                    banned_set.add(clean_w)
        return banned_set
    except FileNotFoundError:
        return set()

def compliance_check(text, banned_set):
    """
    合规扫描器：
    如果发现违规词，将其替换为醒目的红色警示文本。
    """
    if not banned_set:
        return text, False
    
    found_issues = False
    checked_text = text
    
    # 遍历所有违禁词 (为了性能，实际生产环境可用 AC 自动机算法优化，这里用循环足够演示)
    for bad_word in banned_set:
        if bad_word in checked_text:
            found_issues = True
            # 使用 Streamlit 的红色高亮语法替换违规词
            replacement = f":red[**🚫{bad_word}**]" 
            checked_text = checked_text.replace(bad_word, replacement)
            
    return checked_text, found_issues

# 加载违禁词到内存
st.session_state.banned_words = load_banned_words()

# ================= 侧边栏 =================
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/3/3b/Burton_Snowboards_logo.svg/2560px-Burton_Snowboards_logo.svg.png", width=150)
    st.title("⚙️ 控制台")
    
    if api_key:
        st.success(api_status)
    else:
        st.error(api_status)
    
    # 显示合规库状态
    if st.session_state.banned_words:
        st.info(f"🛡️ 合规护盾已开启\n已加载 {len(st.session_state.banned_words)} 个电商极限词")
    else:
        st.warning("⚠️ 未检测到极限词清单文件，合规检查未激活")

    st.divider()

    model_choice = st.radio(
        "🧠 大脑引擎:",
        ("⚡ 极速模式 (Gemini 3 Flash)", "🐢 深度思考 (Gemini 3 Pro)"),
        index=0
    )
    selected_model_name = "gemini-3-flash-preview" if "Flash" in model_choice else "gemini-3-pro-preview"

    st.divider()

    if st.button("接待新客户 (清空记忆)", type="primary", use_container_width=True):
        st.session_state.chat_history = []
        st.rerun()
    st.caption("💡 提示：切换客户时请点击此按钮。")

# ================= 核心逻辑：文件上传 =================
@st.cache_resource
def process_uploaded_file(uploaded_file):
    file_ext = uploaded_file.name.split('.')[-1].lower()
    tmp_path = ""
    mime_type = "text/plain"

    try:
        if file_ext in ['xlsx', 'xls']:
            df = pd.read_excel(uploaded_file)
            text_content = df.to_markdown(index=False)
            final_content = f"# 数据来源: {uploaded_file.name}\n\n{text_content}"
            with tempfile.NamedTemporaryFile(delete=False, suffix='.txt', mode='w', encoding='utf-8') as tmp_file:
                tmp_file.write(final_content)
                tmp_path = tmp_file.name
        elif file_ext == 'md':
            with tempfile.NamedTemporaryFile(delete=False, suffix='.md', mode='wb') as tmp_file:
                tmp_file.write(uploaded_file.getvalue())
                tmp_path = tmp_file.name
                mime_type = "text/md"
        else:
            return None

        file_ref = genai.upload_file(path=tmp_path, mime_type=mime_type, display_name=uploaded_file.name)
        while file_ref.state.name == "PROCESSING":
            import time
            time.sleep(1)
            file_ref = genai.get_file(file_ref.name)
        return file_ref

    except Exception as e:
        st.error(f"文件处理错误: {e}")
        return None
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

# ================= 主界面 =================
st.title("🏂 Burton China CS CO-Pilot")
st.caption("🚀 Powered by YZ-Shield | Native RAG | 🛡️ Ad-Law Compliance Guard")
st.divider()

col1, col2 = st.columns([1, 2])

# --- 左侧：知识库 ---
with col1:
    st.subheader("📂 知识库状态")
    uploaded_files = st.file_uploader(
        "上传资料 (Excel/Markdown)", 
        type=['xlsx', 'xls', 'md'], 
        accept_multiple_files=True, 
        label_visibility="collapsed"
    )
    
    if uploaded_files and api_key:
        if not st.session_state.gemini_files: 
            if st.button("🔌 激活并清洗数据", type="secondary", use_container_width=True):
                progress_bar = st.progress(0)
                for i, up_file in enumerate(uploaded_files):
                    file_ref = process_uploaded_file(up_file) 
                    if file_ref:
                        st.session_state.gemini_files.append(file_ref)
                    progress_bar.progress((i + 1) / len(uploaded_files))
                st.success(f"✅ {len(st.session_state.gemini_files)} 份结构化数据已挂载！")
                st.rerun()

    if st.session_state.gemini_files:
        with st.expander("📚 当前生效的数据表", expanded=True):
            for f in st.session_state.gemini_files:
                st.text(f"📊 {f.display_name}")

# --- 右侧：对话工作台 ---
with col2:
    st.subheader("💬 对话工作台")

    if st.session_state.chat_history:
        with st.expander("🕒 历史对话记录", expanded=False):
            for role, text in st.session_state.chat_history[-6:]:
                if role == "user":
                    st.markdown(f"**客户**: {text}")
                else:
                    # 历史记录也要做合规渲染
                    safe_text, _ = compliance_check(text, st.session_state.banned_words)
                    st.markdown(f"**Burton助手**: {safe_text}")

    # 核心 Prompt (加入合规指令)
    system_instruction = """
    你不是直接面对消费者的聊天机器人，你是 **Burton China 客服团队的智能副驾 (CS Copilot)**。
    你的知识库由【Excel表格】和【Markdown文档】组成，数据非常精准。
    
    # 核心原则 (Critical)
    1. **合规第一 (Compliance)**：作为电商客服，严禁使用中国广告法禁止的极限词（如：第一、最强、顶级、首选、全网独家等）。如果文档里有这些词，**请在回复时自动替换为合规说法**（如"热销"、"优选"）。
    2. **精准查询**：查询价格、参数时，必须严格对应表格数据。
    3. **价格高亮**：使用 `:orange[**¥价格**]` 格式。
    4. **硬性销售逻辑**：
       - **选板必问体重**。
       - **Step On必问鞋码**。
    5. **输出格式**：请严格按照 Markdown 格式输出【控制台视图】。

    # 输出视图结构
    ---
    ### 1️⃣ 🧠 客户画像分析
    * **客户类型**: 
    * **关键缺项**: [⚠️ 高亮显示]
    * **情绪指数**: [⭐⭐⭐⭐⭐]

    ### 2️⃣ 📚 核心知识胶囊
    * **推荐产品**: 
    * **参考价格**: :orange[**¥xxxx**] (数据来源: [文件名])
    * **核心科技**: 
    * **技术解释**: 

    ### 3️⃣ 💬 建议回复话术
    > **请复制以下内容发送给客户：**
    > "[建议回复内容。**注意：请确保话术不包含任何广告法极限词**。]"

    ### 4️⃣ 🎯 关联销售机会
    * **推荐搭配**: 
    * **种草理由**: 
    ---
    """

    with st.form(key="chat_form", clear_on_submit=True):
        user_query = st.text_area("在此粘贴客户咨询内容：", height=100, placeholder="例如：这款板子是不是全网第一？ (按Ctrl+Enter发送)")
        submit_button = st.form_submit_button("✨ 发送 / 生成建议")

    if submit_button and user_query:
        if not api_key or not st.session_state.gemini_files:
            st.error("请先配置 API Key 并上传 Excel/Markdown 数据")
        else:
            try:
                model = genai.GenerativeModel(
                    model_name=selected_model_name,
                    system_instruction=system_instruction
                )
                
                gemini_history = []
                for role, text in st.session_state.chat_history[-6:]:
                    gemini_role = "user" if role == "user" else "model"
                    gemini_history.append({"role": gemini_role, "parts": [text]})

                chat = model.start_chat(history=gemini_history)
                
                with st.spinner(f"🤖 正在调用 {selected_model_name} 分析 (含合规审查)..."):
                    response = chat.send_message(st.session_state.gemini_files + [user_query])
                    
                    # --- 🛡️ 核心：执行合规扫描 ---
                    final_text, has_issues = compliance_check(response.text, st.session_state.banned_words)
                    
                    if has_issues:
                        st.toast("⚠️ 警告：回复中检测到广告法敏感词，已自动标红，请人工修改后再发送！", icon="🚨")
                    
                    st.markdown(final_text)
                    
                    # 存入历史的是原始文本(以便模型理解上下文)，还是处理后的文本？
                    # 建议存原始文本给模型(防止模型被干扰)，但展示给用户看处理后的。
                    # 这里简化处理，存原始文本。
                    st.session_state.chat_history.append(("user", user_query))
                    st.session_state.chat_history.append(("assistant", response.text))
                    
            except Exception as e:
                st.error(f"生成失败: {e}")
                if "404" in str(e):
                    st.warning("提示：请检查您的 API Key 是否支持 Gemini 3 Preview 模型。")

