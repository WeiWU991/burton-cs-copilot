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

# ================= 核心逻辑：智能合规过滤 =================

@st.cache_resource
def load_banned_words():
    """从 knowledge_base 文件夹自动读取敏感词"""
    banned_set = set()
    txt_files = glob.glob(os.path.join(KB_FOLDER, "*.txt"))
    for txt_file in txt_files:
        try:
            with open(txt_file, "r", encoding='utf-8') as f:
                content = f.read()
                raw_words = re.split(r"[,\n\s']+", content)
                for w in raw_words:
                    clean_w = w.strip('"').strip("'").strip()
                    if len(clean_w) > 1:
                        banned_set.add(clean_w)
        except Exception:
            pass
    return banned_set

def highlight_banned_words(text, banned_set):
    """【内控模式】标红敏感词"""
    if not banned_set: return text, False
    found = False
    for word in banned_set:
        if word in text:
            found = True
            text = text.replace(word, f":red[**🚫{word}**]")
    return text, found

def shield_banned_words(text, banned_set):
    """【外发模式】直接替换敏感词"""
    if not banned_set: return text, False
    found = False
    for word in banned_set:
        if word in text:
            found = True
            text = text.replace(word, "**") 
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
    
    # 打印后台日志
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

    st.caption("🛡️ 合规护盾")
    if st.session_state.banned_words:
        st.success(f"✅ 智能激活 ({len(st.session_state.banned_words)} 词条)")
        st.info("👀 画像分析区：高亮敏感词\n📋 话术复制区：自动屏蔽")
    else:
        st.warning("⚠️ 未激活")

    st.divider()

    model_choice = st.radio(
        "🧠 大脑引擎:",
        ("⚡ 极速模式 (Gemini 3 Flash)", "🐢 深度思考 (Gemini 3 Pro)"),
        index=0
    )
    selected_model_name = "gemini-3-flash-preview" if "Flash" in model_choice else "gemini-3-pro-preview"

    st.divider()

    if st.button("接待新客户 (清空记忆)", type="primary", use_container_width=True):
        st.session_state.chat_history = []
        st.rerun()

# ================= 主界面 =================
st.title("🏂 Burton China CS CO-Pilot")
st.caption("🚀 Powered by YZ-Shield | Native RAG | 🛡️极限词过滤")
st.divider() 

# --- 对话工作台 ---
if st.session_state.chat_history:
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
1. **合规第一**：严禁使用中国广告法禁止的极限词（如：第一、最强、顶级、首选、全网独家）。如果文档里有这些词，**尽量在回复时替换为合规同义词**。
2. **精准查询**：查询价格、参数时，必须严格对应文档中的表格数据。
3. **价格高亮**：使用 `:orange[**¥价格**]` 格式。
4. **硬性销售逻辑**：选板必问体重；Step On必问鞋码。
5. **格式严格**：必须严格遵守下面的 Markdown 结构，标题不可更改。

# 输出视图结构
---
### 1️⃣ 🧠 客户画像分析
* **客户类型**: 
* **关键缺项**: [⚠️ 高亮显示]
* **情绪指数**: [⭐⭐⭐⭐⭐]

### 2️⃣ 📚 核心知识胶囊
* **推荐产品**: 
* **参考价格**: :orange[**¥xxxx**] (数据来源: [文件名])
* **核心科技**: 
* **技术解释**: 

### 3️⃣ 💬 建议回复话术
> **请复制以下内容发送给客户：**
> "[建议回复内容。请确保语气亲切，并**尝试**避免极限词。]"

### 4️⃣ 🎯 关联销售机会
* **推荐搭配**: 
* **种草理由**: 
---
"""

user_query = st.chat_input("在此输入客户问题 (例如：这款板子是不是全网第一？)...")

if user_query:
    if not api_key:
        st.error("请先配置 API Key")
    elif not st.session_state.gemini_files:
        st.error(f"⚠️ 知识库未加载，请确保 {KB_FOLDER} 文件夹内有 .md 文件并重启 App。")
    else:
        # 1. 记录提问日志
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n📝 [新提问] {timestamp}\n👤 客服: {user_query}", flush=True)

        with st.chat_message("user", avatar="👤"):
            st.write(user_query)
        
        try:
            model = genai.GenerativeModel(
                model_name=selected_model_name,
                system_instruction=system_instruction
            )
            
            gemini_history = []
            for role, text in st.session_state.chat_history[-6:]:
                gemini_role = "user" if role == "user" else "model"
                gemini_history.append({"role": gemini_role, "parts": [text]})

            chat = model.start_chat(history=gemini_history)
            
            with st.chat_message("assistant", avatar="🏂"):
                with st.spinner("🤖 YZ-Shield 正在检索企业知识库..."):
                    response = chat.send_message(st.session_state.gemini_files + [user_query])
                    
                    # 智能分层过滤 (用于前端展示)
                    final_text_display, has_issues = smart_compliance_filter(response.text, st.session_state.banned_words)
                    
                    st.markdown(final_text_display)
                    
                    if has_issues:
                        st.toast("🛡️ 已执行合规处理：内部分析标红，外发话术已屏蔽。", icon="✅")
                    
                    # 2. 记录回答日志 (新增功能)
                    # 为了日志整洁，我们在日志里也记录处理过(已屏蔽)的版本，或者您可以选择 response.text 记录原始内容
                    print(f"🤖 AI回复: \n{final_text_display}\n" + "-"*50, flush=True)
            
            st.session_state.chat_history.append(("user", user_query))
            st.session_state.chat_history.append(("assistant", response.text))
                
        except Exception as e:
            st.error(f"生成失败: {e}")
            print(f"❌ [生成错误] {e}", flush=True)
            if "404" in str(e):
                st.warning("提示：请检查 API Key 是否支持 Gemini 3 Preview 模型。")
