import streamlit as st
import os
import vertexai
from vertexai.preview import reasoning_engines
from dotenv import load_dotenv

# Load local environment (GCP_PROJECT_ID, etc.)
load_dotenv()

# --- THEMEING & UI CONFIG ---
st.set_page_config(page_title="MedFlow AI", layout="centered")

st.markdown("""
    <style>
    .stApp { background-color: #0A192F; color: #E6F1FF; }
    .stChatMessage { border: 1px solid #1f3a5f; border-radius: 15px; }
    .stSubheader { color: #64FFDA; }
    </style>
    """, unsafe_allow_html=True)

st.title("🏥 MedFlow Clinical Intake")

@st.cache_resource
def load_latest_engine():
    """
    Auto-discovers the latest MedFlow engine by Display Name.
    No more manual Resource ID updates!
    """
    project = os.getenv("GCP_PROJECT_ID")
    location = os.getenv("GCP_LOCATION", "us-central1")
    target_display_name = "MedFlow_Clinical_Engine_v21"

    vertexai.init(project=project, location=location)

    try:
        # 1. List all engines in the region
        engines = reasoning_engines.ReasoningEngine.list()
        
        # 2. Filter by the specific display name we used in engine.py
        matches = [e for e in engines if e.display_name == target_display_name]

        if not matches:
            st.error(f"❌ No engine found with name '{target_display_name}'. Did you run engine.py?")
            return None

        # 3. Sort by creation time to get the newest deployment
        latest_engine = sorted(matches, key=lambda x: x.create_time, reverse=True)[0]
        
        # Short-lived success message in sidebar
        st.sidebar.success(f"Connected: {latest_engine.display_name}")
        st.sidebar.caption(f"ID: ...{latest_engine.resource_name[-6:]}")
        
        return latest_engine
    except Exception as e:
        st.error(f"Failed to discover engine: {str(e)}")
        return None

# --- CHAT LOGIC ---
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display message history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# User input
if prompt := st.chat_input("How are you feeling today?"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Call the discovered Engine
    with st.spinner("Clinical Agents are reviewing your case..."):
        engine = load_latest_engine()
        
        if engine:
            # Query the cloud engine
            response = engine.query(message=prompt, consent=True)
            
            if response.get("status") == "error":
                st.error(f"Engine Execution Error: {response.get('message')}")
            else:
                with st.chat_message("assistant"):
                    # 1. Triage Header
                    triage = response['triage']
                    level = triage['level'].upper()
                    
                    if "1" in level or "URGENT" in level:
                        st.error(f"🚨 PRIORITY: {level}")
                    else:
                        st.success(f"✅ PRIORITY: {level}")

                    # 2. Summary & Workflow
                    st.markdown("### Clinical Summary")
                    st.write(response['clinical_summary']['summary'])
                    
                    st.info(f"**Action:** {response['follow_up']['safety_net_advice']}")
                    
                    # 3. Metadata Footer
                    st.caption(f"Status: {response['workflow_status']} | Latency: {response['metadata']['latency']}")

                # Store assistant response in history
                st.session_state.messages.append({
                    "role": "assistant", 
                    "content": f"**Triage:** {level}\n\n{response['clinical_summary']['summary']}"
                })

# --- SIDEBAR TOOLS ---
with st.sidebar:
    st.divider()
    if st.button("Clear Chat Session"):
        st.session_state.messages = []
        st.rerun()