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

# 自动创建必要文件夹
for d in [DIR_RULES, DIR_TMALL, DIR_PPT, DIR_LOGS]:
    if not os.path.exists(d): os.makedirs(d)

try:
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
except:
    st.error("❌ API KEY 未配置，请检查 secrets.toml")
    st.stop()

# ================= 2. 合规引擎与日志逻辑 (完全保留你的UI逻辑) =================
SAFE_WORDS = {"Burton", "BURTON", "burton", "ak", "AK", "Step On", "GORE-TEX", "Anon"}
SMART_SYNONYMS = {"第一": "热销", "NO.1": "人气款", "顶级": "高端", "最": "十分", "极致": "出色", "完美": "理想"}

@st.cache_resource
def load_banned_words():
    banned_set = set()
    for p in glob.glob(os.path.join(DIR_RULES, "*.txt")):
        try:
            with open(p, "r", encoding='utf-8') as f:
                content = f.read()
                raw_words = re.split(r"[,\n\s'\"\[\]]+", content)
                for w in raw_words:
                    clean_w = w.strip()
                    if len(clean_w) > 1 or clean_w == '最':
                        if clean_w not in SAFE_WORDS: banned_set.add(clean_w)
        except: pass
    return banned_set

def highlight_banned_words(text, banned_set):
    if not banned_set: return text, False
    found = False
    for word in banned_set:
        if word in text:
            found = True
            text = text.replace(word, f":red[**🚫{word}**]")
    return text, found

def shield_banned_words(text, banned_set):
    found = False
    for word, syn in SMART_SYNONYMS.items():
        if word in text:
            text = text.replace(word, syn)
            found = True
    return text, found

def save_to_daily_log(role, text):
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    log_path = os.path.join(DIR_LOGS, f"chat_{today}.txt")
    now = datetime.datetime.now().strftime("%H:%M:%S")
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{now}] {role.upper()}: {text}\n{'-'*50}\n")
    except: pass

# ================= 3. 数据调度：云端查重索引 =================
@st.cache_resource(show_spinner=False)
def index_knowledge_base():
    kb = {"rules": [], "tmall": {}, "ppt": []}
    all_files = glob.glob(os.path.join(KB_ROOT, "**/*.md", recursive=True))
    if not all_files: return kb, 0
    
    existing = {f.display_name: f for f in genai.list_files()}
    progress_bar = st.progress(0, text="🚀 正在根据 AI Studio 规范同步同步云端知识库...")
    
    total = len(all_files)
    count = 0
    for p in all_files:
        fn = os.path.basename(p)
        count += 1
        progress_bar.progress(int((count/total)*100), text=f"🚀 正在核对: {fn}")
        
        f_obj = None
        if fn in existing: f_obj = existing[fn]
        else:
            try:
                f_obj = genai.upload_file(p, mime_type="text/plain", display_name=fn)
                while f_obj.state.name == "PROCESSING": time.sleep(1); f_obj = genai.get_file(f_obj.name)
            except: continue
        
        if f_obj:
            if DIR_RULES in p: kb["rules"].append(f_obj)
            elif DIR_TMALL in p: kb["tmall"][fn[:6]] = f_obj
            elif DIR_PPT in p: kb["ppt"].append(f_obj)
            
    progress_bar.empty()
    return kb, total

# --- 初始化 ---
if "kb_engine" not in st.session_state:
    st.session_state.banned_words = load_banned_words()
    kb_data, total = index_knowledge_base()
    st.session_state.kb_engine = kb_data
if "chat_history" not in st.session_state: st.session_state.chat_history = []

# ================= 4. UI 侧边栏 (全面找回功能) =================
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/3/3b/Burton_Snowboards_logo.svg/2560px-Burton_Snowboards_logo.svg.png", width=120)
    st.write("✨ 引擎版本: `gemini-3-flash`")
    
    app_mode = st.radio("🎯 功能模块切换:", ["💬 客服实战副驾", "🎓 AI 模拟陪练营"])
    
    if st.button("🗑️ 清空当前对话记忆", use_container_width=True):
        st.session_state.chat_history = []
        if "cs_session" in st.session_state: del st.session_state.cs_session
        st.rerun()
    
    st.divider()
    with st.expander("🔐 内部日志下载"):
        pwd = st.text_input("请输入管理密令:", type="password")
        if pwd == "burton2026":
            logs = sorted(glob.glob(os.path.join(DIR_LOGS, "*.txt")), reverse=True)
            if logs:
                with open(logs[0], "rb") as f:
                    st.download_button("📥 点击下载今日日志文件", f, file_name=os.path.basename(logs[0]))
            else:
                st.info("今日暂无通话记录")

