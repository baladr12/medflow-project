import os
import vertexai
from vertexai.preview import reasoning_engines
from google import genai
from google.auth import default
from datetime import datetime, timezone
from dotenv import load_dotenv

# 1. Unified Imports from specialized folders
from agents.patient_understanding import PatientUnderstandingAgent
from agents.clinical_triage import ClinicalTriageAgent
from agents.clinical_summary import ClinicalSummaryAgent
from agents.workflow_automation import WorkflowAutomationAgent
from agents.followup_agent import FollowUpAgent
from agents.evaluation_agent import EvaluationAgent
from memory.memory_agent import MemoryAgent
from tools.ehr_store import EHRStore
from memory.memory_store import MemoryStore

# Load local environment for development
load_dotenv()

class MedFlowReasoningEngine:
    """
    MedFlow v21: Enterprise Clinical Reasoning Engine.
    Orchestrates 7 specialized agents with automated infrastructure setup.
    """

    def __init__(self):
        # Configuration - strictly pulled from Env Vars
        self.project = os.getenv("GCP_PROJECT_ID")
        self.location = os.getenv("GCP_LOCATION", "us-central1")
        self.model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

        if not self.project:
            raise ValueError("GCP_PROJECT_ID must be set in Environment Variables.")

        # --- PHASE 0: Infrastructure Auto-Provisioning ---
        self._initialize_infrastructure()

        # Initialize Google GenAI Client
        credentials, _ = default()
        self.client = genai.Client(
            vertexai=True,
            project=self.project,
            location=self.location,
            credentials=credentials
        )

        # Initialize Infrastructure Tools
        self.ehr = EHRStore()         
        self.mem_store = MemoryStore()

        # Initialize the 7-Agent Team
        self.intake = PatientUnderstandingAgent(self.client)
        self.triage = ClinicalTriageAgent(self.client)
        self.summary = ClinicalSummaryAgent(self.client)
        self.workflow = WorkflowAutomationAgent(self.ehr)
        self.memory = MemoryAgent(self.client, self.mem_store)
        self.followup = FollowUpAgent(self.client)
        self.evaluator = EvaluationAgent(self.client)

    def _initialize_infrastructure(self):
        """Idempotent setup for GCS and BigQuery Schema."""
        from google.cloud import storage, bigquery

        # 1. Ensure GCS Bucket exists for Memory
        storage_client = storage.Client()
        bucket_name = os.getenv("GCS_MEMORY_BUCKET")
        if bucket_name:
            bucket = storage_client.bucket(bucket_name)
            if not bucket.exists():
                print(f"🛠️ Provisioning Storage: {bucket_name}")
                storage_client.create_bucket(bucket, location=self.location)

        # 2. Ensure BigQuery Dataset & Table exist for EHR
        bq_client = bigquery.Client()
        dataset_id = os.getenv('BQ_DATASET_ID', 'clinical_records')
        table_id = os.getenv('BQ_TABLE_ID', 'triage_cases')
        dataset_ref = bq_client.dataset(dataset_id)
        
        # Check/Create Dataset
        try:
            bq_client.get_dataset(dataset_ref)
        except Exception:
            print(f"🛠️ Provisioning Dataset: {dataset_id}")
            dataset = bigquery.Dataset(dataset_ref)
            dataset.location = self.location
            bq_client.create_dataset(dataset, timeout=30)

        # Check/Create Table with Schema
        table_ref = dataset_ref.table(table_id)
        try:
            bq_client.get_table(table_ref)
        except Exception:
            print(f"🛠️ Provisioning Table Schema: {table_id}")
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
        """Main execution pipeline: Intake -> Triage -> Summary -> Audit -> Save."""
        start_time = datetime.now(timezone.utc)

        try:
            # Agent 1: Extraction
            raw_data = self.intake.analyse(message)
            
            # Agent 2: Triage
            triage_results = self.triage.triage(raw_data)
            
            # Agent 3: Summary
            clinician_summary = self.summary.create_summary(raw_data, triage_results)

            # Agent 7: Safety Audit
            evaluation = self.evaluator.evaluate(raw_data, triage_results, clinician_summary)
            
            if not evaluation.get("safety_pass", True):
                return {
                    "status": "safety_intervention",
                    "triage": triage_results,
                    "safety_report": evaluation,
                    "message": "Clinical safety audit failed. Case flagged for human review."
                }

            # Agent 6: Follow-ups
            followup_info = self.followup.generate_followup(raw_data, triage_results, clinician_summary)
            
            # Agent 5: Memory
            self.memory.add_to_session(message)
            self.memory.summarise_session()

            # Agent 4: Workflow/Persistence
            prepared_case = self.workflow.prepare_case(raw_data, triage_results, clinician_summary)
            
            workflow_outcome = "Pending Consent"
            if consent:
                save_result = self.workflow.confirm_and_save(prepared_case, consent=True)
                workflow_outcome = save_result.get("status", "Saved")

            duration = (datetime.now(timezone.utc) - start_time).total_seconds()

            return {
                "triage": triage_results,
                "clinical_summary": clinician_summary,
                "follow_up": followup_info,
                "safety_evaluation": evaluation,
                "workflow_status": workflow_outcome,
                "metadata": {
                    "latency": f"{round(duration, 2)}s",
                    "engine": "MedFlow-ADK-v21",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            }

        except Exception as e:
            return {
                "status": "error",
                "message": f"Pipeline failure: {str(e)}",
                "remedy": "Clinical fallback protocols initiated."
            }

# --- DEPLOYMENT SCRIPT ---
if __name__ == "__main__":
    # Pull dynamic config from .env
    PROJECT_ID = os.getenv("GCP_PROJECT_ID")
    LOCATION = os.getenv("GCP_LOCATION", "us-central1")

    if not PROJECT_ID:
        print("❌ Error: Missing GCP_PROJECT_ID in Environment")
        exit(1)

    # Initialize with the project - it will use the credentials from the shell (GitHub Actions)
    vertexai.init(project=PROJECT_ID, location=LOCATION)

    print(f"🚀 Deploying MedFlow Engine to {PROJECT_ID}...")

    try:
        # We REMOVED the service_account argument from here to fix the TypeError
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
        )

        print(f"\n✅ Deployment Complete!")
        print(f"Engine Resource ID: {remote_app.resource_name}")
        print("\n👉 Paste the Resource ID above into your UI .env file.")

    except Exception as e:
        print(f"\n❌ Deployment Failed: {str(e)}")