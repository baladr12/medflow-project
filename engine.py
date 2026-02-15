import os
import vertexai
from vertexai.preview import reasoning_engines
from datetime import datetime, timezone
from dotenv import load_dotenv

# Load local environment for development
load_dotenv()

class MedFlowReasoningEngine:
    def __init__(self):
        # We define these; they will be filled by the injection script below
        self.project = None
        self.location = "us-central1"
        self.model_name = "gemini-2.0-flash"
        self.bucket_name = None
        self.dataset_id = "clinical_records"
        self.table_id = "triage_cases"
        
        # Placeholders
        self.client = None
        self.intake = None
        self.triage = None
        self.summary = None
        self.workflow = None
        self.memory = None
        self.followup = None
        self.evaluator = None

    def _setup(self):
        """Build clients using internal attributes, NOT os.getenv."""
        if self.client is not None:
            return

        from google import genai
        from google.auth import default
        
        # Local Agent Imports
        from agents.patient_understanding import PatientUnderstandingAgent
        from agents.clinical_triage import ClinicalTriageAgent
        from agents.clinical_summary import ClinicalSummaryAgent
        from agents.workflow_automation import WorkflowAutomationAgent
        from agents.followup_agent import FollowUpAgent
        from agents.evaluation_agent import EvaluationAgent
        from memory.memory_agent import MemoryAgent
        from tools.ehr_store import EHRStore
        from memory.memory_store import MemoryStore

        # Validate that injection worked
        if not self.project:
            raise ValueError("Instance error: self.project is not set. Deployment injection failed.")

        # 1. Initialize GenAI Client using THE INSTANCE ATTRIBUTE
        credentials, _ = default()
        self.client = genai.Client(
            vertexai=True,
            project=self.project,
            location=self.location,
            credentials=credentials
        )

        # 2. Initialize Infrastructure
        self.ehr = EHRStore()         
        self.mem_store = MemoryStore()

        # 3. Initialize Agents
        self.intake = PatientUnderstandingAgent(self.client)
        self.triage = ClinicalTriageAgent(self.client)
        self.summary = ClinicalSummaryAgent(self.client)
        self.workflow = WorkflowAutomationAgent(self.ehr)
        self.memory = MemoryAgent(self.client, self.mem_store)
        self.followup = FollowUpAgent(self.client)
        self.evaluator = EvaluationAgent(self.client)
        
        self._initialize_infrastructure()

    def _initialize_infrastructure(self):
        from google.cloud import storage, bigquery

        # Use self.project directly
        storage_client = storage.Client(project=self.project)
        if self.bucket_name:
            bucket = storage_client.bucket(self.bucket_name)
            if not bucket.exists():
                storage_client.create_bucket(bucket, location=self.location)

        bq_client = bigquery.Client(project=self.project)
        dataset_ref = bq_client.dataset(self.dataset_id)
        
        try:
            bq_client.get_dataset(dataset_ref)
        except Exception:
            dataset = bigquery.Dataset(dataset_ref)
            dataset.location = self.location
            bq_client.create_dataset(dataset)

        table_ref = dataset_ref.table(self.table_id)
        try:
            bq_client.get_table(table_ref)
        except Exception:
            schema = [
                bigquery.SchemaField("case_id", "STRING", mode="REQUIRED"),
                bigquery.SchemaField("timestamp", "TIMESTAMP", mode="REQUIRED"),
                bigquery.SchemaField("patient_summary", "STRING"),
                bigquery.SchemaField("triage_level", "STRING"),
            ]
            table = bigquery.Table(table_ref, schema=schema)
            bq_client.create_table(table)

    def query(self, message: str, consent: bool = False):
        self._setup()
        start_time = datetime.now(timezone.utc)
        try:
            raw_data = self.intake.analyse(message)
            triage_results = self.triage.triage(raw_data)
            clinician_summary = self.summary.create_summary(raw_data, triage_results)
            
            # Simple metadata for UI
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()

            return {
                "triage": triage_results,
                "clinical_summary": clinician_summary,
                "follow_up": {"safety_net_advice": "Consult a doctor immediately if symptoms worsen."},
                "workflow_status": "Logged to EHR" if consent else "Pending",
                "metadata": {"latency": f"{round(duration, 2)}s"}
            }
        except Exception as e:
            return {"status": "error", "message": f"Execution failed: {str(e)}"}

# --- DEPLOYMENT SCRIPT ---
if __name__ == "__main__":
    PROJ = os.getenv("GCP_PROJECT_ID")
    LOC = os.getenv("GCP_LOCATION", "us-central1")
    BUCKET = os.getenv("GCS_MEMORY_BUCKET")

    vertexai.init(project=PROJ, location=LOC, staging_bucket=f"gs://{BUCKET}")

    # Create instance
    engine = MedFlowReasoningEngine()

    # PHYSICAL INJECTION: Force these values into the object state
    engine.project = PROJ
    engine.location = LOC
    engine.bucket_name = BUCKET
    engine.dataset_id = os.getenv("BQ_DATASET_ID", "clinical_records")
    engine.table_id = os.getenv("BQ_TABLE_ID", "triage_cases")

    print("🚀 Deploying Engine with state-bundled configuration...")

    try:
        remote_app = reasoning_engines.ReasoningEngine.create(
            engine,
            requirements=[
                "google-genai",
                "google-cloud-aiplatform[reasoningengine,preview]",
                "google-cloud-bigquery",
                "google-cloud-storage",
                "python-dotenv",
            ],
            display_name="MedFlow_ADK_Clinical_Engine_v21",
            extra_packages=["agents", "tools", "memory"],
        )
        print(f"✅ Success! New ID: {remote_app.resource_name}")
    except Exception as e:
        print(f"❌ Failed: {str(e)}")