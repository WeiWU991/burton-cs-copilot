import streamlit as st
import google.generativeai as genai
import os
import glob
import time

# ================= 配置区 =================
st.set_page_config(page_title="Burton CS Co-pilot", page_icon="🏂", layout="wide")

# 定义知识库目录 (相对于 app.py)
KB_FOLDER = "knowledge_base"

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
if "kb_loaded" not in st.session_state:
    st.session_state.kb_loaded = False

# ================= 核心逻辑：合规性 & 知识库加载 =================

@st.cache_resource
def load_banned_words():
    """从 knowledge_base 文件夹自动读取敏感词"""
    banned_set = set()
    # 扫描目录下所有 txt 文件作为敏感词库
    txt_files = glob.glob(os.path.join(KB_FOLDER, "*.txt"))
    
    for txt_file in txt_files:
        try:
            with open(txt_file, "r", encoding='utf-8') as f:
                content = f.read()
                # 简单的分词处理 (逗号、换行)
                import re
                raw_words = re.split(r"[,\n\s']+", content)
                for w in raw_words:
                    clean_w = w.strip('"').strip("'").strip()
                    if len(clean_w) > 1:
                        banned_set.add(clean_w)
        except Exception:
            pass
    return banned_set

def compliance_shield(text, banned_set):
    """合规屏蔽器"""
    if not banned_set:
        return text, False
    
    found_issues = False
    checked_text = text
    for bad_word in banned_set:
        if bad_word in checked_text:
            found_issues = True
            checked_text = checked_text.replace(bad_word, "**") # 替换为星号
    return checked_text, found_issues

@st.cache_resource
def load_knowledge_base_files():
    """
    [自动加载] 扫描 knowledge_base 文件夹下的所有 .md 文件并上传到 Gemini
    """
    uploaded_refs = []
    
    if not os.path.exists(KB_FOLDER):
        os.makedirs(KB_FOLDER)
        return []

    # 找到所有 .md 文件
    md_files = glob.glob(os.path.join(KB_FOLDER, "*.md"))
    
    if not md_files:
        return []

    print(f"Found {len(md_files)} documents in knowledge base.")
    
    for file_path in md_files:
        try:
            file_name = os.path.basename(file_path)
            # 直接上传本地文件，无需创建临时文件
            file_ref = genai.upload_file(path=file_path, mime_type="text/plain", display_name=file_name)
            
            # 等待处理
            while file_ref.state.name == "PROCESSING":
                time.sleep(1)
                file_ref = genai.get_file(file_ref.name)
            
            uploaded_refs.append(file_ref)
            print(f"Loaded: {file_name}")
        except Exception as e:
            print(f"Failed to load {file_path}: {e}")
            
    return uploaded_refs

# --- 系统初始化 (只运行一次) ---
if api_key and not st.session_state.kb_loaded:
    with st.spinner("🚀 正在初始化 Burton 知识引擎... (首次加载可能需要几秒)"):
        # 1. 加载敏感词
        st.session_state.banned_words = load_banned_words()
        # 2. 加载知识库文件
        st.session_state.gemini_files = load_knowledge_base_files()
        st.session_state.kb_loaded = True

# ================= 侧边栏 =================
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/3/3b/Burton_Snowboards_logo.svg/2560px-Burton_Snowboards_logo.svg.png", width=150)
    st.title("⚙️ 系统状态")
    
    if api_key:
        st.success(api_status)
    else:
        st.error(api_status)
    
    st.divider()
    
    # 显示已加载的配置
    st.caption("📚 知识库 (管理员预置)")
    if st.session_state.gemini_files:
        for f in st.session_state.gemini_files:
            st.code(f"📄 {f.display_name}", language="text")
    else:
        st.warning(f"⚠️ 文件夹 {KB_FOLDER} 为空，请管理员上传数据。")

    st.caption("🛡️ 合规护盾")
    if st.session_state.banned_words:
        st.success(f"✅ 已激活 ({len(st.session_state.banned_words)} 词条)")
    else:
        st.warning("⚠️ 未激活")

    st.divider()

    # 模型选择
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

# ================= 主界面 =================
st.title("🏂 Burton China CS CO-Pilot")
st.caption("🚀 Powered by YZ-Shield | Native RAG | 🛡️ Ad-Law Auto-Shield")
# 移除了文件上传区域，直接进入对话界面
st.divider() 

# --- 对话工作台 ---
if st.session_state.chat_history:
    # 优化 UI：使用气泡式对话展示，更像聊天软件
    for role, text in st.session_state.chat_history[-6:]:
        if role == "user":
            with st.chat_message("user", avatar="👤"):
                st.write(text)
        else:
            with st.chat_message("assistant", avatar="🏂"):
                # 历史记录屏蔽敏感词
                safe_text, _ = compliance_shield(text, st.session_state.banned_words)
                st.markdown(safe_text)

# 核心 Prompt
system_instruction = """
你不是直接面对消费者的聊天机器人，你是 **Burton China 客服团队的智能副驾 (CS Copilot)**。
你的知识库已经由管理员预置（Markdown文档），数据精准且权威。

# 核心原则 (Critical)
1. **合规第一 (Compliance)**：严禁使用中国广告法禁止的极限词（如：第一、最强、顶级、首选、全网独家、极致等）。
   - **执行策略**：如果文档里有这些词，**请在回复时自动替换为合规的同义词**（例如：将"全网第一"改为"非常热销"，将"顶级"改为"高端"）。不要输出违规词。
2. **精准查询**：查询价格、参数时，必须严格对应文档中的表格数据。
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
> "[建议回复内容。**确保已替换所有广告法极限词**。]"

### 4️⃣ 🎯 关联销售机会
* **推荐搭配**: 
* **种草理由**: 
---
"""

# 输入框 (使用 chat_input 更符合聊天习惯)
user_query = st.chat_input("在此输入客户问题 (例如：新手推荐什么板子？)...")

if user_query:
    if not api_key:
        st.error("请先配置 API Key")
    elif not st.session_state.gemini_files:
        st.error("⚠️ 知识库未加载，请联系管理员在后台上传数据。")
    else:
        # 1. 显示用户提问
        with st.chat_message("user", avatar="👤"):
            st.write(user_query)
        
        # 2. 生成回答
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
            
            with st.chat_message("assistant", avatar="🏂"):
                with st.spinner("🤖 YZ-Shield 正在检索企业知识库..."):
                    response = chat.send_message(st.session_state.gemini_files + [user_query])
                    
                    # 强力屏蔽
                    final_text, has_issues = compliance_shield(response.text, st.session_state.banned_words)
                    
                    st.markdown(final_text)
                    
                    if has_issues:
                        st.toast("🛡️ 已自动屏蔽部分敏感词 (已替换为 ** )，请放心复制。", icon="✅")
            
            # 更新历史
            st.session_state.chat_history.append(("user", user_query))
            st.session_state.chat_history.append(("assistant", response.text))
                
        except Exception as e:
            st.error(f"生成失败: {e}")
            if "404" in str(e):
                st.warning("提示：请检查 API Key 是否支持 Gemini 3 Preview 模型。")
