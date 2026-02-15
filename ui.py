import streamlit as st
import os
from vertexai.preview import reasoning_engines
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="MedFlow AI", layout="centered")
st.title("🏥 MedFlow Clinical Intake")

# 1. Connect to your "Headless" ADK Engine
# You get this ID after running 'python engine.py'
REMOTE_ID = os.getenv("ENGINE_RESOURCE_ID")

@st.cache_resource
def load_remote_engine():
    return reasoning_engines.ReasoningEngine(REMOTE_ID)

# 2. Simple Chat UI
if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("Tell MedFlow how you are feeling..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 3. Call the "Brain"
    with st.spinner("Consulting Clinical Agents..."):
        engine = load_remote_engine()
        response = engine.query(message=prompt, consent=True)
        
        with st.chat_message("assistant"):
            # Display Triage as a Header
            level = response['triage']['level'].upper()
            st.subheader(f"Priority: {level}")
            st.write(response['clinical_summary']['summary'])
            
            # Show the Follow-up Questions
            st.info(f"**Follow-up:** {response['follow_up']['safety_net_advice']}")
            
    st.session_state.messages.append({"role": "assistant", "content": f"Triage: {level}"})