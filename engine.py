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
    Orchestrates 7 specialized agents with automated infrastructure setup.
    """

    def __init__(self):
        # Configuration - strictly strings only in __init__ to avoid pickle/serialization errors
        self.project = os.getenv("GCP_PROJECT_ID")
        self.location = os.getenv("GCP_LOCATION", "us-central1")
        self.model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        
        # Placeholders for objects that cannot be "pickled"
        self.client = None
        self.intake = None
        self.triage = None
        self.summary = None
        self.workflow = None
        self.memory = None
        self.followup = None
        self.evaluator = None

    def _setup(self):
        """Build clients and agents ONLY when the engine is running in the cloud."""
        if self.client is not None:
            return

        from google import genai
        from google.auth import default
        
        # Imports inside the method to keep the class definition lightweight
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

        # 2. Initialize Infrastructure Tools
        self.ehr = EHRStore()         
        self.mem_store = MemoryStore()

        # 3. Initialize the 7-Agent Team
        self.intake = PatientUnderstandingAgent(self.client)
        self.triage = ClinicalTriageAgent(self.client)
        self.summary = ClinicalSummaryAgent(self.client)
        self.workflow = WorkflowAutomationAgent(self.ehr)
        self.memory = MemoryAgent(self.client, self.mem_store)
        self.followup = FollowUpAgent(self.client)
        self.evaluator = EvaluationAgent(self.client)
        
        # 4. Run infrastructure check
        self._initialize_infrastructure()

    def _initialize_infrastructure(self):
        """Idempotent setup for GCS and BigQuery Schema."""
        from google.cloud import storage, bigquery

        storage_client = storage.Client()
        bucket_name = os.getenv("GCS_MEMORY_BUCKET")
        if bucket_name:
            bucket = storage_client.bucket(bucket_name)
            if not bucket.exists():
                storage_client.create_bucket(bucket, location=self.location)

        bq_client = bigquery.Client()
        dataset_id = os.getenv('BQ_DATASET_ID', 'clinical_records')
        table_id = os.getenv('BQ_TABLE_ID', 'triage_cases')
        dataset_ref = bq_client.dataset(dataset_id)
        
        try:
            bq_client.get_dataset(dataset_ref)
        except Exception:
            dataset = bigquery.Dataset(dataset_ref)
            dataset.location = self.location
            bq_client.create_dataset(dataset, timeout=30)

        table_ref = dataset_ref.table(table_id)
        try:
            bq_client.get_table(table_ref)
        except Exception:
            schema = [
                bigquery.SchemaField("case_id", "STRING", mode="REQUIRED"),
                bigquery.SchemaField("timestamp", "TIMESTAMP", mode="REQUIRED"),
                bigquery.SchemaField("patient_summary", "STRING"),
                bigquery.SchemaField("triage_level", "STRING"),
                bigquery.SchemaField("soap_note", "STRING"),
                bigquery.SchemaField("integrity_hash", "STRING"),
            ]
            table = bigquery.Table(table_ref, schema=schema)
            bq_client.create_table(table)

    def query(self, message: str, consent: bool = False):
        """Main execution pipeline."""
        # Ensure agents are ready before processing
        self._setup()
        
        start_time = datetime.now(timezone.utc)

        try:
            raw_data = self.intake.analyse(message)
            triage_results = self.triage.triage(raw_data)
            clinician_summary = self.summary.create_summary(raw_data, triage_results)
            evaluation = self.evaluator.evaluate(raw_data, triage_results, clinician_summary)
            
            if not evaluation.get("safety_pass", True):
                return {
                    "status": "safety_intervention",
                    "message": "Clinical safety audit failed."
                }

            followup_info = self.followup.generate_followup(raw_data, triage_results, clinician_summary)
            self.memory.add_to_session(message)
            self.memory.summarise_session()

            prepared_case = self.workflow.prepare_case(raw_data, triage_results, clinician_summary)
            
            workflow_outcome = "Pending"
            if consent:
                save_result = self.workflow.confirm_and_save(prepared_case, consent=True)
                workflow_outcome = save_result.get("status", "Saved")

            duration = (datetime.now(timezone.utc) - start_time).total_seconds()

            return {
                "triage": triage_results,
                "clinical_summary": clinician_summary,
                "follow_up": followup_info,
                "workflow_status": workflow_outcome,
                "metadata": {
                    "latency": f"{round(duration, 2)}s",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            }

        except Exception as e:
            return {"status": "error", "message": str(e)}

# --- DEPLOYMENT SCRIPT ---
if __name__ == "__main__":
    PROJECT_ID = os.getenv("GCP_PROJECT_ID")
    LOCATION = os.getenv("GCP_LOCATION", "us-central1")
    STAGING_BUCKET = os.getenv("GCS_MEMORY_BUCKET")

    if not PROJECT_ID or not STAGING_BUCKET:
        print("❌ Error: Missing Env Vars (GCP_PROJECT_ID or GCS_MEMORY_BUCKET)")
        exit(1)

    vertexai.init(
        project=PROJECT_ID, 
        location=LOCATION, 
        staging_bucket=f"gs://{STAGING_BUCKET}"
    )

    print(f"🚀 Deploying MedFlow Engine to {PROJECT_ID}...")

    try:
        remote_app = reasoning_engines.ReasoningEngine.create(
            MedFlowReasoningEngine(),
            requirements=[
                "google-genai",
                "google-cloud-aiplatform[reasoningengine,preview]",
                "google-cloud-bigquery",
                "google-cloud-storage",
                "python-dotenv",
            ],
            display_name="MedFlow_ADK_Clinical_Engine_v21",
            extra_packages=["agents", "tools", "memory"],
            # --- THIS BLOCK FIXES THE FAILED PRECONDITION ERROR ---
            env_vars={
                "GCP_PROJECT_ID": PROJECT_ID,
                "GCP_LOCATION": LOCATION,
                "GCS_MEMORY_BUCKET": STAGING_BUCKET,
                "GEMINI_MODEL": os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
                "BQ_DATASET_ID": os.getenv("BQ_DATASET_ID", "clinical_records"),
                "BQ_TABLE_ID": os.getenv("BQ_TABLE_ID", "triage_cases"),
            }
            # ------------------------------------------------------
        )

        print(f"\n✅ Deployment Complete!")
        print(f"Engine Resource ID: {remote_app.resource_name}")

    except Exception as e:
        print(f"\n❌ Deployment Failed: {str(e)}")