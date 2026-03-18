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
if "training_scenario" not in st.session_state:
    st.session_state.training_scenario = ""
if "training_card" not in st.session_state:
    st.session_state.training_card = ""

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
    
    app_mode = st.radio("🎯 核心功能模块:", ["💬 客服实战副驾", "🎓 AI 新星起航计划 (内训)"])
    
    # 🔴 新增：恢复清空记忆按钮（仅在实战副驾模式下显示）
    if app_mode == "💬 客服实战副驾":
        if st.button("🗑️ 接待新客户 (清空记忆)", type="primary", use_container_width=True):
            st.session_state.chat_history = []
            if "cs_chat_session" in st.session_state:
                del st.session_state.cs_chat_session
            if "is_first_turn" in st.session_state:
                del st.session_state.is_first_turn
            st.rerun()

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
    
    # 显示完整的历史对话（不再限制显示最后6条，方便客服回溯上下文）
    if st.session_state.chat_history:
        for role, text in st.session_state.chat_history:
            if role == "user":
                with st.chat_message("user", avatar="👤"): st.write(text)
            else:
                with st.chat_message("assistant", avatar="🏂"):
                    safe_text, _ = smart_compliance_filter(text, st.session_state.banned_words)
                    st.markdown(safe_text)

    # 🔴 核心指令修改：赋予连续对话能力
    system_instruction = """
    你是 Burton China 客服智能副驾。
    1. **连贯问答 (Contextual)**：请记住当前客户在历史对话中提供的信息。如果客户已提供过【性别】、【体重】或【鞋码】，在后续推荐中直接使用该数据，严禁重复反问。如果关键信息依然缺失，必须在回复末尾主动反问。
    2. **合规**：严禁极限词(最、第一、顶级等)。
    3. **价格隐藏**：严禁输出具体金额，引导看店铺活动。
    输出必须严格包含：### 1️⃣ 🧠 客户画像分析、### 2️⃣ 📚 核心知识胶囊、### 3️⃣ 💬 建议回复话术、### 4️⃣ 🎯 关联销售机会。
    （如果是简单的客户寒暄如“谢谢”，可不用严格此格式，自然回复即可）
    """
    
    # 初始化持久化的 Chat Session
    if "cs_chat_session" not in st.session_state:
        model_with_sys = genai.GenerativeModel(model_name=selected_model_name, system_instruction=system_instruction)
        st.session_state.cs_chat_session = model_with_sys.start_chat(history=[])
        st.session_state.is_first_turn = True # 标记是否是第一句话

    user_query = st.chat_input("在此输入客户问题 (例如：帮我选个单板)...")
    if user_query:
        if not api_key or not st.session_state.gemini_files:
            st.error("⚠️ 系统未准备就绪。")
        else:
            with st.chat_message("user", avatar="👤"): st.write(user_query)
            try:
                with st.chat_message("assistant", avatar="🏂"):
                    with st.spinner("🤖 正在结合上下文推理销售策略..."):
                        
                        # 🔴 核心优化：只在第一句话把厚厚的文档扔给它，后面只传字，省钱又快！
                        if st.session_state.is_first_turn:
                            payload = st.session_state.gemini_files + [user_query]
                            st.session_state.is_first_turn = False
                        else:
                            payload = [user_query]
                            
                        response = st.session_state.cs_chat_session.send_message(payload)
                        final_text_display, has_issues = smart_compliance_filter(response.text, st.session_state.banned_words)
                        st.markdown(final_text_display)
                        
                        if has_issues: st.toast("🛡️ 已替换极限词，价格已隐藏。", icon="✅")
                
                st.session_state.chat_history.append(("user", user_query))
                st.session_state.chat_history.append(("assistant", response.text))
            except Exception as e:
                st.error(f"生成失败: {e}")

