import streamlit as st
import google.generativeai as genai
import os
import glob
import time
from datetime import datetime
import re

# ================= 1. 基础配置 =================
st.set_page_config(page_title="Burton CS Co-pilot", page_icon="🏂", layout="wide")

KB_FOLDER = "knowledge_base"
LOG_FOLDER = "chat_logs"

if not os.path.exists(LOG_FOLDER): 
    os.makedirs(LOG_FOLDER)

# --- API 连接 ---
try:
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
    api_status = "✅ 核心已连接 (Gemini 3.0)"
except Exception as e:
    api_status = f"⚠️ 配置错误: {str(e)}"
    api_key = None

# --- 初始化状态 ---
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "gemini_files" not in st.session_state:
    st.session_state.gemini_files = []
if "banned_words" not in st.session_state:
    st.session_state.banned_words = set()
if "kb_loaded" not in st.session_state:
    st.session_state.kb_loaded = False
if "is_first_turn" not in st.session_state:
    st.session_state.is_first_turn = True

# ================= 2. 日志系统 =================
def save_to_daily_log(role, text):
    today_str = datetime.now().strftime("%Y-%m-%d")
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_filename = os.path.join(LOG_FOLDER, f"chat_log_{today_str}.txt")
    clean_text = re.sub(r':\w+\[\*\*(.*?)\*\*\]', r'\1', text)
    log_entry = f"[{timestamp}] {role.upper()}:\n{clean_text}\n{'-'*60}\n"
    try:
        with open(log_filename, "a", encoding="utf-8") as f:
            f.write(log_entry)
    except: pass

# ================= 3. 合规过滤 =================
SAFE_WORDS = {"Burton", "BURTON", "burton", "Anon", "ANON", "anon", "ak", "AK", "GORE-TEX", "Boa", "MIPS", "Step On", "Est", "Re:Flex"}
SMART_SYNONYMS = {"第一": "排名前列", "NO.1": "人气热销", "Top1": "人气热销", "冠军": "人气优选", "首选": "优选", "顶级": "高端", "最": "十分"}

@st.cache_resource
def load_banned_words():
    banned_set = set()
    txt_files = glob.glob(os.path.join(KB_FOLDER, "*.txt"))
    for txt_file in txt_files:
        try:
            with open(txt_file, "r", encoding='utf-8') as f:
                content = f.read()
                words = re.split(r"[,\n\s'\"\[\]]+", content)
                for w in words:
                    cw = w.strip()
                    if (len(cw) > 1 or cw == '最') and cw not in SAFE_WORDS:
                        banned_set.add(cw)
        except: pass
    return banned_set

def smart_compliance_filter(text, banned_set):
    if not banned_set: return text, False
    found = False
    for word in banned_set:
        if word in text:
            found = True
            replacement = SMART_SYNONYMS.get(word, "出色")
            text = text.replace(word, f":red[**🚫{word}**](建议改为:{replacement})")
    return text, found

# ================= 4. 知识库加载与自愈 =================
@st.cache_resource
def load_knowledge_base_files():
    uploaded_refs = []
    md_files = glob.glob(os.path.join(KB_FOLDER, "*.md"))
    for file_path in md_files:
        try:
            file_ref = genai.upload_file(path=file_path, mime_type="text/plain")
            uploaded_refs.append(file_ref)
        except: pass
    return uploaded_refs

def reset_knowledge_base():
    load_knowledge_base_files.clear()
    load_banned_words.clear()
    st.session_state.kb_loaded = False
    if "cs_chat_session" in st.session_state: del st.session_state.cs_chat_session
    st.session_state.is_first_turn = True
    st.rerun()

if api_key and not st.session_state.kb_loaded:
    with st.spinner("🚀 初始化 Burton 引擎..."):
        st.session_state.banned_words = load_banned_words()
        st.session_state.gemini_files = load_knowledge_base_files()
        st.session_state.kb_loaded = True

