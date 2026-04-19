import streamlit as st
import google.generativeai as genai
import os
import glob
import time
import datetime
import re

# ================= 1. 基础配置与路径 =================
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
    st.error("❌ API KEY 配置缺失，请检查 .streamlit/secrets.toml")
    st.stop()

# ================= 2. 合规引擎与日志系统 =================
SAFE_WORDS = {"Burton", "BURTON", "burton", "Anon", "ANON", "anon", "ak", "AK", "[ak]", "GORE-TEX", "Boa", "MIPS", "Step On", "Est", "Re:Flex"}
SMART_SYNONYMS = {"第一": "排名前列", "NO.1": "人气热销", "Top1": "人气热销", "冠军": "人气优选", "首选": "优选", "顶级": "高端", "顶尖": "高端", "极致": "出色", "极佳": "出色", "完美": "理想", "绝佳": "非常棒", "独家": "特色", "独有": "特有", "最强": "强力", "最好": "很好", "最大": "很大", "最高": "很高", "最低": "超值", "全网": "全渠道", "世界级": "高水准", "史无前例": "难得一见", "永久": "长久", "百分之百": "致力于", "必": "建议", "最": "十分"}

@st.cache_resource
def load_banned_words():
    """加载极限词库"""
    banned_set = set()
    for p in glob.glob(os.path.join(DIR_RULES, "*.txt")):
        try:
            with open(p, "r", encoding='utf-8') as f:
                content = f.read()
                raw_words = re.split(r"[,\n\s'\"\[\]]+", content)
                for w in raw_words:
                    clean_w = w.strip()
                    if len(clean_w) > 1 or clean_w == '最':
                        if clean_w not in SAFE_WORDS and clean_w.lower() not in [s.lower() for s in SAFE_WORDS]:
                            banned_set.add(clean_w)
        except: pass
    return banned_set

def highlight_banned_words(text, banned_set):
    """分析部分标红高亮"""
    if not banned_set: return text, False
    found = False
    for word in banned_set:
        if word in text:
            found = True
            suggestion = f" 💡建议改:{SMART_SYNONYMS[word]}" if word in SMART_SYNONYMS else ""
            text = text.replace(word, f":red[**🚫{word}**]{suggestion}")
    return text, found

def shield_banned_words(text, banned_set):
    """回复部分静默替换"""
    if not banned_set: return text, False
    found = False
    for word in banned_set:
        if word in text:
            found = True
            replacement = SMART_SYNONYMS.get(word, "") 
            text = text.replace(word, replacement)
    return text, found

def smart_compliance_filter(full_response, banned_set):
    """合规组装器"""
    if not banned_set: return full_response, False
    parts = full_response.split("### 3️⃣ 💬 建议回复话术")
    if len(parts) < 2: return highlight_banned_words(full_response, banned_set)
    
    part_before = parts[0]
    rest = parts[1]
    sub_parts = rest.split("### 4️⃣")
    reply_content = sub_parts[0]
    part_after = "### 4️⃣" + sub_parts[1] if len(sub_parts) > 1 else ""
    
    safe_before, i1 = highlight_banned_words(part_before, banned_set)
    safe_reply, i2 = shield_banned_words(reply_content, banned_set)
    safe_after, i3 = highlight_banned_words(part_after, banned_set)
    
    return safe_before + "### 3️⃣ 💬 建议回复话术" + safe_reply + safe_after, (i1 or i2 or i3)

def save_to_daily_log(role, text):
    """自动物理写入日志"""
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    now = datetime.datetime.now().strftime("%H:%M:%S")
    log_path = os.path.join(DIR_LOGS, f"chat_{today}.txt")
    clean_text = re.sub(r':\w+\[\*\*(.*?)\*\*\]', r'\1', text)
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{now}] {role.upper()}:\n{clean_text}\n{'-'*50}\n")
    except: pass

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
        
    for p in glob.glob(os.path.join(DIR_RULES, "*.md")): kb["rules"].append(up(p))
    for p in glob.glob(os.path.join(DIR_TMALL, "*.md")): kb["tmall"][os.path.basename(p)[:6]] = up(p)
    for p in glob.glob(os.path.join(DIR_PPT, "*.md")): kb["ppt"].append(up(p))
    return kb

