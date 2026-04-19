import streamlit as st
import google.generativeai as genai
import os
import glob
import time
import datetime
import re

# ================= 1. 基础配置与路径校验 =================
st.set_page_config(page_title="Burton CS Co-pilot", page_icon="🏂", layout="wide")

KB_ROOT = "knowledge_base"
DIR_RULES = os.path.join(KB_ROOT, "01_rules")
DIR_TMALL = os.path.join(KB_ROOT, "02_tmall_data")
DIR_PPT   = os.path.join(KB_ROOT, "03_ppt_original")
DIR_LOGS  = "chat_logs"

# 强力初始化物理路径
for d in [DIR_RULES, DIR_TMALL, DIR_PPT, DIR_LOGS]:
    if not os.path.exists(d): 
        os.makedirs(d)

# API 密钥鉴权
try:
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
except Exception as e:
    st.error(f"❌ API KEY 配置缺失: {str(e)}")
    st.stop()

# ================= 2. 合规引擎与字典 (完全复刻备份代码逻辑) =================
SAFE_WORDS = {"Burton", "BURTON", "burton", "ak", "AK", "Step On", "GORE-TEX", "Anon"}
SMART_SYNONYMS = {
    "第一": "排名前列", "NO.1": "人气热销", "Top1": "人气热销",
    "冠军": "人气优选", "首选": "优选", "顶级": "高端",
    "顶尖": "高端", "极致": "出色", "极佳": "出色",
    "完美": "理想", "绝佳": "非常棒", "独家": "特色",
    "独有": "特有", "最强": "强力", "最好": "很好",
    "最大": "很大", "最高": "很高", "最低": "超值",
    "全网": "全渠道", "世界级": "高水准", "史无前例": "难得一见",
    "永久": "长久", "百分之百": "致力于", "必": "建议", "最": "十分"
}

@st.cache_resource
def load_banned_words():
    banned_set = set()
    txt_files = glob.glob(os.path.join(DIR_RULES, "*.txt"))
    for txt_file in txt_files:
        try:
            with open(txt_file, "r", encoding='utf-8') as f:
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
            suggestion = f" 💡建议改:{SMART_SYNONYMS[word]}" if word in SMART_SYNONYMS else ""
            text = text.replace(word, f":red[**🚫{word}**]{suggestion}")
    return text, found

def shield_banned_words(text, banned_set):
    if not banned_set: return text, False
    found = False
    for word in banned_set:
        if word in text:
            found = True
            replacement = SMART_SYNONYMS.get(word, "")
            text = text.replace(word, replacement)
    return text, found

def smart_compliance_filter(full_response, banned_set):
    """三段式过滤：话术部分屏蔽，其余部分高亮"""
    if not banned_set: return full_response, False
    header = "### 3️⃣ 💬 建议回复话术"
    next_sec = "### 4️⃣"
    parts = full_response.split(header)
    if len(parts) < 2: return highlight_banned_words(full_response, banned_set)
    
    part_before = parts[0]
    rest = parts[1]
    sub_parts = rest.split(next_sec)
    reply_content = sub_parts[0]
    part_after = next_sec + (sub_parts[1] if len(sub_parts) > 1 else "")
    
    safe_before, i1 = highlight_banned_words(part_before, banned_set)
    safe_reply, i2 = shield_banned_words(reply_content, banned_set)
    safe_after, i3 = highlight_banned_words(part_after, banned_set)
    
    return safe_before + header + safe_reply + safe_after, (i1 or i2 or i3)

# ================= 3. 数据调度：云端查重与可视化进度 =================

@st.cache_resource(show_spinner=False)
def index_knowledge_base():
    kb = {"rules": [], "tmall": {}, "ppt": []}
    
    # 物理扫描文件列表
    all_rules = glob.glob(os.path.join(DIR_RULES, "*.md"))
    all_tmall = glob.glob(os.path.join(DIR_TMALL, "*.md"))
    all_ppt = glob.glob(os.path.join(DIR_PPT, "*.md"))
    total_files = len(all_rules) + len(all_tmall) + len(all_ppt)
    
    if total_files == 0:
        return kb, 0, 0
    
    progress_bar = st.progress(0, text="🚀 正在连接 Google 云端核对指纹...")
    
    # 查重逻辑
    existing_files = {}
    try:
        for f in genai.list_files():
            if f.display_name: existing_files[f.display_name] = f
    except: pass
        
    current_count = 0
    success_count = 0

    def up(p):
        nonlocal current_count, success_count
        current_count += 1
        fn = os.path.basename(p)
        progress_bar.progress(int((current_count / total_files) * 100), text=f"🚀 [{current_count}/{total_files}] 处理中: {fn}")
        
        if fn in existing_files:
            success_count += 1
            return existing_files[fn]
        try:
            f = genai.upload_file(p, mime_type="text/plain", display_name=fn)
            wait = 0
            while f.state.name == "PROCESSING" and wait < 12:
                time.sleep(1); f = genai.get_file(f.name); wait += 1
            success_count += 1
            return f
        except: return None

    for p in all_rules:
        res = up(p)
        if res: kb["rules"].append(res)
    for p in all_tmall:
        res = up(p)
        if res: kb["tmall"][os.path.basename(p)[:6]] = res
    for p in all_ppt:
        res = up(p)
        if res: kb["ppt"].append(res)
        
    progress_bar.empty() 
    return kb, total_files, success_count

