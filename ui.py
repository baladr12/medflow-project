import streamlit as st
import os
import vertexai
from vertexai.preview import reasoning_engines
from dotenv import load_dotenv

load_dotenv()

# --- CLINICAL THEMEING ---
st.set_page_config(page_title="MedFlow AI", layout="centered")

st.markdown("""
    <style>
    .stApp { background-color: #0A192F; color: #E6F1FF; }
    .stChatMessage { border: 1px solid #1f3a5f; border-radius: 15px; }
    </style>
    """, unsafe_allow_html=True)

st.title("🏥 MedFlow Clinical Intake")

REMOTE_ID = os.getenv("ENGINE_RESOURCE_ID")

@st.cache_resource
def load_remote_engine():
    vertexai.init(
        project=os.getenv("GCP_PROJECT_ID"),
        location=os.getenv("GCP_LOCATION", "us-central1")
    )
    return reasoning_engines.ReasoningEngine(REMOTE_ID)

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("Tell MedFlow how you are feeling..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.spinner("Consulting Clinical Agents..."):
        try:
            engine = load_remote_engine()
            # Important: We pass consent=True for the workflow agent
            response = engine.query(message=prompt, consent=True)
            
            if response.get("status") == "error":
                st.error(f"Engine Error: {response.get('message')}")
            else:
                with st.chat_message("assistant"):
                    # 1. Triage Badge
                    level = response['triage']['level'].upper()
                    if "URGENT" in level or "1" in level or "2" in level:
                        st.error(f"🚨 PRIORITY: {level}")
                    else:
                        st.success(f"✅ PRIORITY: {level}")
                    
                    # 2. Clinical Summary
                    st.markdown("### Clinical Summary")
                    st.write(response['clinical_summary']['summary'])
                    
                    # 3. Safety Net
                    st.info(f"**Safety Advice:** {response['follow_up']['safety_net_advice']}")
                    
                    # 4. Latency Metadata
                    st.caption(f"Latency: {response['metadata']['latency']} | System: {response['metadata'].get('engine', 'MedFlow-v21')}")

                st.session_state.messages.append({"role": "assistant", "content": f"Triage: {level}"})
        
        except Exception as e:
            st.error("🚨 The Clinical Engine is currently re-configuring. Please try again in 30 seconds.")
            st.expander("Technical Details").code(str(e))