if "kb_engine" not in st.session_state:
    with st.spinner("🚀 正在同步多级核心数据源 (约需 1-2 分钟)，请稍候..."):
        st.session_state.kb_engine = index_knowledge_base()
        st.session_state.banned_words = load_banned_words()
if "chat_history" not in st.session_state: st.session_state.chat_history = []

# ================= 4. UI 侧边栏 =================
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/3/3b/Burton_Snowboards_logo.svg/2560px-Burton_Snowboards_logo.svg.png", width=120)
    
    app_mode = st.radio("🎯 核心功能模块:", ["💬 客服实战副驾", "🎓 AI 模拟陪练营"])
    
    if app_mode == "💬 客服实战副驾":
        st.info("💡 **导购操作规范**：\n查询精确尺码与参数请**务必输入 6 位货号**，否则系统无法提取天猫详情。")
        if st.button("🗑️ 接待新客户 (清空记忆)", use_container_width=True):
            st.session_state.chat_history = []
            if "cs_session" in st.session_state: del st.session_state.cs_session
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

# ================= 5. 模块 A：客服实战副驾 (企业级多轨路由) =================
if app_mode == "💬 客服实战副驾":
    st.title("🏂 Burton 客服实战副驾")

    for role, text in st.session_state.chat_history:
        with st.chat_message(role, avatar="👤" if role=="user" else "🏂"):
            st.markdown(text)

    query = st.chat_input("输入问题... (🎯 查尺码/参数请务必附带 6 位货号)")

    if query:
        save_to_daily_log("user", query)
        with st.chat_message("user", avatar="👤"): st.write(query)
        
        # 提取 ID (滑动窗口追踪)
        scan_text = query
        if st.session_state.chat_history: scan_text += " " + st.session_state.chat_history[-1][1]
        target_ids = list(set(re.findall(r'(?<!\d)\d{6,15}(?!\d)', scan_text)))
        target_ids = [n[:6] for n in target_ids]

        # 组装 Payload (防污染分发)
        payload = []
        payload.extend(st.session_state.kb_engine["rules"])
        tmall_hit = False
        loaded_tmall_ids = []
        
        for bid in target_ids:
            if bid in st.session_state.kb_engine["tmall"]:
                payload.append(st.session_state.kb_engine["tmall"][bid])
                loaded_tmall_ids.append(bid)
                tmall_hit = True
        
        if not tmall_hit:
            payload.extend(st.session_state.kb_engine["ppt"])
            hint = "\n\n<system>系统后台：未命中天猫精准库。若问题涉及尺码细节且无货号，请必须提示客服输入货号。</system>"
        else:
            hint = f"\n\n<system>系统后台：已命中天猫精准库货号 {loaded_tmall_ids}，请优先提取其中的精准尺码与参数作答。</system>"

        payload.append(query + hint)

        sys_instruction = """
        你是 Burton 资深客服专家。
        1. 严格防幻觉：资料里没有的参数，必须说不知道！
        2. ID 约束：问尺码或参数没给 ID 时，必须礼貌索要 6 位货号。
        3. 业务红线：Step On 男女款严禁混用！
        4. 输出格式：### 1️⃣ 🧠 客户意图分析、### 2️⃣ 📚 核心知识点、### 3️⃣ 💬 建议回复话术、### 4️⃣ 🎯 关联推荐。
        """

        if "cs_session" not in st.session_state:
            model = genai.GenerativeModel("gemini-1.5-flash", system_instruction=sys_instruction)
            st.session_state.cs_session = model.start_chat(history=[])

        try:
            with st.chat_message("assistant", avatar="🏂"):
                with st.spinner("🤖 正在路由多级数据库..."):
                    resp = st.session_state.cs_session.send_message(payload)
                    final_text, has_issues = smart_compliance_filter(resp.text, st.session_state.banned_words)
                    st.markdown(final_text)
                    if has_issues:
                        st.toast("🛡️ 已触发极限词合规过滤", icon="✅")
                    
                    save_to_daily_log("assistant", final_text)
                    st.session_state.chat_history.append(("user", query))
                    st.session_state.chat_history.append(("assistant", final_text))
        except Exception as e:
            st.error(f"检索失败: {e}")

