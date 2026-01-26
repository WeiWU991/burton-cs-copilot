import streamlit as st
import google.generativeai as genai
import os
import glob
import time
import datetime
import re

# ================= 配置区 =================
st.set_page_config(page_title="Burton CS Co-pilot", page_icon="🏂", layout="wide")

# 定义知识库目录
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

# ================= 核心逻辑：智能合规过滤 (Smart Shield) =================

# 🟢 白名单
SAFE_WORDS = {
    "Burton", "BURTON", "burton", 
    "Anon", "ANON", "anon",
    "ak", "AK", "[ak]",
    "GORE-TEX", "Boa", "MIPS", 
    "Step On", "Est", "Re:Flex"
}

# 🔴 高频极限词的“安全替身”字典
SMART_SYNONYMS = {
    "第一": "排名前列",
    "NO.1": "人气热销",
    "Top1": "人气热销",
    "冠军": "人气优选",
    "首选": "优选",
    "顶级": "高端",
    "顶尖": "高端",
    "极致": "出色",
    "极佳": "出色",
    "完美": "理想",
    "绝佳": "非常棒",
    "独家": "特色",
    "独有": "特有",
    "最强": "强力",
    "最好": "很好",
    "最大": "很大",
    "最高": "很高",
    "最低": "超值",
    "全网": "全渠道",
    "世界级": "高水准",
    "史无前例": "难得一见",
    "永久": "长久",
    "百分之百": "致力于",
    "必": "建议",
}

@st.cache_resource
def load_banned_words():
    """从 knowledge_base 文件夹自动读取敏感词"""
    banned_set = set()
    txt_files = glob.glob(os.path.join(KB_FOLDER, "*.txt"))
    for txt_file in txt_files:
        try:
            with open(txt_file, "r", encoding='utf-8') as f:
                content = f.read()
                raw_words = re.split(r"[,\n\s'\"\[\]]+", content)
                for w in raw_words:
                    clean_w = w.strip()
                    if len(clean_w) > 1 and clean_w not in SAFE_WORDS and clean_w.lower() not in [s.lower() for s in SAFE_WORDS]:
                        banned_set.add(clean_w)
        except Exception:
            pass
    
    banned_set = {w for w in banned_set if w not in SAFE_WORDS and w.lower() not in [s.lower() for s in SAFE_WORDS]}
    return banned_set

def highlight_banned_words(text, banned_set):
    """【内控模式】标红敏感词"""
    if not banned_set: return text, False
    found = False
    for word in banned_set:
        if word in text:
            found = True
            suggestion = f" 💡建议改:{SMART_SYNONYMS[word]}" if word in SMART_SYNONYMS else ""
            text = text.replace(word, f":red[**🚫{word}**]{suggestion}")
    return text, found

def shield_banned_words(text, banned_set):
    """【外发模式】智能替换"""
    if not banned_set: return text, False
    found = False
    for word in banned_set:
        if word in text:
            found = True
            replacement = SMART_SYNONYMS.get(word, "") 
            text = text.replace(word, replacement)
    return text, found

def smart_compliance_filter(full_response, banned_set):
    """【智能分层过滤】"""
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
    has_issues = issue1 or issue2 or issue3
    
    return final_text, has_issues

@st.cache_resource
def load_knowledge_base_files():
    """自动加载知识库"""
    uploaded_refs = []
    if not os.path.exists(KB_FOLDER):
        os.makedirs(KB_FOLDER)
        return []
    md_files = glob.glob(os.path.join(KB_FOLDER, "*.md"))
    
    print(f"📚 [Load] Found {len(md_files)} markdown files", flush=True)
    
    for file_path in md_files:
        try:
            file_name = os.path.basename(file_path)
            file_ref = genai.upload_file(path=file_path, mime_type="text/plain", display_name=file_name)
            while file_ref.state.name == "PROCESSING":
                time.sleep(1)
                file_ref = genai.get_file(file_ref.name)
            uploaded_refs.append(file_ref)
            print(f"✅ Loaded: {file_name}", flush=True)
        except Exception as e:
            print(f"❌ Failed: {file_path} - {e}", flush=True)
    return uploaded_refs

# --- 系统初始化 ---
if api_key and not st.session_state.kb_loaded:
    with st.spinner("🚀 正在初始化 Burton 知识引擎..."):
        st.session_state.banned_words = load_banned_words()
        st.session_state.gemini_files = load_knowledge_base_files()
        st.session_state.kb_loaded = True

