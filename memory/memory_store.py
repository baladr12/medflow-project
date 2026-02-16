import json
import os
from google.cloud import storage

class MemoryStore:
    def __init__(self):
        self.project_id = os.getenv("GCP_PROJECT_ID")
        self.bucket_name = os.getenv("GCS_MEMORY_BUCKET")
        self.blob_name = "memory/default_patient.json"
        self.storage_client = storage.Client(project=self.project_id)

    def load(self):
        """Loads memory from GCS."""
        try:
            bucket = self.storage_client.bucket(self.bucket_name)
            blob = bucket.blob(self.blob_name)
            
            if not blob.exists():
                return {}
            
            content = blob.download_as_text()
            return json.loads(content)
        except Exception as e:
            print(f"❌ Memory Load Error: {e}")
            return {}

    def save(self, memory):
        print(f"DEBUG: STARTING SAVE PROCESS FOR BUCKET: {self.bucket_name}")
        try:
            bucket = self.storage_client.bucket(self.bucket_name)
            blob = bucket.blob(self.blob_name)
            
            # LOG THIS EXACT LINE TO YOUR TERMINAL
            print(f"DEBUG: TARGET BLOB PATH: gs://{self.bucket_name}/{self.blob_name}")
            
            data_string = json.dumps(memory)
            blob.upload_from_string(data_string, content_type='application/json')
            
            print(f"DEBUG: SAVE COMPLETED SUCCESSFULLY")
        except Exception as e:
            print(f"❌ DEBUG: PHYSICAL SAVE ERROR: {str(e)}")