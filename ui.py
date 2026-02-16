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
    """Auto-discovers and wraps the latest MedFlow engine based on display name."""
    project = os.getenv("GCP_PROJECT_ID")
    location = os.getenv("GCP_LOCATION", "us-central1")
    
    # This MUST match the display_name in your engine.py exactly
    target_display_name = "MedFlow_FORCE_FINAL_VERSION"

    vertexai.init(project=project, location=location)

    try:
        # 1. Fetch all deployed engines
        engines = reasoning_engines.ReasoningEngine.list()
        
        # 2. Filter for our specific engine name
        matches = [e for e in engines if e.display_name == target_display_name]
        
        if not matches:
            st.error(f"❌ No engine found with name '{target_display_name}'. Please check your deployment logs.")
            return None

        # 3. Sort by creation time to get the absolute latest version
        matches.sort(key=lambda x: x.create_time, reverse=True)
        latest_resource = matches[0]
        
        # 4. Extract deployment time for the Version Tag
        deployed_at = latest_resource.create_time.strftime("%b %d, %I:%M %p")
        
        # 5. Wrap the resource into an executable object
        executable_engine = reasoning_engines.ReasoningEngine(latest_resource.resource_name)
        
        # Sidebar Status Updates
        st.sidebar.success(f"Connected: {latest_resource.display_name}")
        st.sidebar.info(f"📅 Deployed: {deployed_at}") # <--- VERSION TAG ADDED
        st.sidebar.caption(f"Resource: ...{latest_resource.resource_name[-8:]}")
        st.sidebar.caption(f"Patient Session: {st.session_state.patient_id}")
        
        return executable_engine
    except Exception as e:
        st.error(f"Discovery Error: {str(e)}")
        return None

# --- CHAT LOGIC ---
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display Chat History
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# User Input
if prompt := st.chat_input("How are you feeling today?"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.spinner("Clinical Agents are reviewing your case..."):
        # Discovery happens here automatically
        engine = load_latest_engine()
        
        if engine:
            try:
                # Execute query on the cloud engine
                response = engine.query(
                    message=prompt, 
                    consent=True, 
                    patient_id=st.session_state.patient_id
                )
                
                with st.chat_message("assistant"):
                    # 1. Triage Priority Header
                    triage = response.get('triage', {})
                    level = str(triage.get('level', 'Unknown')).upper()
                    
                    if any(word in level for word in ["EMERGENCY", "URGENT", "RED", "1"]):
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
                    metadata = response.get('metadata', {})
                    st.caption(f"Status: {response.get('workflow_status')} | Latency: {metadata.get('latency')} | Trace: {metadata.get('trace_id')}")

                    # 5. Developer Debugging (Checking GCS memory Latch)
                    with st.expander("🔍 Raw Agent Response Data"):
                        st.json(response)

                # Save assistant response to history
                st.session_state.messages.append({
                    "role": "assistant", 
                    "content": f"**Triage:** {level}\n\n**Advice:** {advice}"
                })
                
            except Exception as e:
                st.error(f"Cloud Engine Error: {str(e)}")

# --- SIDEBAR TOOLS ---
with st.sidebar:
    st.header("MedFlow Controls")
    if st.button("Clear Chat Session"):
        st.session_state.messages = []
        # Rotating the patient_id resets the memory latch in GCS
        st.session_state.patient_id = f"TEMP-{uuid.uuid4().hex[:8].upper()}"
        st.rerun()