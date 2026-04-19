import streamlit as st
import google.generativeai as genai
import os, glob, time, datetime, re

# ================= 1. 基础配置与路径统一 =================
st.set_page_config(page_title="Burton CS Co-pilot", page_icon="🏂", layout="wide")

# 统一物理路径变量名
KB_ROOT = "knowledge_base"
DIR_RULES = os.path.join(KB_ROOT, "01_rules")
DIR_TMALL = os.path.join(KB_ROOT, "02_tmall_data")
DIR_PPT   = os.path.join(KB_ROOT, "03_ppt_original")
DIR_LOGS  = "chat_logs"

# 自动创建缺失的文件夹
for d in [DIR_RULES, DIR_TMALL, DIR_PPT, DIR_LOGS]:
    if not os.path.exists(d): os.makedirs(d)

# API 鉴权
try:
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
except:
    st.error("❌ API KEY 配置缺失，请检查 secrets 配置！")
    st.stop()

# ================= 2. 核心功能：合规过滤与日志系统 =================

@st.cache_resource
def load_banned_words():
    """从 01_rules 文件夹加载敏感词库"""
    banned_set = set()
    paths = glob.glob(os.path.join(DIR_RULES, "banned_words.txt"))
    if paths:
        with open(paths[0], "r", encoding="utf-8") as f:
            for line in f:
                word = line.strip()
                if word: banned_set.add(word)
    return banned_set

def smart_compliance_filter(text, banned_set):
    """合规引擎：针对建议话术部分进行极限词静默替换"""
    if not banned_set: return text, False
    found = False
    processed_text = text
    if "### 3️⃣ 💬 建议回复话术" in text:
        parts = text.split("### 3️⃣ 💬 建议回复话术")
        reply_part = parts[1]
        for word in banned_set:
            if word in reply_part:
                found = True
                reply_part = reply_part.replace(word, " [已合规处理] ")
        processed_text = parts[0] + "### 3️⃣ 💬 建议回复话术" + reply_part
    return processed_text, found

def save_to_daily_log(role, text):
    """自动按天同步日志到文件夹"""
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    now = datetime.datetime.now().strftime("%H:%M:%S")
    log_path = os.path.join(DIR_LOGS, f"chat_{today}.txt")
    # 移除 Markdown 渲染标签再存入日志
    clean_text = re.sub(r':\w+\[\*\*(.*?)\*\*\]', r'\1', text)
    entry = f"[{now}] {role.upper()}:\n{clean_text}\n{'-'*50}\n"
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(entry)
    except:
        pass

# ================= 3. 数据调度：多级文件索引 =================

@st.cache_resource
def index_knowledge_base():
    """将物理文件分类映射到 Gemini 缓存中"""
    kb = {"rules": [], "tmall": {}, "ppt": []}
    
    def up(p):
        f = genai.upload_file(p, mime_type="text/plain")
        while f.state.name == "PROCESSING": 
            time.sleep(1)
            f = genai.get_file(f.name)
        return f

    # 1. 加载全局规则
    for p in glob.glob(os.path.join(DIR_RULES, "*.md")):
        kb["rules"].append(up(p))
        
    # 2. 加载天猫精调 (截取前6位ID作为索引)
    for p in glob.glob(os.path.join(DIR_TMALL, "*.md")):
        bid = os.path.basename(p)[:6]
        kb["tmall"][bid] = up(p)
        
    # 3. 加载大杂烩PPT (兜底语义搜索)
    for p in glob.glob(os.path.join(DIR_PPT, "*.md")):
        kb["ppt"].append(up(p))
    
    return kb

# 初始化系统状态
if "chat_history" not in st.session_state: st.session_state.chat_history = []
if "kb_engine" not in st.session_state:
    with st.spinner("🚀 正在同步核心数据源，请稍候..."):
        st.session_state.kb_engine = index_knowledge_base()
        st.session_state.banned_words = load_banned_words()

# ================= 4. UI 侧边栏 =================

