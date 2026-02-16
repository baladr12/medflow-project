import os
import vertexai
from vertexai.preview import reasoning_engines
from datetime import datetime, timezone
from dotenv import load_dotenv

# Ensure environment is loaded before anything else
load_dotenv()

class MedFlowReasoningEngine:
    """
    MedFlow v21: Enterprise Clinical Reasoning Engine.
    Features: 7-Agent Orchestration, Observability, and Sticky Triage Memory.
    """

    def __init__(self):
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
        """Initializes agents and tools with forced cloud context."""
        if self.client is not None:
            return

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

        # 1. Initialize Stores & Link Bucket
        self.ehr = EHRStore()         
        self.mem_store = MemoryStore()
        if self.bucket_name:
            self.mem_store.bucket_name = self.bucket_name
        
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
        except Exception: pass

    def query(self, message: str, consent: bool = False, patient_id: str = "anonymous"):
        """Main cloud execution with State-Aware Triage and GCS Debugging."""
        self._setup()
        trace_id = self.obs.start_request()
        start_timer = self.obs.start_timer()

        print(f"DEBUG [START]: Query for patient {patient_id}")
        print(f"DEBUG [CONFIG]: Target Bucket: {self.bucket_name}")

        try:
            # 1. LOAD PATIENT HISTORY
            self.mem_store.blob_name = f"sessions/{patient_id}.json" # Added 'sessions/' prefix
            
            try:
                history = self.mem_store.load() 
                print(f"DEBUG [MEMORY]: Load successful for {patient_id}")
            except Exception as load_err:
                print(f"DEBUG [MEMORY]: No existing session found or error: {str(load_err)}")
                history = {}

            # Get previous priority
            prev_priority = str(history.get("last_triage_level", "routine")).lower().strip()
            print(f"DEBUG [STATE]: Previous priority was: {prev_priority}")
            
            self.obs.add_trace("MemoryStore", f"Load: {prev_priority} for {patient_id}")

            # 2. EXTRACTION
            extracted_data = self.intake.analyse(message)
            
            # 3. TRIAGE
            triage_payload = {**extracted_data} 
            triage_payload["previous_priority"] = prev_priority
            
            triage_results = self.triage.triage(triage_payload)
            new_level = triage_results.get("level", "routine")
            print(f"DEBUG [STATE]: New triage level calculated: {new_level}")
            
            # 4. SUMMARY
            clinician_summary = self.summary.create_summary(triage_payload, triage_results)
            
            # 5. PERSISTENCE (Update and Save)
            history["last_triage_level"] = new_level
            
            try:
                self.mem_store.save(history) 
                print(f"DEBUG [SAVE]: Successfully saved {new_level} to gs://{self.bucket_name}/sessions/{patient_id}.json")
            except Exception as save_err:
                print(f"❌ DEBUG [SAVE ERROR]: FAILED to write to GCS: {str(save_err)}")

            # 6. WORKFLOW
            workflow_outcome = "Logged"
            if consent:
                prepared_case = self.workflow.prepare_case(triage_payload, triage_results, clinician_summary)
                save_result = self.workflow.confirm_and_save(prepared_case, consent=True)
                workflow_outcome = save_result.get("status", "Saved")

            latency = self.obs.stop_timer(start_timer)
            
            return {
                "triage": triage_results,
                "clinical_summary": clinician_summary,
                "follow_up": {
                    "safety_net_advice": triage_results.get('action', 'Seek medical review.')
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
            print(f"❌ CRITICAL: Pipeline Crashed: {str(e)}")
            if self.obs: self.obs.error(f"Pipeline Error: {str(e)}")
            return {"status": "error", "message": str(e)}

# --- DEPLOYMENT SCRIPT ---
if __name__ == "__main__":
    PROJECT_ID = os.getenv("GCP_PROJECT_ID")
    LOCATION = os.getenv("GCP_LOCATION", "us-central1")
    STAGING_BUCKET = os.getenv("GCS_MEMORY_BUCKET")
    SERVICE_ACCOUNT = os.getenv("GCP_SERVICE_ACCOUNT")

    # Final validation check
    required = {"Project": PROJECT_ID, "Bucket": STAGING_BUCKET, "Service Account": SERVICE_ACCOUNT}
    for label, val in required.items():
        if not val:
            print(f"❌ Error: {label} is missing from .env")
            exit(1)

    vertexai.init(project=PROJECT_ID, location=LOCATION, staging_bucket=f"gs://{STAGING_BUCKET}")

    engine_instance = MedFlowReasoningEngine()
    engine_instance.project = PROJECT_ID
    engine_instance.bucket_name = STAGING_BUCKET

    print(f"🚀 Deploying v21 LATCH_FIX to {PROJECT_ID}...")
    
    # Define common requirements once
    REQS = [
        "google-genai>=0.8.0",
        "google-cloud-aiplatform[reasoningengine,preview]",
        "google-cloud-logging",
        "google-cloud-bigquery",
        "google-cloud-storage",
        "google-auth",
        "pydantic",
        "python-dotenv",
        "cloudpickle",
        "requests"
    ]

    try:
        remote_app = reasoning_engines.ReasoningEngine.create(
            engine_instance,
            requirements=REQS,
            display_name="MedFlow_LATCH_FORCE_NEW_FINAL", # Changed name to bypass cache
            extra_packages=["agents", "tools", "memory", "observability"],
            service_account=SERVICE_ACCOUNT
        )
        print(f"✅ Deployed Successfully: {remote_app.resource_name}")
    except TypeError as e:
        if "unexpected keyword argument 'service_account'" in str(e):
            print("⚠️ Direct 'service_account' failed, attempting with no identity (uses runner default)...")
            # FALLBACK: If the SDK is in a strict environment, let it inherit the 
            # identity from the GitHub Action's authenticated session.
            remote_app = reasoning_engines.ReasoningEngine.create(
                engine_instance,
                requirements=REQS,
                display_name="MedFlow_LATCH_FORCE_FINAL_AUTO_V1",
                extra_packages=["agents", "tools", "memory", "observability"]
            )
            print(f"✅ Deployed Successfully (Auto-Identity): {remote_app.resource_name}")
        else:
            raise e