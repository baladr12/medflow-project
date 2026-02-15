import os
import vertexai
from vertexai.preview import reasoning_engines
from datetime import datetime, timezone
from dotenv import load_dotenv

# Load local environment for development
load_dotenv()

class MedFlowReasoningEngine:
    """
    MedFlow v21: Enterprise Clinical Reasoning Engine.
    Features: 7-Agent Orchestration, Observability, and Patient Isolation.
    """

    def __init__(self):
        # We initialize with None; these are set during deployment or in _setup
        self.project = os.getenv("GCP_PROJECT_ID")
        self.location = os.getenv("GCP_LOCATION", "us-central1")
        self.model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        self.bucket_name = os.getenv("GCS_MEMORY_BUCKET")
        self.dataset_id = "clinical_records"
        self.table_id = "triage_cases"
        
        # Object placeholders
        self.client = None
        self.obs = None
        self.intake = None
        self.triage = None
        self.summary = None
        self.workflow = None
        self.memory = None
        self.ehr = None
        self.mem_store = None

    def _setup(self):
        """Initializes agents and observability in the cloud environment."""
        if self.client is not None:
            return

        # Ensure environment variables are synced for Google SDKs
        if self.project:
            os.environ["GCP_PROJECT_ID"] = self.project
            os.environ["GOOGLE_CLOUD_PROJECT"] = self.project

        from google import genai
        from google.auth import default
        
        # Internal imports for Reasoning Engine compatibility
        from agents.patient_understanding import PatientUnderstandingAgent
        from agents.clinical_triage import ClinicalTriageAgent
        from agents.clinical_summary import ClinicalSummaryAgent
        from agents.workflow_automation import WorkflowAutomationAgent
        from memory.memory_agent import MemoryAgent
        from tools.ehr_store import EHRStore
        from memory.memory_store import MemoryStore
        from observability.manager import ObservabilityManager

        # 1. Initialize Observability & GenAI
        credentials, _ = default()
        self.obs = ObservabilityManager(name="medflow-engine")
        self.client = genai.Client(
            vertexai=True,
            project=self.project,
            location=self.location,
            credentials=credentials
        )

        # 2. Initialize Tools & Team
        self.ehr = EHRStore()         
        self.mem_store = MemoryStore()
        
        self.intake = PatientUnderstandingAgent(self.client)
        self.triage = ClinicalTriageAgent(self.client)
        self.summary = ClinicalSummaryAgent(self.client)
        self.workflow = WorkflowAutomationAgent(self.ehr)
        self.memory = MemoryAgent(self.client, self.mem_store)
        
        # Run infrastructure check (Dataset/Table creation)
        self._initialize_infrastructure()

    def _initialize_infrastructure(self):
        """Ensures GCP BigQuery resources exist autonomously."""
        from google.cloud import bigquery
        from google.api_core import exceptions

        # Use explicitly defined project to avoid 403 Access Denied on default project
        project_id = self.project or os.getenv("GCP_PROJECT_ID")
        if not project_id:
            return

        bq_client = bigquery.Client(project=project_id)
        full_dataset_id = f"{project_id}.{self.dataset_id}"
        
        # 1. Ensure Dataset Exists
        try:
            bq_client.get_dataset(full_dataset_id)
        except exceptions.NotFound:
            print(f"✨ Auto-provisioning dataset: {full_dataset_id}")
            dataset = bigquery.Dataset(full_dataset_id)
            dataset.location = self.location
            bq_client.create_dataset(dataset, timeout=30)
        except Exception as e:
            print(f"⚠️ Infrastructure Warning (Dataset): {e}")

        # 2. Table creation is handled by EHRStore during the first save attempt
        # but we check it here for total autonomy if needed.

    def query(self, message: str, consent: bool = False, patient_id: str = "anonymous"):
        """Main cloud execution point with observability and patient isolation."""
        self._setup()
        
        trace_id = self.obs.start_request()
        start_timer = self.obs.start_timer()

        try:
            # --- PATIENT CONTEXT SWITCH ---
            # Isolate this patient's long-term memory blob
            self.mem_store.blob_name = f"memory/{patient_id}.json"
            self.obs.add_trace("MemoryStore", f"Context set: {patient_id}")

            # 1. Extraction (PatientUnderstandingAgent)
            self.obs.add_trace("IntakeAgent", "Analyzing clinical input")
            raw_data = self.intake.analyse(message)
            
            # 2. Triage (ClinicalTriageAgent)
            self.obs.add_trace("TriageAgent", "Calculating priority")
            triage_results = self.triage.triage(raw_data)
            
            # 3. Summary (ClinicalSummaryAgent)
            self.obs.add_trace("SummaryAgent", "Synthesizing SOAP note")
            clinician_summary = self.summary.create_summary(raw_data, triage_results)
            
            # 4. Persistence (WorkflowAutomationAgent)
            workflow_outcome = "Logged"
            if consent:
                self.obs.add_trace("WorkflowAgent", "Persisting to EHR")
                prepared_case = self.workflow.prepare_case(raw_data, triage_results, clinician_summary)
                save_result = self.workflow.confirm_and_save(prepared_case, consent=True)
                workflow_outcome = save_result.get("status", "Saved")

            latency = self.obs.stop_timer(start_timer)
            self.obs.info("Inference complete", extra={"latency": latency, "patient": patient_id})

            return {
                "triage": triage_results,
                "clinical_summary": clinician_summary,
                "follow_up": {
                    "safety_net_advice": triage_results.get('action', 'Seek medical review if symptoms persist.')
                },
                "workflow_status": workflow_outcome,
                "metadata": {
                    "latency": f"{latency}s",
                    "trace_id": trace_id,
                    "patient_id": patient_id,
                    "model": self.model_name
                }
            }
        except Exception as e:
            if self.obs:
                self.obs.error(f"Pipeline Error: {str(e)}")
            return {"status": "error", "message": f"Cloud Pipeline Error: {str(e)}"}

# --- DEPLOYMENT SCRIPT ---
if __name__ == "__main__":
    # Pull values from environment (set by deploy.yml)
    PROJECT_ID = os.getenv("GCP_PROJECT_ID")
    LOCATION = os.getenv("GCP_LOCATION", "us-central1")
    STAGING_BUCKET = os.getenv("GCS_MEMORY_BUCKET")

    if not PROJECT_ID or not STAGING_BUCKET:
        print("❌ Error: Missing GCP_PROJECT_ID or GCS_MEMORY_BUCKET in environment.")
        exit(1)

    # Initialize Vertex AI for the deployment process
    vertexai.init(project=PROJECT_ID, location=LOCATION, staging_bucket=f"gs://{STAGING_BUCKET}")

    # Initialize the engine instance with project context
    engine_instance = MedFlowReasoningEngine()
    engine_instance.project = PROJECT_ID
    engine_instance.bucket_name = STAGING_BUCKET

    print(f"🚀 Deploying MedFlow v21 to {PROJECT_ID}...")

    try:
        remote_app = reasoning_engines.ReasoningEngine.create(
            engine_instance,
            requirements=[
                "google-genai",
                "google-cloud-aiplatform[reasoningengine,preview]",
                "google-cloud-bigquery",
                "google-cloud-storage",
                "google-cloud-logging",
                "python-dotenv",
                "pydantic"
            ],
            display_name="MedFlow_Clinical_Engine_v21",
            extra_packages=["agents", "tools", "memory", "observability"],
        )
        print(f"✅ Deployed Successfully!")
        print(f"Resource Name: {remote_app.resource_name}")
    except Exception as e:
        print(f"❌ Deployment Failed: {str(e)}")