# 🏥 MedFlow — Enterprise Clinical Reasoning Engine

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![Vertex AI](https://img.shields.io/badge/Vertex%20AI-Reasoning%20Engine-4285F4.svg)](https://cloud.google.com/vertex-ai)
[![Gemini](https://img.shields.io/badge/Gemini-2.0%20Flash-34A853.svg)](https://deepmind.google/technologies/gemini/)
[![Status](https://img.shields.io/badge/Status-Active-brightgreen.svg)]()

> **MedFlow is not a medical chatbot. It is a State-Aware Clinical Reasoning Engine.**

MedFlow transforms raw, unstructured patient narratives into structured, actionable clinical insights by combining **deterministic safety guardrails** with the generative reasoning of **Gemini 2.0 Flash** — deployed on Google Vertex AI Reasoning Engine.

Built for healthcare platforms and clinical decision support workflows that require AI to be not just intelligent, but **accountable, auditable, and safe-by-construction**.

📄 **[Read the full architecture deep-dive on Medium](https://medium.com/@balarajendran12)**

---

## 🏗️ Architecture Overview

MedFlow executes a strict 7-agent pipeline on every patient query. No agent does more than its defined job. Every step is traced end-to-end via a shared `trace_id`.

```
Streamlit UI
     │
     ▼
engine.py · MedFlowReasoningEngine.query()
     │
     ├── ObservabilityManager.start_request()     → trace_id issued
     ├── MemoryStore.load()                        → GCS: sessions/{patient_id}.json
     │
     ├── Agent 1 · PatientUnderstandingAgent       → symptoms, red_flags, severity
     ├── triage_rules.py · check_red_flags()       → deterministic safety (runs BEFORE LLM)
     ├── Agent 2 · ClinicalTriageAgent             → Gemini + Python final guardrail
     ├── Agent 3 · ClinicalSummaryAgent            → chief_complaint, clinician_note
     ├── Agent 4 · EvaluationAgent                 → rule_based_score + LLM-as-judge
     ├── Agent 5 · MemoryAgent                     → stable clinical attributes → GCS
     ├── Agent 6 · FollowUpAgent                   → safety_net_advice, follow_up_questions
     ├── Agent 7 · WorkflowAutomationAgent         → BigQuery (consent-gated)
     │
     └── ObservabilityManager.stop_timer()         → latency + trace_id → Cloud Logging
```

---

## 🤖 The 7 Agents

| # | Agent | Class | Responsibility |
|---|-------|-------|----------------|
| 1 | Patient Understanding | `PatientUnderstandingAgent` | Extracts symptoms, red_flags, severity from raw patient message via strict JSON schema |
| 2 | Clinical Triage | `ClinicalTriageAgent` | Hybrid triage — deterministic rule result injected into Gemini system_instruction + Python final override |
| 3 | Clinical Summary | `ClinicalSummaryAgent` | Produces structured GP summary: chief_complaint, history, clinician_note |
| 4 | Evaluation (Auditor) | `EvaluationAgent` | Dual audit: rule_based_score() + llm_judge() — safety_pass gate before any output reaches user |
| 5 | Memory | `MemoryAgent` | Extracts stable clinical attributes only (age, conditions, allergies, meds) — temporary symptoms excluded |
| 6 | Follow-Up | `FollowUpAgent` | Risk-stratified safety-netting: emergency → location questions, urgent → symptom progression, routine → monitoring guidelines |
| 7 | Workflow Automation | `WorkflowAutomationAgent` | EHR integration + BigQuery persistence — fires only if `consent=True` |

---

## 🛡️ Core Safety Mechanisms

### 1. The GCS Latch (Sticky Triage)

The most critical reliability feature in MedFlow. Once a session is classified as `emergency`, that status is **locked in Google Cloud Storage** and cannot be de-escalated by any subsequent patient message — including "I feel better."

```python
# triage_rules.py — Rule 1 runs FIRST, before any symptom is read
previous_priority = str(data.get("previous_priority", "routine")).lower().strip()
if previous_priority == "emergency":
    return "emergency"   # LLM never called
```

In early prototypes without this latch, the system down-triaged active emergencies in ~30% of sessions where patients reported improvement mid-encounter. The latch reduced this to zero.

### 2. triage_rules.py — Deterministic Guardrail (4-Rule Priority Chain)

Runs **before** any LLM call. Four rules in strict priority order:

| Rule | Logic | Returns |
|------|-------|---------|
| 1 — Sticky latch | `previous_priority == 'emergency'` | `emergency` immediately |
| 2 — Keyword scan | Match `red_flags + symptoms` against emergency keyword set | `emergency` |
| 3 — Urgent escalation | `severity == 'severe'` OR `moderate + high_risk_group` | `urgent` |
| 4 — Default routing | `severity == 'mild'` → self-care, else → routine | `self-care` / `routine` |

Emergency keyword coverage: cardiac (chest pain, SOB, arm pain), neurological (stroke, facial drooping, slurred speech, seizure), abdominal (RLQ, rigid abdomen, rebound tenderness), trauma/psych (heavy bleeding, suicidal ideation).

### 3. EvaluationAgent — Dual-Mode Audit

A structurally separate reasoning pass (temperature=0.0) that audits the pipeline's own output before anything reaches the user:

- **`rule_based_score()`** — applies hard deterministic checks. If high-risk symptom present but triage ≠ emergency: −60 penalty
- **`llm_judge()`** — Gemini scores `clinical_accuracy`, `triage_appropriateness`, `summary_clarity`, flags `dangerous_omissions`
- **`safety_pass`** requires: weighted score > 50 AND no dangerous omissions

### 4. Double Guardrail in ClinicalTriageAgent

The rule result from `triage_rules.py` is baked into the Gemini system_instruction AND re-checked after the LLM responds:

```python
# Final Python-level override — LLM cannot win against a rule
if rule_result == "emergency":
    result["level"] = "emergency"
    result["questions"] = []   # no follow-up questions in emergency
```

---

## 🛠️ Technical Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.11+ |
| LLM | Gemini 2.0 Flash (Vertex AI) |
| Orchestration | Vertex AI Reasoning Engine (v1beta1) |
| Session state | Google Cloud Storage — `sessions/{patient_id}.json` |
| Long-term records | BigQuery — `clinical_records.triage_cases` |
| Observability | Google Cloud Logging + custom `ObservabilityManager` |
| UI | Streamlit |
| CI/CD | GitHub Actions (`deploy.yml`) |

**Temperature settings by agent** (deliberate, not default):
- `PatientUnderstandingAgent` → `0.1` (flexible extraction)
- `ClinicalSummaryAgent` → `0.2` (natural clinical language)
- `ClinicalTriageAgent` → `0.0` (deterministic decisions)
- `EvaluationAgent` → `0.0` (strict audit)

---

## 📁 Project Structure

```
medflow-project/
├── engine.py                      # Main orchestrator · MedFlowReasoningEngine
├── ui.py                          # Streamlit dashboard
├── requirements.txt
│
├── agents/
│   ├── patient_understanding.py   # Agent 1 — extraction + schema enforcement
│   ├── clinical_triage.py         # Agent 2 — hybrid triage (rules + Gemini)
│   ├── clinical_summary.py        # Agent 3 — GP clinician note
│   ├── evaluation_agent.py        # Agent 4 — dual-mode safety auditor
│   ├── followup_agent.py          # Agent 6 — risk-stratified safety netting
│   └── workflow_automation.py     # Agent 7 — consent-gated BigQuery persistence
│
├── memory/
│   ├── memory_agent.py            # Agent 5 — stable attribute extraction
│   └── memory_store.py            # GCS read/write for session state
│
├── tools/
│   ├── triage_rules.py            # Deterministic guardrail (runs before LLM)
│   └── ehr_store.py               # EHR integration layer
│
├── observability/
│   └── manager.py                 # trace_id issuance + Cloud Logging
│
└── .github/
    └── workflows/
        └── deploy.yml             # CI/CD → Vertex AI Reasoning Engine
```

---

## 🚀 Getting Started

### Prerequisites

- Python 3.11+
- A Google Cloud project with Vertex AI, BigQuery, Cloud Storage, and Cloud Logging APIs enabled
- A GCS bucket for session state
- A service account with appropriate IAM roles

### 1. Clone and install

```bash
git clone https://github.com/baladr12/medflow-project.git
cd medflow-project
pip install -r requirements.txt
```

### 2. Configure environment

Create a `.env` file in the project root:

```env
GCP_PROJECT_ID="your-project-id"
GCP_LOCATION="us-central1"
GCS_MEMORY_BUCKET="your-session-bucket"
GEMINI_MODEL="gemini-2.0-flash"
GCP_SERVICE_ACCOUNT="medflow-deployer@your-project.iam.gserviceaccount.com"
```

### 3. Deploy to Vertex AI Reasoning Engine

```bash
python engine.py
```

The script auto-detects SDK versions and falls back gracefully if `service_account` parameter is unsupported.

### 4. Launch the Streamlit dashboard

```bash
streamlit run ui.py
```

---

## 📊 API Response Schema

Every `query()` call returns a standardised JSON object:

```json
{
  "triage": {
    "level": "emergency",
    "reasoning": "RLQ pain + fever indicates possible appendicitis.",
    "questions": [],
    "confidence_score": 0.95
  },
  "clinical_summary": {
    "chief_complaint": "Acute RLQ abdominal pain with fever",
    "clinician_note": "Patient presents with RLQ pain, febrile. Appendicitis cannot be excluded.",
    "risk_level": "emergency",
    "recommended_action": "Immediate ED referral."
  },
  "follow_up": {
    "safety_net_advice": "Proceed to the nearest Emergency Room immediately.",
    "questions_to_ask": []
  },
  "workflow_status": "Logged",
  "metadata": {
    "patient_id": "TEMP-B03100C2",
    "latency": "4.09s",
    "trace_id": "abc123",
    "model": "gemini-2.0-flash"
  }
}
```

---

## 🔑 Key Design Decisions

**Why deterministic rules before the LLM?**
Probability should never override pre-defined safety rules in a clinical context. `triage_rules.py` provides a hard guarantee that certain symptom combinations will always trigger emergency — regardless of how the patient phrases their message.

**Why GCS for session state and not in-memory?**
The Vertex AI Reasoning Engine is stateless between requests. GCS provides durable, persistent session state that survives across turns, deployments, and restarts. The sticky latch only works because state is external.

**Why schema enforcement on every Gemini call?**
Without `response_schema`, key names drift between model versions and temperature settings. Every agent in MedFlow treats LLM output as an API contract, not free text. This eliminated an entire class of downstream KeyError bugs.

**Why is consent checked in `engine.py` and not the UI?**
Healthcare data persistence should never depend on a frontend checkbox reaching the backend correctly. The `consent=True` gate is enforced at the code level in `WorkflowAutomationAgent`.

---

## ⚠️ Disclaimer

MedFlow is a **Clinical Decision Support (CDS)** tool intended for healthcare professional use or as a screening aid. It does **not** provide medical diagnoses or replace the judgment of a licensed physician.

**In case of a real medical emergency, contact emergency services (999 / 911) immediately.**

---

## 🤝 Connect

Built by **Devi Rajendran**

- 📄 [Full architecture article on Medium](https://medium.com/@balarajendran12/beyond-the-chatbot-engineering-a-multi-agent-clinical-reasoning-engine-on-vertex-ai-7e4872de99c4)
- 💼 [LinkedIn](https://www.linkedin.com/in/your-linkedin)
- 🔗 [GitHub](https://github.com/baladr12/medflow-project)

*If you are working on clinical AI, multi-agent systems, or production Vertex AI — feel free to open an issue, raise a PR, or connect directly.*
