import streamlit as st
import google.generativeai as genai
import os
import glob
import time
import datetime
import re

# ================= 1. 基础配置与路径映射 =================
st.set_page_config(page_title="Burton CS Co-pilot", page_icon="🏂", layout="wide")

# 定义严格的物理目录结构
KB_ROOT = "knowledge_base"
DIR_RULES = os.path.join(KB_ROOT, "01_rules")
DIR_TMALL = os.path.join(KB_ROOT, "02_tmall_data")
DIR_PPT   = os.path.join(KB_ROOT, "03_ppt_original")
DIR_LOGS  = "chat_logs"

# 自动创建必要文件夹
for d in [DIR_RULES, DIR_TMALL, DIR_PPT, DIR_LOGS]:
    if not os.path.exists(d): 
        os.makedirs(d)

# API 密钥鉴权
try:
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
except:
    st.error("❌ API KEY 配置缺失，请检查 .streamlit/secrets.toml！")
    st.stop()

# ================= 2. 合规引擎与字典 (高级UI版) =================
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
    """合规引擎：分析部分标红，话术部分静默替换"""
    if not banned_set: return full_response, False
    parts = full_response.split("### 3️⃣ 💬 建议回复话术")
    if len(parts) < 2: return highlight_banned_words(full_response, banned_set)
    part_before = parts[0]
    rest = parts[1]
    sub_parts = rest.split("### 4️⃣")
    reply_content = sub_parts[0]
    part_after = "### 4️⃣" + (sub_parts[1] if len(sub_parts) > 1 else "")
    
    safe_before, i1 = highlight_banned_words(part_before, banned_set)
    safe_reply, i2 = shield_banned_words(reply_content, banned_set)
    safe_after, i3 = highlight_banned_words(part_after, banned_set)
    
    return safe_before + "### 3️⃣ 💬 建议回复话术" + safe_reply + safe_after, (i1 or i2 or i3)

def save_to_daily_log(role, text):
    """自动写入系统日志"""
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    now = datetime.datetime.now().strftime("%H:%M:%S")
    log_path = os.path.join(DIR_LOGS, f"chat_{today}.txt")
    clean_text = re.sub(r':\w+\[\*\*(.*?)\*\*\]', r'\1', text)
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{now}] {role.upper()}:\n{clean_text}\n{'-'*50}\n")
    except: pass

# ================= 3. 数据调度：终极云端查重引擎 =================

@st.cache_resource(show_spinner=False)
def index_knowledge_base():
    """带云端查重、防限流、前端进度条的终极加载引擎"""
    kb = {"rules": [], "tmall": {}, "ppt": []}
    
    all_rules = glob.glob(os.path.join(DIR_RULES, "*.md"))
    all_tmall = glob.glob(os.path.join(DIR_TMALL, "*.md"))
    all_ppt = glob.glob(os.path.join(DIR_PPT, "*.md"))
    total_files = len(all_rules) + len(all_tmall) + len(all_ppt)
    
    if total_files == 0:
        return kb, 0, 0
    
    progress_bar = st.progress(0, text="🚀 正在连接 Google 云端，核对文件指纹...")
    
    # 🔴 核心优化 1：拉取云端已存在的文件，避免重复上传被限流！
    existing_files = {}
    try:
        for f in genai.list_files():
            if f.display_name:
                existing_files[f.display_name] = f
    except Exception as e:
        pass 
        
    current_count = 0
    success_count = 0

    def up(p):
        nonlocal current_count, success_count
        current_count += 1
        f_name = os.path.basename(p)
        
        # 实时更新 UI 进度
        percent = int((current_count / total_files) * 100)
        progress_bar.progress(percent, text=f"🚀 [{current_count}/{total_files}] 正在处理: {f_name}")
        
        # 🔴 核心优化 2：云端已有该文件，直接秒读！
        if f_name in existing_files:
            success_count += 1
            return existing_files[f_name]
            
        # 云端没有，执行上传
        try:
            f = genai.upload_file(p, mime_type="text/plain", display_name=f_name)
            wait_time = 0
            while f.state.name == "PROCESSING" and wait_time < 12: 
                time.sleep(1)
                f = genai.get_file(f.name)
                wait_time += 1
            success_count += 1
            return f
        except Exception as e:
            return None # 遇到限流则静默跳过

    # 依次挂载文件
    for p in all_rules:
        res = up(p)
        if res: kb["rules"].append(res)
    for p in all_tmall:
        bid = os.path.basename(p)[:6]
        res = up(p)
        if res: kb["tmall"][bid] = res
    for p in all_ppt:
        res = up(p)
        if res: kb["ppt"].append(res)
        
    time.sleep(1)
    progress_bar.empty() 
    return kb, total_files, success_count

