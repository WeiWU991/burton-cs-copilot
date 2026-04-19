import streamlit as st
import google.generativeai as genai
import os
import glob
import time
import datetime
import re

# ================= 1. 基础配置 =================
st.set_page_config(page_title="Burton CS Co-pilot", page_icon="🏂", layout="wide")

KB_ROOT = "knowledge_base"
DIR_RULES = os.path.join(KB_ROOT, "01_rules")
DIR_TMALL = os.path.join(KB_ROOT, "02_tmall_data")
DIR_PPT   = os.path.join(KB_ROOT, "03_ppt_original")
DIR_LOGS  = "chat_logs"

for d in [DIR_RULES, DIR_TMALL, DIR_PPT, DIR_LOGS]:
    if not os.path.exists(d): os.makedirs(d)

try:
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
except:
    st.error("❌ API KEY 未配置")
    st.stop()

# ================= 2. 核心架构：模型智能选择器 =================
def get_best_available_model(instruction):
    """自动嗅探并返回当前 API 权限下最强且可用的模型 ID"""
    # 按优先级排列 2026 年常用模型名
    candidate_models = [
        "gemini-2.0-flash", 
        "gemini-1.5-flash",
        "gemini-1.5-pro"
    ]
    
    # 尝试列出当前账号可用的所有模型
    try:
        available_ids = [m.name for m in genai.list_models()]
        for target in candidate_models:
            full_name = f"models/{target}"
            if full_name in available_ids:
                return genai.GenerativeModel(target, system_instruction=instruction)
    except:
        pass
    
    # 万一 list_models 失败，回退到最稳妥的 ID
    return genai.GenerativeModel("gemini-1.5-flash", system_instruction=instruction)

# ================= 3. 合规与日志逻辑 =================
SMART_SYNONYMS = {"第一": "热销", "NO.1": "人气款", "顶级": "高端", "最": "十分", "极致": "出色"}

def smart_compliance_filter(text, banned_set):
    if "### 3️⃣ 💬 建议回复话术" not in text: return text, False
    parts = text.split("### 3️⃣ 💬 建议回复话术")
    reply = parts[1]
    found = False
    for word, syn in SMART_SYNONYMS.items():
        if word in reply:
            reply = reply.replace(word, syn)
            found = True
    return parts[0] + "### 3️⃣ 💬 建议回复话术" + reply, found

def save_to_daily_log(role, text):
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    log_path = os.path.join(DIR_LOGS, f"chat_{today}.txt")
    now = datetime.datetime.now().strftime("%H:%M:%S")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"[{now}] {role.upper()}: {text}\n{'-'*50}\n")

# ================= 4. 数据加载与云端查重 =================
@st.cache_resource(show_spinner=False)
def index_knowledge_base():
    kb = {"rules": [], "tmall": {}, "ppt": []}
    all_files = []
    for d in [DIR_RULES, DIR_TMALL, DIR_PPT]:
        all_files.extend(glob.glob(os.path.join(d, "*.md")))
    
    if not all_files: return kb, 0, 0
    
    existing = {f.display_name: f for f in genai.list_files()}
    progress_bar = st.progress(0, text="🚀 同步云端知识库...")
    
    total = len(all_files)
    count = 0
    success = 0

    def up_process(p, category):
        nonlocal count, success
        count += 1
        fn = os.path.basename(p)
        progress_bar.progress(int((count/total)*100), text=f"🚀 [{count}/{total}] 同步: {fn}")
        
        f_obj = None
        if fn in existing: 
            f_obj = existing[fn]
            success += 1
        else:
            try:
                f_obj = genai.upload_file(p, mime_type="text/plain", display_name=fn)
                while f_obj.state.name == "PROCESSING": time.sleep(1); f_obj = genai.get_file(f_obj.name)
                success += 1
            except: pass
            
        if f_obj:
            if category == "rules": kb["rules"].append(f_obj)
            elif category == "tmall": kb["tmall"][fn[:6]] = f_obj
            elif category == "ppt": kb["ppt"].append(f_obj)

    for p in glob.glob(os.path.join(DIR_RULES, "*.md")): up_process(p, "rules")
    for p in glob.glob(os.path.join(DIR_TMALL, "*.md")): up_process(p, "tmall")
    for p in glob.glob(os.path.join(DIR_PPT, "*.md")): up_process(p, "ppt")

    progress_bar.empty()
    return kb, total, success