def save_to_daily_log(role, text):
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    log_path = os.path.join(DIR_LOGS, f"chat_{today}.txt")
    now = datetime.datetime.now().strftime("%H:%M:%S")
    clean_text = re.sub(r':\w+\[\*\*(.*?)\*\*\]', r'\1', text)
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{now}] {role.upper()}: {clean_text}\n{'-'*50}\n")
    except: pass

# --- 初始化加载 ---
if "kb_engine" not in st.session_state:
    st.session_state.banned_words = load_banned_words()
    kb_data, total, success = index_knowledge_base()
    if total == 0:
        st.error("❌ 未找到 Markdown 文件！请确保 knowledge_base 目录结构正确。")
        st.stop()
    st.session_state.kb_engine = kb_data
if "chat_history" not in st.session_state: 
    st.session_state.chat_history = []

# ================= 4. UI 侧边栏 (全面找回功能) =================
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/3/3b/Burton_Snowboards_logo.svg/2560px-Burton_Snowboards_logo.svg.png", width=120)
    
    app_mode = st.radio("🎯 功能模块:", ["💬 客服实战副驾", "🎓 AI 模拟陪练营"])
    
    if st.button("🗑️ 接待新客户 (清空记忆)", use_container_width=True, type="primary"):
        st.session_state.chat_history = []
        if "cs_session" in st.session_state: del st.session_state.cs_session
        st.rerun()

    st.divider()
    with st.expander("🔐 管理员日志系统"):
        pwd = st.text_input("输入密令:", type="password")
        if pwd == "burton2026":
            st.success("验证成功")
            logs = sorted(glob.glob(os.path.join(DIR_LOGS, "*.txt")), reverse=True)
            if logs:
                selected = st.selectbox("选择日期", logs, format_func=lambda x: os.path.basename(x))
                with open(selected, "rb") as f:
                    st.download_button("📥 下载选定日志", f, file_name=os.path.basename(selected), use_container_width=True)

# ================= 5. 实战/培训逻辑 (Gemini 3 适配) =================
MODEL_ID = "gemini-3-flash-preview"
SYS_PROMPT = """你是 Burton China 客服专家。
1. 查尺码/参数必须提供 6 位货号。
2. Step On 男女款严禁混用！
3. 格式：### 1️⃣ 画像、### 2️⃣ 知识胶囊、### 3️⃣ 💬 建议回复话术、### 4️⃣ 关联推荐。
4. 严格防幻觉，不脑补资料外的数据。"""

if app_mode == "💬 客服实战副驾":
    st.title("🏂 Burton 实战副驾")
    for role, text in st.session_state.chat_history:
        with st.chat_message(role, avatar="👤" if role=="user" else "🏂"):
            safe_display, _ = smart_compliance_filter(text, st.session_state.banned_words)
            st.markdown(safe_display)

    query = st.chat_input("查尺码请附带 6 位货号...")
    if query:
        save_to_daily_log("user", query)
        with st.chat_message("user", avatar="👤"): st.write(query)
        
        # 提取货号进行路由
        ids = list(set(re.findall(r'(?<!\d)\d{6,15}(?!\d)', query)))
        bids = [n[:6] for n in ids]
        
        payload = []
        payload.extend(st.session_state.kb_engine["rules"])
        hit = False
        for b in bids:
            if b in st.session_state.kb_engine["tmall"]:
                payload.append(st.session_state.kb_engine["tmall"][b]); hit = True
        if not hit: payload.extend(st.session_state.kb_engine["ppt"])
        payload.append(query)

        if "cs_session" not in st.session_state:
            model = genai.GenerativeModel(MODEL_ID, system_instruction=SYS_PROMPT)
            st.session_state.cs_session = model.start_chat(history=[])

        try:
            with st.chat_message("assistant", avatar="🏂"):
                with st.spinner("🤖 正在检索多级知识库..."):
                    resp = st.session_state.cs_session.send_message(payload)
                    final_text, has_issue = smart_compliance_filter(resp.text, st.session_state.banned_words)
                    st.markdown(final_text)
                    if has_issue: st.toast("🛡️ 已处理合规词", icon="✅")
                    save_to_daily_log("assistant", resp.text)
                    st.session_state.chat_history.append(("user", query))
                    st.session_state.chat_history.append(("assistant", resp.text))
        except Exception as e:
            st.error(f"检索失败: {e}")

elif app_mode == "🎓 AI 模拟陪练营":
    st.title("🎓 模拟陪练营")
    if st.button("🎲 生成本周挑战"):
        with st.spinner("导师出题中..."):
            model = genai.GenerativeModel(MODEL_ID)
            kb = st.session_state.kb_engine["rules"] + st.session_state.kb_engine["ppt"]
            resp = model.generate_content(kb + ["根据知识库生成一个带陷阱的滑雪装备咨询场景，直接输出客户说的话。"])
            st.session_state.scen = resp.text
            st.rerun()
    if "scen" in st.session_state:
        st.info(st.session_state.scen)
        reply = st.text_area("✍️ 你的回复:")
        if st.button("📝 提交批改"):
            model = genai.GenerativeModel(MODEL_ID)
            kb = st.session_state.kb_engine["rules"] + st.session_state.kb_engine["ppt"]
            eval_resp = model.generate_content(kb + [f"场景：{st.session_state.scen}\n回复：{reply}\n请点评打分并给出示范。"])
            st.markdown(eval_resp.text)