# ================= 6. 模块 B：AI 模拟陪练营 (省流降本隔离版) =================
elif app_mode == "🎓 AI 模拟陪练营":
    st.title("🎓 Burton 客服新兵陪练营")
    st.markdown("通过模拟真实客户对话，测试你的导购专业度、规则熟悉度以及服务态度。")

    train_chapter = st.selectbox(
        "📚 选择本节考核科目:",
        [
            "综合考核：全品类应对与灵活导购",
            "第1课：初识 Burton & 品牌文化传递",
            "第2课：单板硬件体系 (Camber vs Flat Top)",
            "第3课：固定器与雪鞋的完美匹配 (硬度法则)",
            "第4课：Step On 系统的绝对红线",
            "第5课：雪服穿搭与科技 (Gore-Tex & 分层穿衣)",
            "第6课：Anon 护目镜与头盔选购",
        ]
    )

    if st.button("🎲 生成随机客户挑战"):
        with st.spinner("正在根据考核科目生成客户档案..."):
            model = genai.GenerativeModel("gemini-1.5-flash")
            
            # 【核心架构亮点】：陪练营坚决不加载 800 个天猫文件，只使用规则和 PPT 进行降本推演
            training_kb = st.session_state.kb_engine["rules"] + st.session_state.kb_engine["ppt"]
            
            prompt = f"""
            你是一位非常有经验的 Burton 客服培训师。
            请根据当前考核科目：【{train_chapter}】，以及你所掌握的知识库，生成一个逼真的客户进店咨询场景。
            
            要求：
            1. 客户的角色要符合该科目的特征（例如：新手、老炮、给孩子买装备的家长等）。
            2. 客户的提问必须包含 1-2 个陷阱或信息缺失（例如：问板子不报身高体重，选 Step On 不分男女款，或者要最便宜的）。
            3. 请用第一人称，直接输出客户说的话（不要输出多余的解释）。
            """
            
            try:
                response = model.generate_content(training_kb + [prompt])
                st.session_state.training_scenario = response.text
                st.rerun()
            except Exception as e:
                st.error(f"生成失败，请重试: {e}")

    if "training_scenario" in st.session_state:
        st.info(f"👤 **模拟客户:**\n\n\"{st.session_state.training_scenario}\"")
        
        trainee_reply = st.text_area("✍️ 请输入你的回复话术 (作为客服):", height=150)
        
        if st.button("📝 提交批改"):
            if trainee_reply:
                with st.spinner("🧑‍🏫 培训导师正在评估你的回复..."):
                    model = genai.GenerativeModel("gemini-1.5-flash")
                    # 同样，评估时也不需要天猫文件，省时省Token
                    training_kb = st.session_state.kb_engine["rules"] + st.session_state.kb_engine["ppt"]
                    
                    eval_prompt = f"""
                    你现在是 Burton China 的金牌客服培训总监。
                    当前考核科目：【{train_chapter}】
                    客户的原始提问: {st.session_state.training_scenario}
                    新员工回复: {trainee_reply}
                   
                    【评分标准 (满分100)】
                    1. 致命错误 (-30分): 是否使用了广告法极限词 (如最、第一、顶级等)，或者擅自承诺了具体价格数字。
                    2. 流程错误 (-20分): 导购逻辑是否缺失？(如选板未反问身高/体重，选鞋/固定器未反问鞋码，或未能应对缺货情况)。
                    3. 专业度 (40分): 推荐的产品、科技点是否准确对应本节课【{train_chapter}】的教学目标和知识库。
                    4. 服务态度 (10分): 语气是否专业、耐心、亲切。
                    
                    请严格按照以下 Markdown 格式输出：
                    ### 🎯 综合评分: [X分] / 100分
                    * **评级**: [S/A/B/C/D]
                   
                    ### 🔍 扣分项与亮点分析
                    * [列出具体哪里做得好，哪里扣分了，务必结合本节课的教学目标点评]
                   
                    ### 💡 导师示范话术
                    > [给出一个满分的完美回复示范。语气要符合品牌调性，且包含必要的信息反问或连带推荐]
                    """
                    try:
                        eval_response = model.generate_content(training_kb + [eval_prompt])
                        st.markdown(eval_response.text)
                        
                        if "不及格" in eval_response.text or "致命错误" in eval_response.text:
                            st.error("🚨 警告：触发核心红线，请仔细阅读导师点评！")
                        else:
                            st.success("🎉 回复得不错，继续保持！")
                    except Exception as e:
                        st.error(f"批改失败: {e}")
            else:
                st.warning("⚠️ 请先输入你的回复！")
