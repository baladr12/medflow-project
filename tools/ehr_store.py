import os
import uuid
import json
from datetime import datetime, timezone
from google.cloud import bigquery

class EHRStore:
    """
    Enterprise EHR Store using Google BigQuery.
    Handles streaming clinical records with schema-safe JSON serialization.
    """
    def __init__(self):
        # Explicitly initialize client with project to prevent IAM scope issues
        self.project_id = os.getenv("GCP_PROJECT_ID")
        self.client = bigquery.Client(project=self.project_id)
        self.dataset_id = os.getenv("BQ_DATASET_ID", "clinical_records")
        self.table_id = os.getenv("BQ_TABLE_ID", "triage_cases")
        
        if not self.project_id:
            raise ValueError("GCP_PROJECT_ID must be set in environment variables.")

        self.table_path = f"{self.project_id}.{self.dataset_id}.{self.table_id}"

    def save_case(self, case_data: dict):
        """
        Saves a clinical record to BigQuery and returns a unique Case ID.
        Serializes complex agent outputs into JSON strings.
        """
        case_id = f"CASE-{uuid.uuid4().hex[:8].upper()}"
        
        # 1. Prepare clinical data objects
        # We use json.dumps() to ensure dictionaries are converted to database-friendly strings
        patient_info = json.dumps(case_data['clinical_data'].get('patient', {}))
        
        # We capture the full clinical summary object (Chief Complaint, History, etc.)
        summary_info = json.dumps(case_data['clinical_data'].get('summary', {}))

        # 2. Mapping to BigQuery Schema
        rows_to_insert = [
            {
                "case_id": case_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "patient_summary": patient_info,
                "triage_level": str(case_data['clinical_data']['triage'].get('level', 'UNKNOWN')),
                "soap_note": summary_info,
                "integrity_hash": case_data.get("integrity_hash", "N/A")
            }
        ]

        # 3. Streaming Insert
        try:
            errors = self.client.insert_rows_json(self.table_path, rows_to_insert)
            
            if errors:
                # Log specific column errors for debugging
                print(f"❌ BigQuery Insert Error Details: {errors}")
                raise RuntimeError(f"BigQuery Insert Failure: {errors}")
            
            return case_id

        except Exception as e:
            print(f"❌ Critical Storage Error: {str(e)}")
            raise e