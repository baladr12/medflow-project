🏥 MedFlow: Enterprise Clinical Reasoning Engine
MedFlow is a state-aware, multi-agent medical triage system built on Google Vertex AI Reasoning Engine. It transforms raw patient narratives into structured, actionable clinical insights by combining deterministic safety guardrails with the advanced generative reasoning of Gemini 2.0 Flash.

🏗️ 7-Agent Architecture
MedFlow utilizes a specialized multi-agent orchestration pattern. Each agent is a discrete logical unit designed to perform a specific function within the clinical pipeline:

Patient Understanding (Intake): Extracts symptoms, duration, and severity from unstructured patient chat.

Investigation Agent: Analyzes gaps in data and generates diagnostic-specific follow-up questions.

Clinical Triage Agent: Categorizes risks (Emergency, Urgent, Routine) using hybrid deterministic/AI logic.

Clinical Summary Agent: Translates technical data into professional clinician notes and chief complaints.

Evaluation Agent (Safety Gate): Conducts a "silent review" of the triage decision to ensure safety compliance.

Workflow Automation Agent: Manages EHR integration and persists records to BigQuery.

Memory Agent (The Latch): Manages "Sticky Triage" states by syncing session data to Google Cloud Storage.

🧠 Core Clinical Logic
🔒 The GCS Latch (Sticky Memory)
MedFlow implements a "Sticky Priority" logic. If a patient triggers an Emergency state (e.g., chest pain), the system "latches" that status. Even if the patient later reports feeling better, the session remains locked in Emergency status until the encounter is closed, preventing dangerous de-escalations during active symptoms.

🕵️ Investigation Mandate
To prevent "vague-in, vague-out" results, the engine is mandated to investigate. In Routine or Urgent cases, the engine must generate a questions_to_ask array. This forces the UI to provide interactive buttons that help rule out high-risk pathologies (e.g., asking for the specific quadrant of abdominal pain).

🛡️ Deterministic Guardrails (triage_rules.py)
Before the LLM processes the data, a hard-coded Python layer scans for high-sensitivity keywords (Red Flags):

Cardiac: Chest pain, radiating arm pain, SOB.

Neurological: Facial drooping, slurred speech, sudden confusion.

Abdominal: RLQ (Right Lower Quadrant), rigid abdomen, rebound tenderness.

🛠️ Technical Stack
Language: Python 3.11+

LLM: Gemini 2.0 Flash (Vertex AI)

Orchestration: Vertex AI Reasoning Engine (v1beta1)

Storage: Google Cloud Storage (Session Latch) & BigQuery (EHR Records)

Observability: Google Cloud Logging & Custom Manager

UI: Streamlit (Enterprise Dashboard)

🚀 Deployment & Installation
1. Environment Setup
Create a .env file with your GCP credentials:

Code snippet
GCP_PROJECT_ID="your-project-id"
GCP_LOCATION="us-central1"
GCS_MEMORY_BUCKET="your-session-bucket"
GEMINI_MODEL="gemini-2.0-flash"
GCP_SERVICE_ACCOUNT="medflow-deployer@your-project.iam.gserviceaccount.com"
2. Deploy to Vertex AI
The engine.py script handles the remote build and deployment:

Bash
python engine.py
The script automatically detects SDK versions and falls back to default identities if service account parameters are unsupported locally.

3. Launch the Dashboard
Bash
streamlit run streamlit_ui_app.py
📊 API Schema Example
MedFlow returns a standardized JSON object for every turn:

JSON
{
  "triage": {
    "level": "emergency",
    "reasoning": "RLQ pain + Fever indicates possible appendicitis.",
    "questions": [],
    "confidence_score": 0.95
  },
  "follow_up": {
    "safety_net_advice": "Proceed to the nearest Emergency Room immediately.",
    "questions_to_ask": []
  },
  "metadata": {
    "patient_id": "TEMP-B03100C2",
    "latency": "4.09s"
  }
}


graph TD
    %% User Layer
    User((Patient/Clinician)) -->|Input| Streamlit[Streamlit Frontend]
    
    %% Orchestration Layer
    subgraph "Google Cloud Platform (Vertex AI)"
        Streamlit -->|gRPC/REST| RE[Reasoning Engine Runtime]
        RE -->|System Prompt| Gemini[Gemini 2.0 Flash]
        
        subgraph "7-Agent Pipeline"
            Gemini --> Triage[Triage Agent]
            Gemini --> Extract[Extraction Agent]
            Gemini --> Safety[Safety Guardrail]
        end
    end

    %% Persistence Layer
    subgraph "Data & State"
        RE <-->|Sticky Latch| GCS[(Cloud Storage: Session State)]
        RE -->|InsertRow| BQ[(BigQuery: Clinical Records)]
    end

    %% Identity Layer
    IAM[IAM: medflow-ai-runner] -.->|Permissions| RE
    IAM -.->|Access| BQ
    IAM -.->|Access| GCS

    %% Styling
    style RE fill:#4285F4,color:#fff
    style Gemini fill:#34A853,color:#fff
    style BQ fill:#FBBC05,color:#000
    style GCS fill:#EA4335,color:#fff

    
📜 Disclaimer
MedFlow is a Clinical Decision Support (CDS) tool. It is intended for healthcare professional use or as a screening aid. It does not provide medical diagnoses or replace the judgment of a licensed physician. In case of a real medical emergency, users should contact emergency services (911) immediately.