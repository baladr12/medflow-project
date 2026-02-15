import os
import uuid
import json
from datetime import datetime, timezone
from google.cloud import bigquery

class EHRStore:
    """
    Enterprise EHR Store using Google BigQuery.
    Handles streaming clinical records with location-aware client initialization.
    """
    def __init__(self):
        self.project_id = os.getenv("GCP_PROJECT_ID")
        # FIX: Explicitly pull location from env to match where the table was created
        self.location = os.getenv("GCP_LOCATION", "us-central1") 
        
        # Initialize client with location to avoid cross-region 404 errors
        self.client = bigquery.Client(
            project=self.project_id,
            location=self.location
        )
        
        self.dataset_id = os.getenv("BQ_DATASET_ID", "clinical_records")
        self.table_id = os.getenv("BQ_TABLE_ID", "triage_cases")
        
        if not self.project_id:
            raise ValueError("GCP_PROJECT_ID must be set in environment variables.")

        self.table_path = f"{self.project_id}.{self.dataset_id}.{self.table_id}"

    def save_case(self, case_data: dict):
        """
        Saves a clinical record to BigQuery and returns a unique Case ID.
        """
        # Ensure table exists before attempting insert to debug pathing
        try:
            self.client.get_table(self.table_path)
        except Exception:
            print(f"⚠️ Warning: Table {self.table_path} not reachable in {self.location}. Checking permissions...")

        case_id = f"CASE-{uuid.uuid4().hex[:8].upper()}"
        
        # Prepare data
        patient_info = json.dumps(case_data['clinical_data'].get('patient', {}))
        summary_info = json.dumps(case_data['clinical_data'].get('summary', {}))

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

        try:
            # Explicitly use the table object to ensure region-safety
            errors = self.client.insert_rows_json(self.table_path, rows_to_insert)
            
            if errors:
                print(f"❌ BigQuery Insert Error Details: {errors}")
                raise RuntimeError(f"BigQuery Insert Failure: {errors}")
            
            return case_id

        except Exception as e:
            # This will now capture if it's a 404 (Path) or 403 (Permission)
            print(f"❌ Critical Storage Error: {str(e)}")
            raise e