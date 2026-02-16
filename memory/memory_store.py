import json
import os
from google.cloud import storage

class MemoryStore:
    def __init__(self):
        self.project_id = os.getenv("GCP_PROJECT_ID")
        self.bucket_name = os.getenv("GCS_MEMORY_BUCKET")
        self.blob_name = "sessions/default.json" # Default prefix matches engine.py
        # Remove self.storage_client from here to avoid pickling issues

    def _get_client(self):
        """Lazy load the client to ensure it uses the cloud's runtime identity."""
        return storage.Client(project=self.project_id)

    def load(self):
        try:
            client = self._get_client()
            bucket = client.bucket(self.bucket_name)
            blob = bucket.blob(self.blob_name)
            
            if not blob.exists():
                print(f"DEBUG: No blob found at {self.blob_name}")
                return {}
            
            content = blob.download_as_text()
            return json.loads(content)
        except Exception as e:
            print(f"❌ Memory Load Error: {e}")
            return {}

    def save(self, memory):
        print(f"DEBUG: STARTING SAVE PROCESS FOR BUCKET: {self.bucket_name}")
        try:
            client = self._get_client()
            bucket = client.bucket(self.bucket_name)
            blob = bucket.blob(self.blob_name)
            
            print(f"DEBUG: TARGET BLOB PATH: gs://{self.bucket_name}/{self.blob_name}")
            
            data_string = json.dumps(memory)
            # Use 'if_generation_match' or similar if you need concurrency control, 
            # but for now, standard upload:
            blob.upload_from_string(data_string, content_type='application/json')
            
            print(f"DEBUG: SAVE COMPLETED SUCCESSFULLY")
        except Exception as e:
            print(f"❌ DEBUG: PHYSICAL SAVE ERROR: {str(e)}")