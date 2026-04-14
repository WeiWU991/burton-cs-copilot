import streamlit as st
import google.generativeai as genai
import os
import glob
import time
import datetime
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
    api_status = "✅ 系统核心已连接"
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

# ================= 2. 核心功能：货号前缀拦截器 (重点更新) =================
def normalize_product_id(query):
    """
    智能处理货号逻辑：
    - 6位数字：触发前缀匹配，搜索所有相关变体。
    - 7位及以上数字：截取前6位，锁定核心产品。
    """
    # 查找所有数字串
    all_numbers = re.findall(r'\b\d{6,15}\b', query)
    if not all_numbers:
        return query
    
    hints = []
    for num in all_numbers:
        base_id = num[:6]
        if len(num) == 6:
            hints.append(f"货号 {num} 是 Base ID。请检索知识库中所有以 {num} 开头的产品条目。")
        else:
            hints.append(f"货号 {num} 的核心 Base ID 是 {base_id}。请忽略颜色码，以此前缀进行检索。")
    
    hint_text = f"\n\n(⚙️系统增强指令：请注意，提问中涉及核心货号：{', '.join(hints)}。请确保检索结果涵盖该前缀下的所有匹配项。)"
    return query + hint_text

# ================= 3. 日志、合规与自愈逻辑 (保持原样) =================
def save_to_daily_log(role, text):
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    log_filename = os.path.join(LOG_FOLDER, f"chat_log_{today_str}.txt")
    clean_text = re.sub(r':\w+\[\*\*(.*?)\*\*\]', r'\1', text)
    log_entry = f"[{timestamp}] {role.upper()}:\n{clean_text}\n{'-'*60}\n"
    try:
        with open(log_filename, "a", encoding="utf-8") as f:
            f.write(log_entry)
    except: pass

def reset_knowledge_base():
    load_knowledge_base_files.clear()
    load_banned_words.clear()
    st.session_state.kb_loaded = False
    if "cs_chat_session" in st.session_state: del st.session_state.cs_chat_session
    st.session_state.is_first_turn = True
    st.rerun()

# [此处省略合规过滤和加载文件的代码，确保与您之前的版本一致即可]
# @st.cache_resource 
# def load_banned_words()...
# def smart_compliance_filter()...
# def load_knowledge_base_files()...

# ================= 4. 初始化加载 =================
if api_key and not st.session_state.kb_loaded:
    with st.spinner("🚀 初始化 Burton 引擎..."):
        # 假设之前的 load_banned_words 和 load_knowledge_base_files 已定义
        st.session_state.kb_loaded = True

# ================= 5. 侧边栏与管理模块 =================
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/3/3b/Burton_Snowboards_logo.svg/2560px-Burton_Snowboards_logo.svg.png", width=150)
    app_mode = st.radio("🎯 核心功能模块:", ["💬 客服实战副驾", "🎓 AI 模拟陪练营"])
    
    if st.button("🗑️ 接待新客户 (清空记忆)", type="primary", use_container_width=True):
        st.session_state.chat_history = []
        st.session_state.is_first_turn = True
        if "cs_chat_session" in st.session_state: del st.session_state.cs_chat_session
        st.rerun()

    st.divider()
    if api_key: st.success("✅ 系统核心已连接")
    if st.button("🔄 唤醒知识库 (修复403)", use_container_width=True):
        reset_knowledge_base()

    st.divider()
    model_choice = st.radio("🧠 大脑引擎:", ("⚡ 极速模式 (Flash)", "🐢 深度思考 (Pro)"), index=0)
    selected_model_name = "gemini-3-flash-preview" if "Flash" in model_choice else "gemini-3-pro-preview"

    # 管理员日志入口
    with st.expander("🔐 内部日志系统"):
        admin_pwd = st.text_input("请输入密令:", type="password")
        if admin_pwd == "burton2026":
            st.success("验证通过")
            # [此处放入日志下载逻辑]

# ================= 6. 主界面 =================
if app_mode == "💬 客服实战副驾":
    st.title("🏂 Burton 客服副驾")
    
    # 渲染历史
    for role, text in st.session_state.chat_history:
        with st.chat_message(role, avatar="👤" if role=="user" else "🏂"):
            st.markdown(text)

    sys_msg = """
    你是 Burton China 客服智能副驾。
    1. 货号前缀匹配：Burton 货号的核心是前 6 位数字。如果系统提示中包含 Base ID 或前缀指令，请务必检索知识库中所有以此开头的记录。
    2. 跨类目保护：若产品从【成人】切换到【儿童】（或反之），必须立即忽略上文的年龄/性别记忆。儿童雪板严禁匹配成人固定器！
    3. 输出格式：包含画像分析、知识胶囊、回复话术、关联销售。
    """

    user_query = st.chat_input("输入问题或货号...")
    if user_query:
        save_to_daily_log("user", user_query)
        with st.chat_message("user", avatar="👤"): st.write(user_query)

        # 核心拦截处理
        processed_query = normalize_product_id(user_query)

        if "cs_chat_session" not in st.session_state:
            model_instance = genai.GenerativeModel(model_name=selected_model_name, system_instruction=sys_msg)
            st.session_state.cs_chat_session = model_instance.start_chat(history=[])
        
        payload = st.session_state.get("gemini_files", []) + [processed_query] if st.session_state.is_first_turn else [processed_query]

        try:
            with st.chat_message("assistant", avatar="🏂"):
                with st.spinner("🤖 正在检索知识库..."):
                    response = st.session_state.cs_chat_session.send_message(payload)
                    st.session_state.is_first_turn = False
                    save_to_daily_log("assistant", response.text)
                    st.markdown(response.text)
                    st.session_state.chat_history.append(("user", user_query))
                    st.session_state.chat_history.append(("assistant", response.text))
        except Exception as e:
            st.error(f"发生异常: {e}")
