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
        """Persists memory to GCS with root-level pathing."""
        # 1. Safety Check: Ensure the bucket name was passed from engine.py
        if not self.bucket_name:
            print("❌ MemoryStore Save Error: No bucket_name configured.")
            return

        try:
            # 2. Re-fetch bucket and blob directly
            bucket = self.storage_client.bucket(self.bucket_name)
            
            # NOTE: self.blob_name is set in engine.py as "{patient_id}.json"
            blob = bucket.blob(self.blob_name) 
            
            # 3. Forced metadata to prevent caching
            blob.cache_control = "no-store" 
            
            data_string = json.dumps(memory, indent=2)
            
            # 4. Upload to the root of the bucket (next to your .pkl files)
            blob.upload_from_string(
                data=data_string,
                content_type='application/json'
            )
            print(f"✅ SUCCESS: Saved to gs://{self.bucket_name}/{self.blob_name}")
            
        except Exception as e:
            print(f"❌ Save Error: {str(e)}")