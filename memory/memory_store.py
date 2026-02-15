import json
import os
from google.cloud import storage
from google.api_core import exceptions

class MemoryStore:
    """
    Cloud-based memory store using Google Cloud Storage.
    Persists long-term patient context across sessions with flexible blob naming.
    """

    def __init__(self):
        # Pull bucket name from Env Vars
        self.bucket_name = os.getenv("GCS_MEMORY_BUCKET")
        
        # Initialize with a default, but engine.py overrides this per patient
        self.blob_name = "memory/default_patient.json"
        
        # Initialize GCS Client with explicit project to avoid 403 errors
        project_id = os.getenv("GCP_PROJECT_ID")
        self.storage_client = storage.Client(project=project_id)
        self.bucket = None
        
        try:
            if self.bucket_name:
                self.bucket = self.storage_client.get_bucket(self.bucket_name)
        except Exception:
            self.bucket = None

    def _ensure_bucket(self):
        """Ensures the bucket is accessible before read/write operations."""
        if self.bucket:
            return True
        if not self.bucket_name:
            return False
        try:
            self.bucket = self.storage_client.get_bucket(self.bucket_name)
            return True
        except Exception:
            return False

    def load(self):
        """Loads memory from GCS. Returns empty dict if the patient is new."""
        if not self._ensure_bucket():
            return {}

        blob = self.bucket.blob(self.blob_name)
        
        try:
            # CRITICAL: Check if file exists to prevent 404 errors for new patients
            if not blob.exists():
                return {}
            
            content = blob.download_as_text()
            return json.loads(content)
        except Exception as e:
            # Silent failure for new sessions, log actual corruption issues
            return {}

    def save(self, memory):
        """Persists memory dictionary to the specific patient blob."""
        if not self._ensure_bucket():
            return

        try:
            blob = self.bucket.blob(self.blob_name)
            blob.upload_from_string(
                data=json.dumps(memory, indent=2),
                content_type='application/json'
            )
        except Exception as e:
            print(f"❌ Storage Save Error ({self.blob_name}): {e}")

    def update(self, new_data: dict):
        """Utility to load, merge, and save data in one atomic-style step."""
        current_memory = self.load()
        current_memory.update(new_data)
        self.save(current_memory)
        return current_memory