# ================= 侧边栏 =================
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/3/3b/Burton_Snowboards_logo.svg/2560px-Burton_Snowboards_logo.svg.png", width=150)
    st.title("⚙️ 系统状态")
    
    if api_key:
        st.success(api_status)
    else:
        st.error(api_status)
    
    st.divider()
    
    st.caption("📚 知识库 (管理员预置)")
    if st.session_state.gemini_files:
        for f in st.session_state.gemini_files:
            st.code(f"📄 {f.display_name}", language="text")
    else:
        st.warning(f"⚠️ 文件夹 {KB_FOLDER} 为空")

    st.caption("🛡️ 合规护盾 (智能版)")
    if st.session_state.banned_words:
        st.success(f"✅ 已激活 ({len(st.session_state.banned_words)} 词条)")
    else:
        st.warning("⚠️ 未激活")

    st.divider()

    model_choice = st.radio(
        "🧠 大脑引擎:",
        ("⚡ 极速模式 (Gemini 3 Flash)", "🐢 深度思考 (Gemini 3 Pro)"),
        index=0
    )
    selected_model_name = "gemini-3-flash-preview" if "Flash" in model_choice else "gemini-3-pro-preview"

    # 🔴 已移除“接待新客户”按钮，因为现在默认就是无记忆模式

# ================= 主界面 =================
st.title("🏂 Burton China CS CO-Pilot")
st.caption("🚀 Powered by YZ-Shield | Native RAG | 🛡️极限词保护")
st.divider() 

# --- 对话工作台 ---
if st.session_state.chat_history:
    # 依然显示最近的对话记录，方便客服查看上下文，但AI不会读取这些
    for role, text in st.session_state.chat_history[-6:]:
        if role == "user":
            with st.chat_message("user", avatar="👤"):
                st.write(text)
        else:
            with st.chat_message("assistant", avatar="🏂"):
                safe_text, _ = smart_compliance_filter(text, st.session_state.banned_words)
                st.markdown(safe_text)

# 核心 Prompt
system_instruction = """
你不是直接面对消费者的聊天机器人，你是 **Burton China 客服团队的智能副驾 (CS Copilot)**。
你的知识库已经由管理员预置（Markdown文档），数据精准且权威。

# 核心原则 (Critical)
1. **独立问答 (Stateless)**：请忽略任何之前的对话历史，仅根据本次提问进行回答。每一次提问都是一个全新的客户。
2. **价格策略 (Price Hiding)**：
   - 内部逻辑：利用文档价格筛选产品。
   - **严禁输出**：严禁在最终回复中写出具体的金额数字。
   - 话术替代：引导"具体价格请以店铺实时活动为准"。
3. **合规第一 (Compliance)**：严禁使用极限词（如：第一、最强、顶级）。请在生成时替换为合规同义词。
4. **精准查询**：除价格外，参数必须严格对应文档。
5. **硬性销售逻辑**：
   - 选板必问体重。
   - Step On必问鞋码。

# 输出视图结构
---
### 1️⃣ 🧠 客户画像分析
* **客户类型**: 
* **关键缺项**: [⚠️ 高亮显示]
* **情绪指数**: [⭐⭐⭐⭐⭐]

### 2️⃣ 📚 核心知识胶囊
* **推荐产品**: [仅写型号]
* **产品定位**: [例如：高端全能板] (🚫无价格)
* **核心科技**: 
* **技术解释**: 

### 3️⃣ 💬 建议回复话术
> **请复制以下内容发送给客户：**
> "[建议回复内容。语气亲切，严禁出现极限词，严禁出现具体价格数字。]"

### 4️⃣ 🎯 关联销售机会
* **推荐搭配**: 
* **种草理由**: 
---
"""

user_query = st.chat_input("在此输入客户问题 (例如：帮我选个8000左右的板子)...")

if user_query:
    if not api_key:
        st.error("请先配置 API Key")
    elif not st.session_state.gemini_files:
        st.error(f"⚠️ 知识库未加载，请确保 {KB_FOLDER} 文件夹内有 .md 文件并重启 App。")
    else:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n📝 [新提问] {timestamp}\n👤 客服: {user_query}", flush=True)

        with st.chat_message("user", avatar="👤"):
            st.write(user_query)
        
        try:
            model = genai.GenerativeModel(
                model_name=selected_model_name,
                system_instruction=system_instruction
            )
            
            # 🔴 关键修改：强制清空历史，每次都是全新对话
            # 这里的 history=[] 意味着 AI 不会看到之前的任何一句话
            chat = model.start_chat(history=[]) 
            
            with st.chat_message("assistant", avatar="🏂"):
                with st.spinner("🤖 YZ-Shield 正在独立思考 (无记忆模式)..."):
                    response = chat.send_message(st.session_state.gemini_files + [user_query])
                    
                    final_text_display, has_issues = smart_compliance_filter(response.text, st.session_state.banned_words)
                    
                    st.markdown(final_text_display)
                    
                    if has_issues:
                        st.toast("🛡️ 已替换极限词，价格已按策略隐藏。", icon="✅")
                    
                    print(f"🤖 AI回复: \n{final_text_display}\n" + "-"*50, flush=True)
            
            # 仅在 UI 层面保存历史，供客服回看
            st.session_state.chat_history.append(("user", user_query))
            st.session_state.chat_history.append(("assistant", response.text))
                
        except Exception as e:
            st.error(f"生成失败: {e}")
            print(f"❌ [生成错误] {e}", flush=True)
            if "404" in str(e):
                st.warning("提示：请检查 API Key 是否支持 Gemini 3 Preview 模型。")
