import streamlit as st
import google.generativeai as genai
import os
import glob
import time
import datetime
import re

# ================= 配置区 =================
st.set_page_config(page_title="Burton CS Co-pilot", page_icon="🏂", layout="wide")

KB_FOLDER = "knowledge_base"

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
# 新增：用于存储生成的培训场景
if "training_scenario" not in st.session_state:
    st.session_state.training_scenario = ""

# ================= 核心逻辑：智能合规过滤 =================
SAFE_WORDS = {
    "Burton", "BURTON", "burton", 
    "Anon", "ANON", "anon",
    "ak", "AK", "[ak]",
    "GORE-TEX", "Boa", "MIPS", 
    "Step On", "Est", "Re:Flex"
}

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
    txt_files = glob.glob(os.path.join(KB_FOLDER, "*.txt"))
    for txt_file in txt_files:
        try:
            with open(txt_file, "r", encoding='utf-8') as f:
                content = f.read()
                raw_words = re.split(r"[,\n\s'\"\[\]]+", content)
                for w in raw_words:
                    clean_w = w.strip()
                    is_special_char = (clean_w == '最')
                    is_valid_len = (len(clean_w) > 1)
                    if (is_valid_len or is_special_char) and clean_w not in SAFE_WORDS and clean_w.lower() not in [s.lower() for s in SAFE_WORDS]:
                        banned_set.add(clean_w)
        except Exception:
            pass
    banned_set = {w for w in banned_set if w not in SAFE_WORDS and w.lower() not in [s.lower() for s in SAFE_WORDS]}
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
    if not banned_set: return full_response, False
    REPLY_SECTION_HEADER = "### 3️⃣ 💬 建议回复话术"
    NEXT_SECTION_HEADER = "### 4️⃣" 
    parts = full_response.split(REPLY_SECTION_HEADER)
    if len(parts) < 2:
        return highlight_banned_words(full_response, banned_set)
    
    part_before = parts[0]
    rest = parts[1]
    sub_parts = rest.split(NEXT_SECTION_HEADER)
    reply_content = sub_parts[0]
    part_after = NEXT_SECTION_HEADER + sub_parts[1] if len(sub_parts) > 1 else ""
    
    safe_before, issue1 = highlight_banned_words(part_before, banned_set)
    safe_reply, issue2 = shield_banned_words(reply_content, banned_set)
    safe_after, issue3 = highlight_banned_words(part_after, banned_set)
    
    final_text = safe_before + REPLY_SECTION_HEADER + safe_reply + safe_after
    return final_text, (issue1 or issue2 or issue3)

@st.cache_resource
def load_knowledge_base_files():
    uploaded_refs = []
    if not os.path.exists(KB_FOLDER): os.makedirs(KB_FOLDER)
    md_files = glob.glob(os.path.join(KB_FOLDER, "*.md"))
    for file_path in md_files:
        try:
            file_name = os.path.basename(file_path)
            file_ref = genai.upload_file(path=file_path, mime_type="text/plain", display_name=file_name)
            while file_ref.state.name == "PROCESSING":
                time.sleep(1)
                file_ref = genai.get_file(file_ref.name)
            uploaded_refs.append(file_ref)
        except Exception:
            pass
    return uploaded_refs

if api_key and not st.session_state.kb_loaded:
    with st.spinner("🚀 正在初始化 Burton 知识引擎..."):
        st.session_state.banned_words = load_banned_words()
        st.session_state.gemini_files = load_knowledge_base_files()
        st.session_state.kb_loaded = True

# ================= 侧边栏 =================
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/3/3b/Burton_Snowboards_logo.svg/2560px-Burton_Snowboards_logo.svg.png", width=150)
    
    # 🔴 新增：功能模块切换器
    app_mode = st.radio("🎯 核心功能模块:", ["💬 客服实战副驾", "🎓 AI 模拟陪练营"])
    st.divider()

    st.caption("⚙️ 系统状态")
    if api_key: st.success(api_status)
    else: st.error(api_status)
    
    if st.session_state.banned_words:
        st.success(f"🛡️ 护盾激活 ({len(st.session_state.banned_words)} 词条)")
    
    st.divider()
    model_choice = st.radio("🧠 大脑引擎:", ("⚡ 极速模式 (Flash)", "🐢 深度思考 (Pro)"), index=0)
    selected_model_name = "gemini-3-flash-preview" if "Flash" in model_choice else "gemini-3-pro-preview"

# ================= 主界面 =================
st.title("🏂 Burton China AI Hub")
st.caption("🚀 Powered by YZ-Shield | Enterprise CS & Training Engine")
st.divider() 

model = genai.GenerativeModel(model_name=selected_model_name)

