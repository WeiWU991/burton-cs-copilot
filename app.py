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

# ================= 2. 合规与日志逻辑 =================
SAFE_WORDS = {"Burton", "BURTON", "burton", "Anon", "ANON", "anon", "ak", "AK", "[ak]", "GORE-TEX", "Boa", "MIPS", "Step On", "Est", "Re:Flex"}
SMART_SYNONYMS = {"第一": "排名前列", "NO.1": "人气热销", "Top1": "人气热销", "冠军": "人气优选", "首选": "优选", "顶级": "高端", "顶尖": "高端", "极致": "出色", "极佳": "出色", "完美": "理想", "绝佳": "非常棒", "独家": "特色", "独有": "特有", "最强": "强力", "最好": "很好", "最大": "很大", "最高": "很高", "最低": "超值", "全网": "全渠道", "史无前例": "难得一见", "必": "建议", "最": "十分"}

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

def smart_compliance_filter(full_response, banned_set):
    if not banned_set: return full_response, False
    parts = full_response.split("### 3️⃣ 💬 建议回复话术")
    if len(parts) < 2: return full_response, False
    # 静默替换建议回复部分
    reply_content = parts[1]
    found = False
    for word, syn in SMART_SYNONYMS.items():
        if word in reply_content:
            reply_content = reply_content.replace(word, syn)
            found = True
    return parts[0] + "### 3️⃣ 💬 建议回复话术" + reply_content, found

def save_to_daily_log(role, text):
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    log_path = os.path.join(DIR_LOGS, f"chat_{today}.txt")
    now = datetime.datetime.now().strftime("%H:%M:%S")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"[{now}] {role.upper()}: {text}\n{'-'*50}\n")

# ================= 3. 数据加载与云端查重 =================
@st.cache_resource(show_spinner=False)
def index_knowledge_base():
    kb = {"rules": [], "tmall": {}, "ppt": []}
    all_files = glob.glob(os.path.join(KB_ROOT, "**/*.md", recursive=True))
    if not all_files: return kb, 0, 0
    
    existing = {f.display_name: f for f in genai.list_files()}
    progress_bar = st.progress(0, text="🚀 正在同步 Google 云端知识库...")
    
    total = len(all_files)
    count = 0
    success = 0

    def up_process(p):
        nonlocal count, success
        count += 1
        fn = os.path.basename(p)
        progress_bar.progress(int((count/total)*100), text=f"🚀 同步中 [{count}/{total}]: {fn}")
        if fn in existing: 
            success += 1
            return existing[fn]
        try:
            f = genai.upload_file(p, mime_type="text/plain", display_name=fn)
            while f.state.name == "PROCESSING": time.sleep(1); f = genai.get_file(f.name)
            success += 1
            return f
        except: return None

    # 按层级重新分拣（基于你设计的文件夹结构）
    for p in glob.glob(os.path.join(DIR_RULES, "*.md")):
        res = up_process(p)
        if res: kb["rules"].append(res)
    for p in glob.glob(os.path.join(DIR_TMALL, "*.md")):
        bid = os.path.basename(p)[:6]
        res = up_process(p)
        if res: kb["tmall"][bid] = res
    for p in glob.glob(os.path.join(DIR_PPT, "*.md")):
        res = up_process(p)
        if res: kb["ppt"].append(res)

    progress_bar.empty()
    return kb, total, success

# --- 初始化 ---
if "kb_engine" not in st.session_state:
    st.session_state.banned_words = load_banned_words()
    kb_data, total, success = index_knowledge_base()
    if total == 0: st.error("❌ 未找到知识库文件！"); st.stop()
    st.session_state.kb_engine = kb_data
if "chat_history" not in st.session_state: st.session_state.chat_history = []

# ================= 4. UI 侧边栏 =================
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/3/3b/Burton_Snowboards_logo.svg/2560px-Burton_Snowboards_logo.svg.png", width=120)
    app_mode = st.radio("🎯 模式:", ["💬 实战副驾", "🎓 陪练营"])
    if st.button("🗑️ 清空记忆"):
        st.session_state.chat_history = []
        if "session" in st.session_state: del st.session_state.session
        st.rerun()
    st.divider()
    with st.expander("🔐 日志"):
        pwd = st.text_input("密令:", type="password")
        if pwd == "burton2026":
            logs = sorted(glob.glob(os.path.join(DIR_LOGS, "*.txt")), reverse=True)
            if logs:
                with open(logs[0], "rb") as f:
                    st.download_button("📥 下载今日日志", f, file_name=os.path.basename(logs[0]))

# ================= 5. 实战/培训逻辑 (Gemini 3 适配版) =================
sys_instruction = "你是 Burton 专家。尺码查询必须有 ID。严禁脑补资料外的数据。Step On 严禁男女混用。"

def get_model():
    """Gemini 3 模型获取器，带自动回退机制"""
    try:
        return genai.GenerativeModel("gemini-3-flash", system_instruction=sys_instruction)
    except:
        return genai.GenerativeModel("gemini-3-flash-preview", system_instruction=sys_instruction)

if app_mode == "💬 实战副驾":
    st.title("🏂 Burton 实战副驾")
    for r, t in st.session_state.chat_history:
        with st.chat_message(r): st.markdown(t)

    query = st.chat_input("查尺码请带货号...")
    if query:
        save_to_daily_log("user", query)
        with st.chat_message("user"): st.write(query)
        
        # ID 路由
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

        if "session" not in st.session_state:
            st.session_state.session = get_model().start_chat(history=[])

        with st.chat_message("assistant"):
            with st.spinner("AI 正在思考..."):
                resp = st.session_state.session.send_message(payload)
                final_text, _ = smart_compliance_filter(resp.text, st.session_state.banned_words)
                st.markdown(final_text)
                save_to_daily_log("assistant", final_text)
                st.session_state.chat_history.append(("user", query))
                st.session_state.chat_history.append(("assistant", final_text))

elif app_mode == "🎓 陪练营":
    st.title("🎓 陪练营")
    # 培训营逻辑同前，调用 get_model() 即可
    if st.button("🎲 开始挑战"):
        with st.spinner("生成场景中..."):
            training_kb = st.session_state.kb_engine["rules"] + st.session_state.kb_engine["ppt"]
            prompt = "生成一个滑雪装备咨询场景，带陷阱。直接输出对话。"
            resp = get_model().generate_content(training_kb + [prompt])
            st.session_state.scenario = resp.text
            st.rerun()
    if "scenario" in st.session_state:
        st.info(st.session_state.scenario)
        # 批改逻辑同实战，调用 get_model()
