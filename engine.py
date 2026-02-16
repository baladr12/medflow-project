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
    Features: 7-Agent Orchestration, Observability, and Sticky Triage Memory.
    """

    def __init__(self):
        # Configuration pulled from deployment or env
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
        """Initializes agents and tools in the cloud environment."""
        if self.client is not None:
            return

        # Ensure project variables are set for Google Cloud Clients
        if self.project:
            os.environ["GCP_PROJECT_ID"] = self.project
            os.environ["GOOGLE_CLOUD_PROJECT"] = self.project

        from google import genai
        from google.auth import default
        
        from agents.patient_understanding import PatientUnderstandingAgent
        from agents.clinical_triage import ClinicalTriageAgent
        from agents.clinical_summary import ClinicalSummaryAgent
        from agents.workflow_automation import WorkflowAutomationAgent
        from memory.memory_agent import MemoryAgent
        from tools.ehr_store import EHRStore
        from memory.memory_store import MemoryStore
        from observability.manager import ObservabilityManager

        credentials, _ = default()
        self.obs = ObservabilityManager(name="medflow-engine")
        self.client = genai.Client(
            vertexai=True,
            project=self.project,
            location=self.location,
            credentials=credentials
        )

        # 1. Initialize Stores
        self.ehr = EHRStore()         
        self.mem_store = MemoryStore()
        
        # --- THE MEMORY FIX ---
        # Force the bucket name into the MemoryStore so it points to the correct GCS location
        if self.bucket_name:
            self.mem_store.bucket_name = self.bucket_name
            print(f"DEBUG: MemoryStore linked to bucket: {self.bucket_name}")
        # ----------------------

        # 2. Initialize Agents
        self.intake = PatientUnderstandingAgent(self.client)
        self.triage = ClinicalTriageAgent(self.client)
        self.summary = ClinicalSummaryAgent(self.client)
        self.workflow = WorkflowAutomationAgent(self.ehr)
        self.memory = MemoryAgent(self.client, self.mem_store)
        
        self._initialize_infrastructure()

    def _initialize_infrastructure(self):
        """Ensures BigQuery resources exist."""
        from google.cloud import bigquery
        from google.api_core import exceptions

        project_id = self.project or os.getenv("GCP_PROJECT_ID")
        if not project_id: return

        bq_client = bigquery.Client(project=project_id)
        full_dataset_id = f"{project_id}.{self.dataset_id}"
        
        try:
            bq_client.get_dataset(full_dataset_id)
        except exceptions.NotFound:
            dataset = bigquery.Dataset(full_dataset_id)
            dataset.location = self.location
            bq_client.create_dataset(dataset, timeout=30)
        except Exception as e:
            print(f"⚠️ Infra Warning: {e}")

    def query(self, message: str, consent: bool = False, patient_id: str = "anonymous"):
        """Main cloud execution with State-Aware Triage."""
        self._setup()
        
        trace_id = self.obs.start_request()
        start_timer = self.obs.start_timer()

        try:
            # 1. LOAD PATIENT HISTORY
            self.mem_store.blob_name = f"{patient_id}.json"
            history = self.mem_store.load() 

            # Standardize priority for the logic latch
            prev_priority = str(history.get("last_triage_level", "routine")).lower().strip()
            
            print(f"DEBUG: Memory for {patient_id} loaded. Value: {prev_priority}")
            self.obs.add_trace("MemoryStore", f"Patient: {patient_id} | Memory Load: {prev_priority}")

            # 2. EXTRACTION
            self.obs.add_trace("IntakeAgent", "Analyzing clinical input")
            extracted_data = self.intake.analyse(message)
            
            # --- THE AGGRESSIVE INJECTION ---
            triage_payload = {**extracted_data} 
            triage_payload["previous_priority"] = prev_priority
            
            # 3. TRIAGE (Sticky Priority Check inside this agent)
            self.obs.add_trace("TriageAgent", f"Calculating priority (Context: {prev_priority})")
            triage_results = self.triage.triage(triage_payload)
            new_level = triage_results.get("level", "routine")
            
            # 4. SUMMARY
            self.obs.add_trace("SummaryAgent", "Synthesizing clinical note")
            clinician_summary = self.summary.create_summary(triage_payload, triage_results)
            
            # 5. PERSISTENCE & MEMORY UPDATE
            history["last_triage_level"] = new_level
            print(f"DEBUG: Attempting to save '{new_level}' to {self.mem_store.blob_name}")
            self.mem_store.save(history) 

            # VERIFICATION LOG (Crucial for debugging the 'None' issue)
            verify_history = self.mem_store.load()
            print(f"DEBUG: Verification load result: {verify_history.get('last_triage_level')}")

            workflow_outcome = "Logged"
            if consent:
                self.obs.add_trace("WorkflowAgent", "Persisting to EHR")
                prepared_case = self.workflow.prepare_case(triage_payload, triage_results, clinician_summary)
                save_result = self.workflow.confirm_and_save(prepared_case, consent=True)
                workflow_outcome = save_result.get("status", "Saved")

            latency = self.obs.stop_timer(start_timer)
            
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
            if self.obs: self.obs.error(f"Pipeline Error: {str(e)}")
            return {"status": "error", "message": f"Cloud Pipeline Error: {str(e)}"}

# --- DEPLOYMENT SCRIPT ---
if __name__ == "__main__":
    PROJECT_ID = os.getenv("GCP_PROJECT_ID")
    LOCATION = os.getenv("GCP_LOCATION", "us-central1")
    STAGING_BUCKET = os.getenv("GCS_MEMORY_BUCKET")
    # NEW: Pull the service account from env
    SERVICE_ACCOUNT = os.getenv("GCP_SERVICE_ACCOUNT")

    if not all([PROJECT_ID, STAGING_BUCKET, SERVICE_ACCOUNT]):
        print("❌ Error: Missing configuration in .env (Project, Bucket, or Service Account)")
        exit(1)

    vertexai.init(project=PROJECT_ID, location=LOCATION, staging_bucket=f"gs://{STAGING_BUCKET}")

    engine_instance = MedFlowReasoningEngine()
    engine_instance.project = PROJECT_ID
    engine_instance.bucket_name = STAGING_BUCKET

    print(f"🚀 Deploying MedFlow v21 Final Latch to {PROJECT_ID}...")
    print(f"🚀 Deploying with Service Account: {SERVICE_ACCOUNT}")

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
            display_name="MedFlow_DYNAMIC_SA_DEPLOY",
            extra_packages=["agents", "tools", "memory", "observability"],
            # DYNAMIC INJECTION
            service_account=SERVICE_ACCOUNT
        )
        print(f"✅ Deployed Successfully: {remote_app.resource_name}")
    except Exception as e:
        print(f"❌ Deployment Failed: {str(e)}")