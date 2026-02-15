import streamlit as st
import os
import uuid
import vertexai
from vertexai.preview import reasoning_engines
from dotenv import load_dotenv

# Load local environment
load_dotenv()

# --- THEMEING & UI CONFIG ---
st.set_page_config(page_title="MedFlow AI", layout="wide")

# Persistent Patient ID for the session (No Login Required)
if "patient_id" not in st.session_state:
    st.session_state.patient_id = f"TEMP-{uuid.uuid4().hex[:8].upper()}"

st.markdown("""
    <style>
    .stApp { background-color: #0A192F; color: #E6F1FF; }
    .stChatMessage { border: 1px solid #1f3a5f; border-radius: 15px; }
    .stSubheader { color: #64FFDA; font-weight: bold; }
    .report-card { 
        background-color: #112240; 
        padding: 20px; 
        border-radius: 10px; 
        border-left: 5px solid #64FFDA;
        margin-bottom: 20px;
    }
    </style>
    """, unsafe_allow_html=True)

st.title("🏥 MedFlow Clinical Intake")

@st.cache_resource
def load_latest_engine():
    """Auto-discovers and wraps the latest MedFlow engine."""
    project = os.getenv("GCP_PROJECT_ID")
    location = os.getenv("GCP_LOCATION", "us-central1")
    target_display_name = "MedFlow_Clinical_Engine_v21"

    vertexai.init(project=project, location=location)

    try:
        engines = reasoning_engines.ReasoningEngine.list()
        matches = [e for e in engines if e.display_name == target_display_name]
        if not matches:
            st.error(f"❌ No engine found with name '{target_display_name}'.")
            return None

        latest_resource = sorted(matches, key=lambda x: x.create_time, reverse=True)[0]
        executable_engine = reasoning_engines.ReasoningEngine(latest_resource.resource_name)
        
        st.sidebar.success(f"Connected: {latest_resource.display_name}")
        st.sidebar.caption(f"Patient Session: {st.session_state.patient_id}")
        return executable_engine
    except Exception as e:
        st.error(f"Discovery Error: {str(e)}")
        return None

# --- CHAT LOGIC ---
if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("How are you feeling today?"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.spinner("Clinical Agents are reviewing your case..."):
        engine = load_latest_engine()
        
        if engine:
            try:
                # UPDATED: Passing the temporary patient_id to the engine
                response = engine.query(
                    message=prompt, 
                    consent=True, 
                    patient_id=st.session_state.patient_id
                )
                
                with st.chat_message("assistant"):
                    # 1. Triage Priority Header
                    triage = response.get('triage', {})
                    level = str(triage.get('level', 'Unknown')).upper()
                    
                    if any(word in level for word in ["EMERGENCY", "URGENT", "1"]):
                        st.error(f"### 🚨 PRIORITY: {level}")
                    else:
                        st.success(f"### ✅ PRIORITY: {level}")

                    # 2. Structured Clinical Report
                    summary_data = response.get('clinical_summary', {})
                    st.markdown(f"#### Chief Complaint: {summary_data.get('chief_complaint', 'N/A')}")
                    
                    with st.container():
                        st.markdown('<div class="report-card">', unsafe_allow_html=True)
                        col1, col2 = st.columns([2, 1])
                        
                        with col1:
                            st.subheader("Patient History")
                            st.write(summary_data.get('history', 'N/A'))
                            
                            st.subheader("Clinician Notes")
                            st.info(summary_data.get('clinician_note', 'N/A'))
                        
                        with col2:
                            st.subheader("Red Flags")
                            flags = summary_data.get('red_flags_identified', [])
                            if flags:
                                for flag in flags:
                                    st.write(f"🚩 {flag}")
                            else:
                                st.write("No acute red flags detected.")
                        st.markdown('</div>', unsafe_allow_html=True)

                    # 3. Actionable Advice
                    advice = response.get('follow_up', {}).get('safety_net_advice', 'Follow standard protocols.')
                    st.warning(f"**Immediate Action Required:** {advice}")
                    
                    # 4. Metadata & Status
                    st.caption(f"Status: {response.get('workflow_status')} | Latency: {response.get('metadata', {}).get('latency')} | Trace: {response.get('metadata', {}).get('trace_id')}")

                    # 5. Developer Debugging
                    with st.expander("🔍 Raw Agent Response Data"):
                        st.json(response)

                st.session_state.messages.append({
                    "role": "assistant", 
                    "content": f"**Triage:** {level}\n\n**Complaint:** {summary_data.get('chief_complaint')}"
                })
            except Exception as e:
                st.error(f"Query Failed: {str(e)}")

# --- SIDEBAR TOOLS ---
with st.sidebar:
    st.header("MedFlow Controls")
    if st.button("Clear Chat Session"):
        st.session_state.messages = []
        # Reset ID on clear to simulate a new patient
        st.session_state.patient_id = f"TEMP-{uuid.uuid4().hex[:8].upper()}"
        st.rerun()