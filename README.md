# medflow-project
A safe, transparent, automated triage assistant can significantly reduce workload and improve patient flow.
# 🏥 MedFlow AI: Clinical Triage Orchestrator (v20)

MedFlow AI is a safety-first, multi-agent patient intake system powered by **Gemini 2.0 Flash**. It automates the transition from raw patient symptoms to structured clinical records while maintaining strict medical guardrails.

---

## 🧩 Multi-Agent Architecture

This system replaces "single-prompt" AI with a specialized **7-Agent Pipeline**. Each agent has a specific clinical responsibility:

| Agent | Responsibility | Logic Type |
| :--- | :--- | :--- |
| **1. Intake** | Extraction of symptoms & red flags | LLM (Structured) |
| **2. Triage** | Risk level assignment | **Hybrid** (Rules + LLM) |
| **3. Summary** | Clinical documentation for GPs | LLM (Professional) |
| **4. Workflow** | EHR persistence & SHA-256 Hashing | Deterministic |
| **5. Memory** | Stable attribute tracking (Allergies/Meds) | LLM (MAC Pattern) |
| **6. FollowUp** | Risk-stratified safety netting | LLM (Contextual) |
| **7. Evaluation**| Quality Audit & Safety Scoring | **Hybrid** (Judge + Rules) |



---

## 🛡️ Clinical Safety Features

* **Deterministic Guardrails**: Uses `triage_rules.py` to identify high-risk symptoms (e.g., Chest Pain, SOB) before the LLM processes the data, preventing "under-triage."
* **Integrity Hashing**: Clinical data is hashed using SHA-256. If data is modified before patient consent is captured, the system blocks the EHR write.
* **Audit Trail**: Every transaction generates a vertical timeline trace, providing transparency into which agent made which decision.
* **Safety Netting**: Automatically generates "Red Flag" advice for patients (e.g., "If symptoms worsen, call emergency services immediately").

---

## 🚀 Getting Started

### 1. Project Structure
```text
├── agent.py               # Flask Orchestrator (Backend)
├── app.py                 # Streamlit Dashboard (Frontend)
├── agents/                # Agent definitions (1-7)
├── tools/                 # EHRStore and triage_rules.py
├── observability/         # Centralized logs & metrics
└── memory/                # Long-term patient profile logic

2. Deployment (Vertex AI)
Build the custom container for Google Cloud:

docker build -t gcr.io/[PROJECT_ID]/medflow-brain:v20 .
gcloud auth configure-docker
docker push gcr.io/[PROJECT_ID]/medflow-brain:v20

⚖️ Clinical Disclaimer
Note: MedFlow AI is a Clinical Decision Support (CDS) tool intended for use by healthcare professionals. It is not a replacement for professional medical judgment, diagnosis, or treatment. Always verify AI-generated summaries against raw patient data.

📊 Observability & Monitoring
The system integrates with Google Cloud Logging. Metrics are captured for:

Triage Severity Distribution (Emergency vs. Routine)
End-to-End Pipeline Latency
Agent-level success/failure rates