# --- 系统启动与自检 ---
if "kb_engine" not in st.session_state:
    st.session_state.banned_words = load_banned_words()
    kb_data, total_files, success_count = index_knowledge_base()
    
    if total_files == 0:
        st.error("❌ **致命错误：未在指定目录下找到 Markdown 文件！**")
        st.stop()
    elif success_count < total_files:
        st.warning(f"⚠️ 发现 {total_files - success_count} 个文件同步失败（API限流）。已成功加载 {success_count} 个文件，系统降级启动。")
        st.session_state.kb_engine = kb_data
    else:
        st.session_state.kb_engine = kb_data
        st.toast(f"✅ 完美同步 {success_count} 个核心数据文件！", icon="🎉")

if "chat_history" not in st.session_state: 
    st.session_state.chat_history = []

# ================= 4. UI 侧边栏 =================
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/3/3b/Burton_Snowboards_logo.svg/2560px-Burton_Snowboards_logo.svg.png", width=120)
    app_mode = st.radio("🎯 功能模块:", ["💬 客服实战副驾", "🎓 AI 模拟陪练营"])
    
    if app_mode == "💬 客服实战副驾":
        st.info("💡 **规范**：\n查询尺码/参数请**务必输入 6 位货号**。")
        if st.button("🗑️ 接待新客户", use_container_width=True):
            st.session_state.chat_history = []
            if "cs_session" in st.session_state: del st.session_state.cs_session
            st.rerun()

    st.divider()
    with st.expander("🔐 内部日志管理"):
        pwd = st.text_input("密令:", type="password")
        if pwd == "burton2026":
            st.success("验证成功")
            logs = sorted(glob.glob(os.path.join(DIR_LOGS, "*.txt")), reverse=True)
            if logs:
                selected = st.selectbox("选择日志", logs, format_func=lambda x: os.path.basename(x))
                with open(selected, "rb") as f:
                    st.download_button("📥 下载日志", f, file_name=os.path.basename(selected), use_container_width=True)

