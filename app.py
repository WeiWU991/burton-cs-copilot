import streamlit as st
import google.generativeai as genai
import os
import glob
import time
from datetime import datetime
import re

# ================= 配置区 =================
st.set_page_config(page_title="Burton CS Co-pilot", page_icon="🏂", layout="wide")

KB_FOLDER = "knowledge_base"
LOG_FOLDER = "chat_logs"

# 确保日志文件夹存在
if not os.path.exists(LOG_FOLDER): os.makedirs(LOG_FOLDER)

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

# ================= 核心逻辑：每日日志系统 =================
def save_to_daily_log(role, text):
    """将对话追加到当天的日志文件中"""
    today_str = datetime.now().strftime("%Y-%m-%d")
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_filename = os.path.join(LOG_FOLDER, f"chat_log_{today_str}.txt")
    
    # 格式化存储内容
    log_entry = f"[{timestamp}] {role.upper()}:\n{text}\n{'-'*50}\n"
    
    try:
        with open(log_filename, "a", encoding="utf-8") as f:
            f.write(log_entry)
    except Exception as e:
        print(f"日志写入失败: {e}")

# ================= 核心逻辑：智能合规过滤 =================
SAFE_WORDS = {"Burton", "BURTON", "burton", "Anon", "ANON", "anon", "ak", "AK", "ak", "GORE-TEX", "Boa", "MIPS", "Step On", "Est", "Re:Flex"}
SMART_SYNONYMS = {"第一": "排名前列", "NO.1": "人气热销", "Top1": "人气热销", "冠军": "人气优选", "首选": "优选", "顶级": "高端", "最": "十分"}

@st.cache_resource
def load_banned_words():
    banned_set = set()
    txt_files = glob.glob(os.path.join(KB_FOLDER, "*.txt"))
    for txt_file in txt_files:
        try:
            with open(txt_file, "r", encoding='utf-8') as f:
                content = f.read()
                raw_words = re.split(r"[,\n\s'\"\[\]]+", content)
                for w in raw_words:
                    clean_w = w.strip()
                    if (len(clean_w) > 1 or clean_w == '最') and clean_w not in SAFE_WORDS:
                        banned_set.add(clean_w)
        except Exception: pass
    return banned_set

def highlight_banned_words(text, banned_set):
    if not banned_set: return text, False
    found = False
    for word in banned_set:
        if word in text:
            found = True
            text = text.replace(word, f":red[**🚫{word}**]")
    return text, found

def smart_compliance_filter(full_response, banned_set):
    if not banned_set: return full_response, False
    safe_text, found = highlight_banned_words(full_response, banned_set)
    return safe_text, found

@st.cache_resource
def load_knowledge_base_files():
    uploaded_refs = []
    md_files = glob.glob(os.path.join(KB_FOLDER, "*.md"))
    for file_path in md_files:
        try:
            # 重新上传时确保文件状态可查
            file_ref = genai.upload_file(path=file_path, mime_type="text/plain")
            uploaded_refs.append(file_ref)
        except Exception: pass
    return uploaded_refs

def reset_knowledge_base():
    load_knowledge_base_files.clear()
    st.session_state.kb_loaded = False
    st.rerun()

if api_key and not st.session_state.kb_loaded:
    with st.spinner("🚀 正在初始化 Burton 知识引擎..."):
        st.session_state.banned_words = load_banned_words()
        st.session_state.gemini_files = load_knowledge_base_files()
        st.session_state.kb_loaded = True

# ================= 侧边栏 =================
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/3/3b/Burton_Snowboards_logo.svg/2560px-Burton_Snowboards_logo.svg.png", width=150)
    app_mode = st.radio("🎯 核心模块:", ["💬 客服实战副驾", "🎓 AI 新星起航计划"])
    
    if st.button("🗑️ 接待新客户 (清空界面记忆)", type="primary", use_container_width=True):
        st.session_state.chat_history = []
        if "cs_chat_session" in st.session_state: del st.session_state.cs_chat_session
        st.rerun()

    st.divider()
    st.caption("🛠️ 维护与状态")
    if st.button("🔄 唤醒知识库 (修复403)", use_container_width=True):
        reset_knowledge_base()
    
    # 🔴 关键点：通过 URL 参数控制管理员功能的显示
    # 使用方式：在网页地址后面加上 ?admin=true
    is_admin = st.query_params.get("admin") == "true"
    
    if is_admin:
        st.divider()
        st.success("🔓 管理员模式已开启")
        st.caption("📂 历史日志下载")
        all_logs = sorted(glob.glob(os.path.join(LOG_FOLDER, "*.txt")), reverse=True)
        if all_logs:
            log_to_download = st.selectbox("选择日志日期", all_logs, format_func=lambda x: os.path.basename(x))
            with open(log_to_download, "rb") as f:
                st.download_button(
                    label="📥 下载选定日志",
                    data=f,
                    file_name=os.path.basename(log_to_download),
                    mime="text/plain",
                    use_container_width=True
                )
        else:
            st.info("暂无聊天记录")

# ================= 主界面 =================
st.title("🏂 Burton China AI Hub")
model = genai.GenerativeModel(model_name="gemini-1.5-flash-latest")

if app_mode == "💬 客服实战副驾":
    st.subheader("💬 实时客服支援系统")
    
    for role, text in st.session_state.chat_history:
        with st.chat_message(role, avatar="👤" if role=="user" else "🏂"):
            st.markdown(text)

    user_query = st.chat_input("在此输入客户问题...")
    if user_query:
        save_to_daily_log("user", user_query)
        st.session_state.chat_history.append(("user", user_query))
        with st.chat_message("user", avatar="👤"): st.write(user_query)

        if "cs_chat_session" not in st.session_state:
            st.session_state.cs_chat_session = model.start_chat(history=[])
            payload = st.session_state.gemini_files + [user_query]
        else:
            payload = [user_query]

        try:
            with st.chat_message("assistant", avatar="🏂"):
                with st.spinner("🤖 思考中..."):
                    response = st.session_state.cs_chat_session.send_message(payload)
                    save_to_daily_log("assistant", response.text)
                    
                    safe_text, _ = smart_compliance_filter(response.text, st.session_state.banned_words)
                    st.markdown(safe_text)
                    st.session_state.chat_history.append(("assistant", safe_text))
        except Exception as e:
            if "403" in str(e): st.error("⚠️ 知识库休眠，请点击左侧【唤醒知识库】")
            else: st.error(f"报错: {e}")
