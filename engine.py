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
    Features: 
    - Environment Hot-Patching for Google GenAI SDK
    - Idempotent Infrastructure (Auto-handles existing BQ/GCS)
    - Dynamic Model Loading via .env
    """

    def __init__(self):
        # Placeholders injected during deployment
        self.project = None
        self.location = "us-central1"
        self.model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        self.bucket_name = None
        self.dataset_id = "clinical_records"
        self.table_id = "triage_cases"
        
        # Object placeholders
        self.client = None
        self.intake = None
        self.triage = None
        self.summary = None
        self.workflow = None
        self.memory = None
        self.followup = None
        self.evaluator = None

    def _setup(self):
        """Forces injected variables into cloud environment before SDK initialization."""
        if self.client is not None:
            return

        import os
        # CRITICAL: Force environment variables for the Google GenAI SDK
        if self.project:
            os.environ["GCP_PROJECT_ID"] = self.project
            os.environ["GOOGLE_CLOUD_PROJECT"] = self.project
        if self.location:
            os.environ["GCP_LOCATION"] = self.location

        from google import genai
        from google.auth import default
        
        # Lazy-import agents for lightweight pickling
        from agents.patient_understanding import PatientUnderstandingAgent
        from agents.clinical_triage import ClinicalTriageAgent
        from agents.clinical_summary import ClinicalSummaryAgent
        from agents.workflow_automation import WorkflowAutomationAgent
        from agents.followup_agent import FollowUpAgent
        from agents.evaluation_agent import EvaluationAgent
        from memory.memory_agent import MemoryAgent
        from tools.ehr_store import EHRStore
        from memory.memory_store import MemoryStore

        # 1. Initialize Google GenAI Client
        credentials, _ = default()
        self.client = genai.Client(
            vertexai=True,
            project=self.project,
            location=self.location,
            credentials=credentials
        )

        # 2. Initialize Tools & Memory
        self.ehr = EHRStore()         
        self.mem_store = MemoryStore()

        # 3. Initialize the 7-Agent Team
        # We pass self.model_name to agents if they need to know the specific model
        self.intake = PatientUnderstandingAgent(self.client)
        self.triage = ClinicalTriageAgent(self.client)
        self.summary = ClinicalSummaryAgent(self.client)
        self.workflow = WorkflowAutomationAgent(self.ehr)
        self.memory = MemoryAgent(self.client, self.mem_store)
        self.followup = FollowUpAgent(self.client)
        self.evaluator = EvaluationAgent(self.client)
        
        # 4. Sync Cloud Infrastructure
        self._initialize_infrastructure()

    def _initialize_infrastructure(self):
        """Sets up GCS and BigQuery. Skips if already exists to prevent 409/403 errors."""
        from google.cloud import storage, bigquery
        from google.api_core import exceptions

        if not self.project:
            return

        # 1. Storage Check
        storage_client = storage.Client(project=self.project)
        if self.bucket_name:
            bucket = storage_client.bucket(self.bucket_name)
            try:
                if not bucket.exists():
                    storage_client.create_bucket(bucket, location=self.location)
            except Exception:
                pass 

        # 2. BigQuery Dataset Check (Explicit Full Path)
        bq_client = bigquery.Client(project=self.project)
        full_dataset_id = f"{self.project}.{self.dataset_id}"
        
        try:
            bq_client.get_dataset(full_dataset_id)
        except exceptions.NotFound:
            dataset = bigquery.Dataset(full_dataset_id)
            dataset.location = self.location
            bq_client.create_dataset(dataset, timeout=30)
        except exceptions.Forbidden:
            # Proceed if we have write-only access or it already exists
            pass

        # 3. BigQuery Table Check
        full_table_id = f"{full_dataset_id}.{self.table_id}"
        try:
            bq_client.get_table(full_table_id)
        except exceptions.NotFound:
            schema = [
                bigquery.SchemaField("case_id", "STRING", mode="REQUIRED"),
                bigquery.SchemaField("timestamp", "TIMESTAMP", mode="REQUIRED"),
                bigquery.SchemaField("patient_summary", "STRING"),
                bigquery.SchemaField("triage_level", "STRING"),
            ]
            table = bigquery.Table(full_table_id, schema=schema)
            bq_client.create_table(table)
        except exceptions.Forbidden:
            pass

    def query(self, message: str, consent: bool = False):
        """Main cloud execution point."""
        self._setup()
        start_time = datetime.now(timezone.utc)

        try:
            # Execute Agentic Pipeline
            raw_data = self.intake.analyse(message)
            triage_results = self.triage.triage(raw_data)
            clinician_summary = self.summary.create_summary(raw_data, triage_results)
            
            # Workflow: Log to BigQuery/EHR
            workflow_outcome = "Logged"
            if consent:
                try:
                    prepared_case = self.workflow.prepare_case(raw_data, triage_results, clinician_summary)
                    save_result = self.workflow.confirm_and_save(prepared_case, consent=True)
                    workflow_outcome = save_result.get("status", "Saved to EHR")
                except Exception as e:
                    workflow_outcome = f"EHR Log Partial: {str(e)}"

            duration = (datetime.now(timezone.utc) - start_time).total_seconds()

            return {
                "triage": triage_results,
                "clinical_summary": clinician_summary,
                "follow_up": {"safety_net_advice": "Seek immediate care if symptoms worsen or breathing becomes difficult."},
                "workflow_status": workflow_outcome,
                "metadata": {
                    "latency": f"{round(duration, 2)}s",
                    "engine": "MedFlow-ADK-v21-Production",
                    "model": self.model_name
                }
            }
        except Exception as e:
            return {"status": "error", "message": f"Cloud Pipeline Error: {str(e)}"}

# --- DEPLOYMENT SCRIPT ---
if __name__ == "__main__":
    # 1. Fetch environment variables
    PROJECT_ID = os.getenv("GCP_PROJECT_ID")
    LOCATION = os.getenv("GCP_LOCATION", "us-central1")
    STAGING_BUCKET = os.getenv("GCS_MEMORY_BUCKET")
    MODEL_ID = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    if not PROJECT_ID or not STAGING_BUCKET:
        print("❌ Error: Missing GCP_PROJECT_ID or GCS_MEMORY_BUCKET in .env")
        exit(1)

    # Initialize Vertex AI for deployment
    vertexai.init(project=PROJECT_ID, location=LOCATION, staging_bucket=f"gs://{STAGING_BUCKET}")

    # 2. Create and configure instance
    engine_instance = MedFlowReasoningEngine()
    
    # "Bake" values into the serialized object for cloud persistence
    engine_instance.project = PROJECT_ID
    engine_instance.location = LOCATION
    engine_instance.model_name = MODEL_ID
    engine_instance.bucket_name = STAGING_BUCKET
    engine_instance.dataset_id = os.getenv("BQ_DATASET_ID", "clinical_records")
    engine_instance.table_id = os.getenv("BQ_TABLE_ID", "triage_cases")

    print(f"🚀 Deploying to {PROJECT_ID}...")
    print(f"🧠 Model: {MODEL_ID}")

    try:
        remote_app = reasoning_engines.ReasoningEngine.create(
            engine_instance,
            requirements=[
                "google-genai",
                "google-cloud-aiplatform[reasoningengine,preview]",
                "google-cloud-bigquery",
                "google-cloud-storage",
                "python-dotenv",
            ],
            display_name="MedFlow_Clinical_Engine_v21",
            extra_packages=["agents", "tools", "memory"],
        )

        print(f"\n✅ Success! Engine Deployed.")
        print(f"Resource ID: {remote_app.resource_name}")
        print(f"Update your UI to use Auto-Discovery or this ID.")

    except Exception as e:
        print(f"\n❌ Deployment Failed: {str(e)}")