# ================= 模式 2：AI 模拟陪练营 (原样保留) =================
elif app_mode == "🎓 AI 新星起航计划 (内训)":
    st.subheader("🎓 3周结构化陪跑大纲 (Learn & Practice)")
    st.info("💡 **学习指引**：请按照入职周数，循序渐进抽取【知识微课】复习，随后进入【实战模拟】完成课程打卡。")
    
    col1, col2 = st.columns(2)
    with col1:
        train_chapter = st.selectbox(
            "📚 1. 选择今日培训课程", 
            [
                "【Week 1 破冰】Day 1: 单板解剖学与板型解析",
                "【Week 1 破冰】Day 2: Step On® 革命与固定器",
                "【Week 1 破冰】Day 3: 雪靴科技与贴合度密码",
                "【Week 1 破冰】Day 4: Anon 视觉与减震防线",
                "【Week 2 进阶】Day 1: [ak] 系列与 GORE-TEX 解析",
                "【Week 2 进阶】Day 2: 洋葱式科学穿搭法则",
                "【Week 2 进阶】Day 3: Family Tree 大山系列",
                "【Week 2 进阶】Day 4: 女性专属与儿童成长系统",
                "【Week 3 销冠】Day 1: 探寻需求与尺码核对 (导购SOP)",
                "【Week 3 销冠】Day 2: 极限词排雷与价格合规",
                "【Week 3 销冠】Day 3: 平替策略与缺货应对"
            ]
        )
    with col2:
        train_level = st.selectbox(
            "🔥 2. 选择实战难度", 
            [
                "Level 1: 基础知识问答 (考察产品熟悉度)", 
                "Level 2: 进阶场景推荐 (考察连带销售与搭配)", 
                "Level 3: 极限压力挑战 (考察专业应对与合规风控)"
            ]
        )

    st.divider()

    st.markdown("### 📖 第一步：知识充电站 (Micro-Lesson)")
    st.caption("AI 导师已根据最新产品手册提炼本课核心内容，请仔细阅读后再接受考核。")
    
    if st.button("💡 生成【" + train_chapter.split(':')[-1].strip() + "】课前预习卡", use_container_width=True):
        with st.spinner(f"🤖 正在为您从私有知识库中萃取课程精华..."):
            card_prompt = f"""
            你是 Burton 资深内训师。今天的新员工培训课程是：{train_chapter}。
            请根据你已加载的知识库，生成一张『课前预习微卡片』。
            要求严格按照以下 Markdown 格式输出，语言简练生动，严禁使用广告法极限词，严禁出现具体金额数字：
            
            #### 🌟 本课核心卖点/知识点速记 (Top 3)
            * **[知识点1]**: [一句话解释其原理或客户价值]
            * **[知识点2]**: [一句话解释其原理或客户价值]
            * **[知识点3]**: [一句话解释其原理或客户价值]
            
            #### 🙋 常见咨询与实战避坑
            * **客户常问**: [列出1个该章节新手最容易被问住的问题]
            * **标准解答**: [给出专业、亲切的解答思路。如果涉及选板/鞋，必须提醒员工询问客户的身高/体重/鞋码等信息]
            """
            try:
                response = model.generate_content(st.session_state.gemini_files + [card_prompt])
                st.session_state.training_card = response.text
                st.session_state.training_scenario = "" 
            except Exception as e:
                st.error("提取知识卡片失败，请重试。")

    if st.session_state.training_card:
        with st.container(border=True):
            st.markdown(st.session_state.training_card)

    st.divider()

    st.markdown("### ⚔️ 第二步：实战模拟演练 (Role-play Simulation)")
    
    if not st.session_state.training_card:
        st.warning("⚠️ 建议先在上方抽取并学习『知识充电站』卡片，再进行实战演练。")
        
    if st.button("🎲 匹配【" + train_level + "】模拟客户", type="primary"):
        with st.spinner("🤖 AI 客服总监正在为您匹配客户..."):
            prompt_scenario = f"基于你的Burton知识库。现在是一场新员工内部实战考核。考核课程是：【{train_chapter}】。你需要扮演一个客户发起咨询。客户特点是：【{train_level}】。请只输出一句客户说的话（带引号），要求口语化、真实，字数在50字以内。不要任何前言后语。"
            try:
                response = model.generate_content(st.session_state.gemini_files + [prompt_scenario])
                st.session_state.training_scenario = response.text
            except Exception as e:
                st.error("出题失败，请重试。")

    if st.session_state.training_scenario:
        st.success("✅ 客户已上线，请开始作答！")
        st.markdown(f"### 🙋‍♂️ 客户咨询：\n> **{st.session_state.training_scenario}**")
        
        trainee_reply = st.text_area("✍️ 请在此输入您的专业回复/导购话术：", height=150)
        
        if st.button("📝 提交 AI 导师批改"):
            if trainee_reply:
                with st.spinner("👨‍🏫 AI 导师正在阅卷并撰写评语..."):
                    eval_prompt = f"""
                    你是 Burton 资深内训总监。请严格评估以下新员工的回复。
                    
                    当前考核课程: {train_chapter}
                    客户问题: {st.session_state.training_scenario}
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
                        eval_response = model.generate_content(st.session_state.gemini_files + [eval_prompt])
                        st.markdown(eval_response.text)
                        
                        if "不及格" in eval_response.text or "D" in eval_response.text or "C" in eval_response.text:
                            st.warning("⚠️ 本课核心知识点掌握欠佳，建议重新复习『微课卡片』后再战！")
                        else:
                            st.balloons()
                            st.success("🎉 太棒了！您已成功解锁本节课程，继续保持！")
                            
                    except Exception as e:
                        st.error("评分失败。")
            else:
                st.warning("请先输入您的回复话术！")