with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/3/3b/Burton_Snowboards_logo.svg/2560px-Burton_Snowboards_logo.svg.png", width=120)
    st.title("🏂 系统控制台")
    
    if st.button("🗑️ 接待新客户 (清空记忆)", use_container_width=True):
        st.session_state.chat_history = []
        if "session" in st.session_state: del st.session_state.session
        st.rerun()

    st.divider()
    with st.expander("🔐 内部日志管理 (需密令)"):
        pwd = st.text_input("输入密令:", type="password")
        if pwd == "burton2026":
            st.success("验证成功")
            logs = sorted(glob.glob(os.path.join(DIR_LOGS, "*.txt")), reverse=True)
            if logs:
                selected = st.selectbox("选择日期", logs, format_func=lambda x: os.path.basename(x))
                with open(selected, "rb") as f:
                    st.download_button("📥 下载选定日志", f, file_name=os.path.basename(selected), use_container_width=True)

# ================= 5. 主业务流：动态路由与生成 =================

st.title("🏂 Burton 客服实战副驾")

for role, text in st.session_state.chat_history:
    with st.chat_message(role, avatar="👤" if role=="user" else "🏂"):
        st.markdown(text)

# 底部输入框
prompt_placeholder = "🎯 查尺码/参数请务必附带 6 位货号..."
query = st.chat_input(prompt_placeholder)

if query:
    save_to_daily_log("user", query)
    with st.chat_message("user", avatar="👤"): st.write(query)
    
    # 货号提取 (正则：滑动窗口扫描当前问题 + 上下文)
    scan_text = query
    if st.session_state.chat_history: 
        scan_text += " " + st.session_state.chat_history[-1][1]
        
    target_ids = list(set(re.findall(r'(?<!\d)\d{6,15}(?!\d)', scan_text)))
    target_ids = [n[:6] for n in target_ids]

    # 构建 Payload
    payload = []
    payload.extend(st.session_state.kb_engine["rules"])
    
    tmall_hit = False
    for bid in target_ids:
        if bid in st.session_state.kb_engine["tmall"]:
            payload.append(st.session_state.kb_engine["tmall"][bid])
            tmall_hit = True
    
    # 决策路由：天猫没中才上大文档 PPT
    if not tmall_hit:
        payload.extend(st.session_state.kb_engine["ppt"])
        hint = "\n\n<system>未命中天猫精准库。若问及尺码细节，请务必索要 6 位货号。</system>"
    else:
        hint = "\n\n<system>已命中天猫精准库，请优先提取尺码表作答。</system>"

    payload.append(query + hint)

    # 模型核心指令
    sys_instruction = """
    你是 Burton 资深客服专家。
    1. 严格防幻觉：资料里没有的尺码/参数，必须说不知道，严禁脑补！
    2. ID 约束：问尺码没给 ID 时，必须礼貌索要 6 位货号。
    3. 业务红线：Step On 男女款严禁混用！
    4. 输出格式：### 1️⃣ 🧠 客户意图分析、### 2️⃣ 📚 核心知识点、### 3️⃣ 💬 建议回复话术、### 4️⃣ 🎯 关联推荐。
    """

    if "session" not in st.session_state:
        # 使用 1.5-flash，兼顾速度与长文本处理能力
        model = genai.GenerativeModel("gemini-1.5-flash", system_instruction=sys_instruction)
        st.session_state.session = model.start_chat(history=[])

    try:
        with st.chat_message("assistant", avatar="🏂"):
            with st.spinner("🤖 正在穿越多级数据库进行检索..."):
                resp = st.session_state.session.send_message(payload)
                
                # 运行合规词过滤引擎
                final_text, _ = smart_compliance_filter(resp.text, st.session_state.banned_words)
                st.markdown(final_text)
                save_to_daily_log("assistant", final_text)
                
                # 更新记忆
                st.session_state.chat_history.append(("user", query))
                st.session_state.chat_history.append(("assistant", final_text))
    except Exception as e:
        st.error(f"⚠️ 检索失败，请重试。错误代码: {e}")
