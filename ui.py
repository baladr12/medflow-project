import streamlit as st
import os
import vertexai
from vertexai.preview import reasoning_engines
from dotenv import load_dotenv

# Load local environment (GCP_PROJECT_ID, etc.)
load_dotenv()

# --- THEMEING & UI CONFIG ---
st.set_page_config(page_title="MedFlow AI", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #0A192F; color: #E6F1FF; }
    .stChatMessage { border: 1px solid #1f3a5f; border-radius: 15px; }
    .stSubheader { color: #64FFDA; }
    /* Success/Error boxes styling */
    .stAlert { background-color: #112240; border: 1px solid #64FFDA; color: white; }
    </style>
    """, unsafe_allow_html=True)

st.title("🏥 MedFlow Clinical Intake")

@st.cache_resource
def load_latest_engine():
    """
    Auto-discovers the latest MedFlow engine and WRAPS it 
    so it becomes a callable object with .query()
    """
    project = os.getenv("GCP_PROJECT_ID")
    location = os.getenv("GCP_LOCATION", "us-central1")
    target_display_name = "MedFlow_Clinical_Engine_v21"

    vertexai.init(project=project, location=location)

    try:
        # 1. List all engine resources
        engines = reasoning_engines.ReasoningEngine.list()
        
        # 2. Filter for our specific name
        matches = [e for e in engines if e.display_name == target_display_name]

        if not matches:
            st.error(f"❌ No engine found with name '{target_display_name}'.")
            return None

        # 3. Sort by creation time (newest first)
        latest_resource = sorted(matches, key=lambda x: x.create_time, reverse=True)[0]
        
        # 4. CRITICAL FIX: Wrap the resource ID in the ReasoningEngine class
        # This turns the "Metadata object" into an "Executable object"
        executable_engine = reasoning_engines.ReasoningEngine(latest_resource.resource_name)
        
        st.sidebar.success(f"Connected: {latest_resource.display_name}")
        st.sidebar.caption(f"Resource: {latest_resource.resource_name.split('/')[-1]}")
        
        return executable_engine
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
            try:
                # Use keyword arguments for the query
                response = engine.query(message=prompt, consent=True)
                
                if isinstance(response, dict) and response.get("status") == "error":
                    st.error(f"Engine Error: {response.get('message')}")
                else:
                    with st.chat_message("assistant"):
                        # 1. Triage Header
                        triage = response.get('triage', {})
                        level = str(triage.get('level', 'Unknown')).upper()
                        
                        if "1" in level or "URGENT" in level or "EMERGENCY" in level:
                            st.error(f"🚨 PRIORITY: {level}")
                        else:
                            st.success(f"✅ PRIORITY: {level}")

                        # 2. Summary & Workflow
                        st.markdown("### Clinical Summary")
                        summary_text = response.get('clinical_summary', {}).get('summary', 'No summary available.')
                        st.write(summary_text)
                        
                        advice = response.get('follow_up', {}).get('safety_net_advice', 'Follow standard clinical protocols.')
                        st.info(f"**Action:** {advice}")
                        
                        # 3. Metadata Footer
                        meta = response.get('metadata', {})
                        st.caption(f"Status: {response.get('workflow_status')} | Model: {meta.get('model')} | Latency: {meta.get('latency')}")

                    # Store assistant response in history
                    st.session_state.messages.append({
                        "role": "assistant", 
                        "content": f"**Triage:** {level}\n\n{summary_text}"
                    })
            except Exception as e:
                st.error(f"Query Failed: {str(e)}")

# --- SIDEBAR TOOLS ---
with st.sidebar:
    st.header("MedFlow Controls")
    st.divider()
    if st.button("Clear Chat Session"):
        st.session_state.messages = []
        st.rerun()
    
    st.divider()
    st.info("This interface automatically connects to the most recent 'MedFlow_Clinical_Engine_v21' deployment in your GCP project.")