# --- 初始化 ---
if "kb_engine" not in st.session_state:
    kb_data, total, success = index_knowledge_base()
    if total == 0: st.error("❌ 没找到 MD 文件"); st.stop()
    st.session_state.kb_engine = kb_data
if "chat_history" not in st.session_state: st.session_state.chat_history = []

# ================= 5. UI 与业务逻辑 =================
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/3/3b/Burton_Snowboards_logo.svg/2560px-Burton_Snowboards_logo.svg.png", width=120)
    app_mode = st.radio("🎯 模式:", ["💬 实战副驾", "🎓 陪练营"])
    if st.button("🗑️ 清空记忆"):
        st.session_state.chat_history = []
        if "cs_session" in st.session_state: del st.session_state.cs_session
        st.rerun()

sys_instruction = """你是 Burton 客服专家。
1. 查尺码必带 ID，没 ID 必向用户索要。
2. 严禁脑补资料外数据。
3. 格式：### 1️⃣ 画像、### 2️⃣ 知识、### 3️⃣ 话术、### 4️⃣ 推荐。"""

if app_mode == "💬 实战副驾":
    st.title("🏂 Burton 实战副驾")
    for r, t in st.session_state.chat_history:
        with st.chat_message(r): st.markdown(t)

    query = st.chat_input("查尺码请带货号...")
    if query:
        save_to_daily_log("user", query)
        with st.chat_message("user"): st.write(query)
        
        target_ids = list(set(re.findall(r'(?<!\d)\d{6,15}(?!\d)', query)))
        target_ids = [n[:6] for n in target_ids]
        
        payload = []
        payload.extend(st.session_state.kb_engine["rules"])
        tmall_hit = False
        for bid in target_ids:
            if bid in st.session_state.kb_engine["tmall"]:
                payload.append(st.session_state.kb_engine["tmall"][bid])
                tmall_hit = True
        if not tmall_hit: payload.extend(st.session_state.kb_engine["ppt"])
        payload.append(query)

        if "cs_session" not in st.session_state:
            model = get_best_available_model(sys_instruction)
            st.session_state.cs_session = model.start_chat(history=[])

        with st.chat_message("assistant"):
            with st.spinner("AI 正在思考..."):
                resp = st.session_state.cs_session.send_message(payload)
                final_text, _ = smart_compliance_filter(resp.text, None)
                st.markdown(final_text)
                save_to_daily_log("assistant", final_text)
                st.session_state.chat_history.append(("user", query))
                st.session_state.chat_history.append(("assistant", final_text))

elif app_mode == "🎓 陪练营":
    st.title("🎓 陪练营")
    if st.button("🎲 生成随机挑战"):
        with st.spinner("生成场景中..."):
            training_kb = st.session_state.kb_engine["rules"] + st.session_state.kb_engine["ppt"]
            prompt = "生成一个滑雪装备咨询场景，带陷阱。直接输出对话。"
            model = get_best_available_model("你是个培训导师")
            resp = model.generate_content(training_kb + [prompt])
            st.session_state.scenario = resp.text
            st.rerun()
    if "scenario" in st.session_state:
        st.info(st.session_state.scenario)
        trainee_reply = st.text_area("✍️ 你的回复:")
        if st.button("📝 提交"):
            model = get_best_available_model("你是个评审专家")
            training_kb = st.session_state.kb_engine["rules"] + st.session_state.kb_engine["ppt"]
            eval_prompt = f"场景：{st.session_state.scenario}\n回复：{trainee_reply}\n请点评打分并给出示范话术。"
            eval_resp = model.generate_content(training_kb + [eval_prompt])
            st.markdown(eval_resp.text)
