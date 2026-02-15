import json
import os
from google.cloud import storage
from google.api_core.exceptions import NotFound

class MemoryStore:
    """
    Cloud-based memory store using Google Cloud Storage.
    Persists long-term patient context across sessions.
    """

    def __init__(self):
        # Pull bucket name from Env Vars
        self.bucket_name = os.getenv("GCS_MEMORY_BUCKET")
        self.blob_name = os.getenv("MEMORY_BLOB_NAME", "patient_profile.json")
        
        # Initialize GCS Client
        self.storage_client = storage.Client()
        self.bucket = None
        
        # Initial attempt to connect
        try:
            if self.bucket_name:
                self.bucket = self.storage_client.get_bucket(self.bucket_name)
        except Exception:
            self.bucket = None

    def _ensure_bucket(self):
        """Re-checks for bucket presence (useful if engine.py just created it)."""
        if self.bucket:
            return True
        try:
            self.bucket = self.storage_client.get_bucket(self.bucket_name)
            return True
        except Exception:
            print(f"⚠️ Memory Warning: Bucket {self.bucket_name} not accessible.")
            return False

    def load(self):
        """Loads memory from GCS. Returns empty dict if missing."""
        if not self._ensure_bucket():
            return {}

        blob = self.bucket.blob(self.blob_name)
        if not blob.exists():
            return {}

        try:
            content = blob.download_as_text()
            return json.loads(content)
        except Exception as e:
            print(f"❌ Error loading memory: {e}")
            return {}

    def save(self, memory):
        """Persists memory to GCS bucket."""
        if not self._ensure_bucket():
            return

        try:
            blob = self.bucket.blob(self.blob_name)
            blob.upload_from_string(
                data=json.dumps(memory, indent=2),
                content_type='application/json'
            )
        except Exception as e:
            print(f"❌ Could not save to Cloud Storage: {e}")

    def update(self, new_data: dict):
        """Loads, merges, and saves memory using Cloud Storage."""
        if not new_data:
            return self.load()
            
        current_memory = self.load()
        current_memory.update(new_data)
        self.save(current_memory)
        return current_memory