# ================= 5. 侧边栏与管理模块 =================
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/3/3b/Burton_Snowboards_logo.svg/2560px-Burton_Snowboards_logo.svg.png", width=150)
    
    app_mode = st.radio("🎯 核心模块:", ["💬 客服实战副驾", "🎓 AI 模拟陪练营"])
    
    if st.button("🗑️ 接待新客户 (清空记忆)", type="primary", use_container_width=True):
        st.session_state.chat_history = []
        st.session_state.is_first_turn = True
        if "cs_chat_session" in st.session_state: del st.session_state.cs_chat_session
        st.rerun()

    st.divider()
    st.caption("⚙️ 系统状态")
    st.success(api_status) if api_key else st.error(api_status)
    
    model_choice = st.radio("🧠 大脑引擎:", ("⚡ 极速模式 (Flash 3.0)", "🐢 深度思考 (Pro 3.0)"), index=0)
    selected_model_name = "gemini-3-flash-preview" if "Flash" in model_choice else "gemini-3-pro-preview"
    
    if st.button("🔄 唤醒知识库 (修复403)", use_container_width=True):
        reset_knowledge_base()

    st.divider()
    
    # 🟢 密码锁逻辑
    with st.expander("🔐 内部日志系统 (管理员)"):
        admin_pwd = st.text_input("请输入密令提取日志:", type="password")
        if admin_pwd == "burton2026": 
            st.success("验证通过！")
            all_logs = sorted(glob.glob(os.path.join(LOG_FOLDER, "*.txt")), reverse=True)
            if all_logs:
                selected_log = st.selectbox("选择日期", all_logs, format_func=lambda x: os.path.basename(x))
                with open(selected_log, "rb") as f:
                    st.download_button("📥 下载选定日志", f, file_name=os.path.basename(selected_log), use_container_width=True)
            else:
                st.info("暂无对话记录")

# ================= 6. 主界面 =================
if app_mode == "💬 客服实战副驾":
    st.title("🏂 Burton 客服副驾 (Gemini 3.0)")
    st.caption("提高服务人员的‘专业底线’，将繁琐的资料检索与合规检查交给 AI")

    for role, text in st.session_state.chat_history:
        with st.chat_message(role, avatar="👤" if role=="user" else "🏂"):
            st.markdown(text)

    sys_msg = """你是 Burton China 客服智能副驾。
    1. 连贯性：记住客户提供的身高/体重/鞋码，严禁重复反问。
    2. 知识库锚定：推荐必须基于手册。手册未提及则基于品牌通用知识。
    3. 格式：### 1️⃣ 🧠 客户画像分析、### 2️⃣ 📚 核心知识胶囊、### 3️⃣ 💬 建议回复话术。
    4. 合规：严禁极限词，隐藏具体价格。"""

    user_query = st.chat_input("在此输入客户问题...")
    if user_query:
        save_to_daily_log("user", user_query)
        st.session_state.chat_history.append(("user", user_query))
        with st.chat_message("user", avatar="👤"): st.markdown(user_query)

        if "cs_chat_session" not in st.session_state:
            model_instance = genai.GenerativeModel(model_name=selected_model_name, system_instruction=sys_msg)
            st.session_state.cs_chat_session = model_instance.start_chat(history=[])
        
        kb_files = st.session_state.get("gemini_files", [])
        payload = kb_files + [user_query] if st.session_state.is_first_turn else [user_query]

        try:
            with st.chat_message("assistant", avatar="🏂"):
                with st.spinner("🤖 正在深度检索知识库..."):
                    response = st.session_state.cs_chat_session.send_message(payload)
                    st.session_state.is_first_turn = False
                    save_to_daily_log("assistant", response.text)
                    safe_content, has_issue = smart_compliance_filter(response.text, st.session_state.banned_words)
                    st.markdown(safe_content)
                    st.session_state.chat_history.append(("assistant", safe_content))
                    if has_issue: st.toast("🛡️ 已标记合规风险词", icon="⚠️")
        except Exception as e:
            if "403" in str(e): st.error("⚠️ 知识库过期，请点击左侧【🔄 唤醒知识库】")
            else: st.error(f"发生异常: {e}")
else:
    st.title("🎓 AI 模拟陪练营")
    st.info("此模块功能整合中...")