# ================= 5. 模块 A：客服实战副驾 (多级路由引擎) =================
if app_mode == "💬 客服实战副驾":
    st.title("🏂 Burton 客服实战副驾")
    for role, text in st.session_state.chat_history:
        with st.chat_message(role, avatar="👤" if role=="user" else "🏂"):
            st.markdown(text)

    query = st.chat_input("🎯 查尺码请附带 6 位货号...")
    if query:
        save_to_daily_log("user", query)
        with st.chat_message("user", avatar="👤"): st.write(query)
        
        # 提取 ID (滑动窗口追踪)
        scan_text = query
        if st.session_state.chat_history: scan_text += " " + st.session_state.chat_history[-1][1]
        target_ids = list(set(re.findall(r'(?<!\d)\d{6,15}(?!\d)', scan_text)))
        target_ids = [n[:6] for n in target_ids]

        payload = []
        payload.extend(st.session_state.kb_engine["rules"])
        tmall_hit = False
        loaded_ids = []
        
        for bid in target_ids:
            if bid in st.session_state.kb_engine["tmall"]:
                payload.append(st.session_state.kb_engine["tmall"][bid])
                loaded_ids.append(bid)
                tmall_hit = True
        
        if not tmall_hit:
            payload.extend(st.session_state.kb_engine["ppt"])
            hint = "\n\n<system>未命中天猫精准库。若涉及尺码，请向客服索要货号。</system>"
        else:
            hint = f"\n\n<system>已命中天猫详情 {loaded_ids}，请优先以此作答。</system>"

        payload.append(query + hint)
        sys_instruction = """
        你是 Burton 资深客服专家。
        1. 严格防幻觉：资料没有的必须说不知道！
        2. ID 约束：问尺码没给货号必须索要 6 位货号。
        3. 业务红线：Step On 男女款严禁混用！
        4. 输出格式：### 1️⃣ 🧠 客户意图分析、### 2️⃣ 📚 核心知识点、### 3️⃣ 💬 建议回复话术、### 4️⃣ 🎯 关联推荐。
        """

        if "cs_session" not in st.session_state:
            model = genai.GenerativeModel("gemini-3-flash-preview"", system_instruction=sys_instruction)
            st.session_state.cs_session = model.start_chat(history=[])

        try:
            with st.chat_message("assistant", avatar="🏂"):
                with st.spinner("🤖 正在穿越多级数据库..."):
                    resp = st.session_state.cs_session.send_message(payload)
                    final_text, has_issues = smart_compliance_filter(resp.text, st.session_state.banned_words)
                    st.markdown(final_text)
                    if has_issues: st.toast("🛡️ 已拦截极限词并完成合规替换", icon="✅")
                    
                    save_to_daily_log("assistant", final_text)
                    st.session_state.chat_history.append(("user", query))
                    st.session_state.chat_history.append(("assistant", final_text))
        except Exception as e:
            st.error(f"检索失败: {e}")

# ================= 6. 模块 B：AI 模拟陪练营 (降本降噪版) =================
elif app_mode == "🎓 AI 模拟陪练营":
    st.title("🎓 Burton 客服新兵陪练营")
    train_chapter = st.selectbox("📚 选择考核科目:", ["综合考核：全品类应对", "第1课：品牌文化", "第2课：硬件体系", "第3课：固定器与雪鞋匹配", "第4课：Step On红线", "第5课：雪服穿搭与科技", "第6课：Anon 护目镜与头盔"])

    if st.button("🎲 生成随机挑战"):
        with st.spinner("生成中..."):
            model = genai.GenerativeModel("gemini-1.5-flash")
            # 陪练营专供：不加载天猫文件，极大节省 Token 成本
            training_kb = st.session_state.kb_engine["rules"] + st.session_state.kb_engine["ppt"]
            prompt = f"你是培训师。根据科目【{train_chapter}】生成一段逼真的客户进店咨询场景。包含一个陷阱或信息缺失。第一人称直接输出对话。"
            try:
                response = model.generate_content(training_kb + [prompt])
                st.session_state.training_scenario = response.text
                st.rerun()
            except Exception as e: st.error(f"生成失败: {e}")

    if "training_scenario" in st.session_state:
        st.info(f"👤 **模拟客户:**\n\n\"{st.session_state.training_scenario}\"")
        trainee_reply = st.text_area("✍️ 输入回复:", height=150)
        
        if st.button("📝 提交批改"):
            if trainee_reply:
                with st.spinner("导师评估中..."):
                    model = genai.GenerativeModel("gemini-1.5-flash")
                    training_kb = st.session_state.kb_engine["rules"] + st.session_state.kb_engine["ppt"]
                    eval_prompt = f"""
                    你是培训总监。客户提问: {st.session_state.training_scenario}
                    员工回复: {trainee_reply}
                    根据【{train_chapter}】，输出包含 综合评分(S/A/B/C)、扣分项与亮点分析、以及导师示范话术的报告。
                    如果使用了最、第一等极限词，必须严厉扣分。
                    """
                    try:
                        eval_response = model.generate_content(training_kb + [eval_prompt])
                        st.markdown(eval_response.text)
                    except Exception as e: st.error(f"评估失败: {e}")
