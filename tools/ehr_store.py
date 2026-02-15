import os
import uuid
from datetime import datetime, timezone
from google.cloud import bigquery

class EHRStore:
    """
    Enterprise EHR Store using Google BigQuery.
    Handles streaming clinical records with schema-safe inserts.
    """
    def __init__(self):
        # Configuration pulled from Environment Variables
        self.client = bigquery.Client()
        self.project_id = os.getenv("GCP_PROJECT_ID")
        self.dataset_id = os.getenv("BQ_DATASET_ID", "clinical_records")
        self.table_id = os.getenv("BQ_TABLE_ID", "triage_cases")
        
        if not self.project_id:
            raise ValueError("GCP_PROJECT_ID must be set in environment variables.")

        self.table_path = f"{self.project_id}.{self.dataset_id}.{self.table_id}"

    def save_case(self, case_data: dict):
        """
        Saves a clinical record to BigQuery and returns a unique Case ID.
        """
        case_id = f"CASE-{uuid.uuid4().hex[:8].upper()}"
        
        # Mapping to the exact schema provisioned in engine.py
        rows_to_insert = [
            {
                "case_id": case_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "patient_summary": str(case_data['clinical_data']['patient']),
                "triage_level": case_data['clinical_data']['triage'].get('level'),
                "soap_note": case_data['clinical_data']['summary'],
                "integrity_hash": case_data.get("integrity_hash", "N/A")
            }
        ]

        # Insert data using the Streaming API
        errors = self.client.insert_rows_json(self.table_path, rows_to_insert)
        
        if errors:
            print(f"❌ BigQuery Insert Error Details: {errors}")
            raise RuntimeError(f"BigQuery Insert Failure: {errors}")
        
        return case_id