# ================= 模式 1：客服实战副驾 =================
if app_mode == "💬 客服实战副驾":
    st.subheader("💬 实时客服支援系统")
    if st.session_state.chat_history:
        for role, text in st.session_state.chat_history[-6:]:
            if role == "user":
                with st.chat_message("user", avatar="👤"): st.write(text)
            else:
                with st.chat_message("assistant", avatar="🏂"):
                    safe_text, _ = smart_compliance_filter(text, st.session_state.banned_words)
                    st.markdown(safe_text)

    system_instruction = """
    你是 Burton China 客服智能副驾。
    1. **独立问答**：忽略历史，每一次提问都是新客户。
    2. **主动反问**：如客户未提供【性别】、【体重】或【鞋码】，必须在回复末尾反问，严禁预设。
    3. **合规**：严禁极限词(最、第一、顶级等)。
    4. **价格隐藏**：严禁输出具体金额，引导看店铺活动。
    输出必须严格包含：### 1️⃣ 🧠 客户画像分析、### 2️⃣ 📚 核心知识胶囊、### 3️⃣ 💬 建议回复话术、### 4️⃣ 🎯 关联销售机会。
    """
    
    user_query = st.chat_input("在此输入客户问题 (例如：帮我选个单板)...")
    if user_query:
        if not api_key or not st.session_state.gemini_files:
            st.error("⚠️ 系统未准备就绪。")
        else:
            with st.chat_message("user", avatar="👤"): st.write(user_query)
            try:
                chat = model.start_chat(history=[]) 
                model_with_sys = genai.GenerativeModel(model_name=selected_model_name, system_instruction=system_instruction)
                chat = model_with_sys.start_chat(history=[])
                
                with st.chat_message("assistant", avatar="🏂"):
                    with st.spinner("🤖 正在生成销售策略..."):
                        response = chat.send_message(st.session_state.gemini_files + [user_query])
                        final_text_display, has_issues = smart_compliance_filter(response.text, st.session_state.banned_words)
                        st.markdown(final_text_display)
                        if has_issues: st.toast("🛡️ 已替换极限词，价格已隐藏。", icon="✅")
                
                st.session_state.chat_history.append(("user", user_query))
                st.session_state.chat_history.append(("assistant", response.text))
            except Exception as e:
                st.error(f"生成失败: {e}")

# ================= 模式 2：AI 模拟陪练营 =================
elif app_mode == "🎓 AI 模拟陪练营":
    st.subheader("🎓 阶梯式通关实战演练")
    st.info("💡 **向客户演示建议**：这是我们在二期规划的『AI 金牌导师』功能。系统会根据知识库自动扮演刁钻客户，并对新员工的回复进行质检打分。")
    
    col1, col2 = st.columns(2)
    with col1:
        train_category = st.selectbox("📚 选择培训产品线", ["Snowboards (雪板)", "Boots & Bindings (鞋&固定器)", "Outerwear (雪服)", "Anon (雪镜/头盔)"])
    with col2:
        train_level = st.selectbox("🔥 选择客户刁钻程度", ["Level 1: 友好型新手", "Level 2: 预算充足但纠结的进阶玩家", "Level 3: 地狱模式 (暴躁/极限要求)"])

    if st.button("🎲 生成客诉场景", type="primary"):
        with st.spinner("🤖 AI 客服总监正在出题..."):
            prompt_scenario = f"基于你的Burton知识库，生成一段简短的、真实的客户咨询对话（只需客户说的一句话）。客户购买品类是 {train_category}，客户的特点是 {train_level}。不要任何前言后语，只输出客户的带引号的话。"
            try:
                response = model.generate_content(st.session_state.gemini_files + [prompt_scenario])
                st.session_state.training_scenario = response.text
            except Exception as e:
                st.error("出题失败，请重试。")

    if st.session_state.training_scenario:
        st.success("✅ 场景已生成，请开始你的表演！")
        st.markdown(f"### 🤬 客户发话了：\n> **{st.session_state.training_scenario}**")
        
        trainee_reply = st.text_area("✍️ 请在此输入你的回复（客服话术）：", height=150)
        
        if st.button("📝 提交批改"):
            if trainee_reply:
                with st.spinner("👨‍🏫 AI 导师正在阅卷..."):
                    eval_prompt = f"""
                    你是 Burton 资深客服培训总监。请严格评估以下新员工的回复。
                    
                    客户问题: {st.session_state.training_scenario}
                    新员工回复: {trainee_reply}
                    
                    【评分标准 (满分100)】
                    1. 致命错误 (-30分): 是否使用了广告法极限词 (如最、第一、顶级等)。
                    2. 流程错误 (-20分): 选板是否忘记问身高/体重？选鞋/固定器是否忘记问鞋码？
                    3. 专业度 (40分): 推荐的产品、科技点是否符合 Burton 调性。
                    4. 服务态度 (10分): 语气是否专业亲切。

                    请严格按照以下 Markdown 格式输出：
                    ### 🎯 综合评分: [X分] / 100分
                    * **评级**: [S/A/B/C/D]
                    
                    ### 🔍 扣分项与亮点分析
                    * [列出具体哪里做得好，哪里扣分了]
                    
                    ### 💡 总监示范话术
                    > [给出一个满分的完美回复示范]
                    """
                    try:
                        eval_response = model.generate_content(st.session_state.gemini_files + [eval_prompt])
                        st.markdown(eval_response.text)
                        
                        # 如果得分低，加个趣味提示
                        if "不及格" in eval_response.text or "D" in eval_response.text or "C" in eval_response.text:
                            st.warning("⚠️ 看来还需要多加练习！回去多看看产品手册哦。")
                        else:
                            st.balloons()
                            
                    except Exception as e:
                        st.error("评分失败。")
            else:
                st.warning("请先输入你的回复！")