# ================= 5. 核心业务逻辑 =================
# 严格遵循 AI Studio 命名
MODEL_ID = "gemini-3-flash"
SYS_PROMPT = """你是 Burton 资深产品专家。
1. 查尺码/参数必须要求 6 位货号。
2. 格式：### 1️⃣ 画像、### 2️⃣ 知识、### 3️⃣ 话术、### 4️⃣ 推荐。
3. 严格遵循挂载文档，严禁胡编。"""

if app_mode == "💬 客服实战副驾":
    st.title("🏂 Burton 客服实战副驾")
    for r, t in st.session_state.chat_history:
        with st.chat_message(r, avatar="👤" if r=="user" else "🏂"): st.markdown(t)

    query = st.chat_input("查尺码请输入货号数字...")
    if query:
        save_to_daily_log("user", query)
        with st.chat_message("user", avatar="👤"): st.write(query)
        
        # ID 路由逻辑
        ids = list(set(re.findall(r'(?<!\d)\d{6,15}(?!\d)', query)))
        bids = [n[:6] for n in ids]
        
        payload = []
        payload.extend(st.session_state.kb_engine["rules"])
        tmall_hit = False
        for b in bids:
            if b in st.session_state.kb_engine["tmall"]:
                payload.append(st.session_state.kb_engine["tmall"][b])
                tmall_hit = True
        if not tmall_hit: payload.extend(st.session_state.kb_engine["ppt"])
        payload.append(query)

        if "cs_session" not in st.session_state:
            # 这里的实例化严格使用 gemini-3-flash
            model = genai.GenerativeModel(MODEL_ID, system_instruction=SYS_PROMPT)
            st.session_state.cs_session = model.start_chat(history=[])

        with st.chat_message("assistant", avatar="🏂"):
            with st.spinner("🤖 正在检索多级知识库..."):
                resp = st.session_state.cs_session.send_message(payload)
                
                # 合规处理：拆分处理，话术部分屏蔽，其余部分高亮
                content = resp.text
                if "### 3️⃣ 💬 建议回复话术" in content:
                    parts = content.split("### 3️⃣ 💬 建议回复话术")
                    p1 = highlight_banned_words(parts[0], st.session_state.banned_words)[0]
                    p2 = shield_banned_words(parts[1], st.session_state.banned_words)[0]
                    final_text = p1 + "### 3️⃣ 💬 建议回复话术" + p2
                else:
                    final_text = highlight_banned_words(content, st.session_state.banned_words)[0]
                
                st.markdown(final_text)
                save_to_daily_log("assistant", final_text)
                st.session_state.chat_history.append(("user", query))
                st.session_state.chat_history.append(("assistant", final_text))

elif app_mode == "🎓 AI 模拟陪练营":
    st.title("🎓 模拟陪练营")
    st.write("基于核心铁律和 PPT 课件进行情景模拟。")
    if st.button("🎲 开启本节科目挑战", use_container_width=True):
        model = genai.GenerativeModel(MODEL_ID)
        training_kb = st.session_state.kb_engine["rules"] + st.session_state.kb_engine["ppt"]
        resp = model.generate_content(training_kb + ["请根据知识库生成一个滑雪装备咨询场景，带陷阱。直接输出对话。"])
        st.session_state.train_scen = resp.text
        st.rerun()
        
    if "train_scen" in st.session_state:
        st.info(st.session_state.train_scen)
        reply = st.text_area("✍️ 你的回复话术:")
        if st.button("📝 提交导师批改", use_container_width=True):
            model = genai.GenerativeModel(MODEL_ID)
            training_kb = st.session_state.kb_engine["rules"] + st.session_state.kb_engine["ppt"]
            eval_resp = model.generate_content(training_kb + [f"场景：{st.session_state.train_scen}\n员工回复：{reply}\n请点评打分并给出示范话术。"])
            st.markdown(eval_resp.text)
