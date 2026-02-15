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
        
        # FIXED: Initialize with a default, but allow engine.py to override this
        # for specific patient isolation.
        self.blob_name = "memory/default_patient.json"
        
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
        if not self.bucket_name:
            print("❌ Memory Error: GCS_MEMORY_BUCKET environment variable is not set.")
            return False
        try:
            self.bucket = self.storage_client.get_bucket(self.bucket_name)
            return True
        except Exception:
            print(f"⚠️ Memory Warning: Bucket {self.bucket_name} not accessible.")
            return False

    def load(self):
        """Loads memory from GCS using the current self.blob_name."""
        if not self._ensure_bucket():
            return {}

        # The blob name is now dynamic based on what engine.py set it to
        blob = self.bucket.blob(self.blob_name)
        
        try:
            if not blob.exists():
                return {}
            
            content = blob.download_as_text()
            return json.loads(content)
        except Exception as e:
            print(f"❌ Error loading memory from {self.blob_name}: {e}")
            return {}

    def save(self, memory):
        """Persists memory to the specific blob name in the GCS bucket."""
        if not self._ensure_bucket():
            return

        try:
            blob = self.bucket.blob(self.blob_name)
            blob.upload_from_string(
                data=json.dumps(memory, indent=2),
                content_type='application/json'
            )
        except Exception as e:
            print(f"❌ Could not save to Cloud Storage ({self.blob_name}): {e}")

    def update(self, new_data: dict):
        """Loads, merges, and saves memory using the current patient context."""
        if not new_data:
            return self.load()
            
        current_memory = self.load()
        current_memory.update(new_data)
        self.save(current_memory)
        return current_memory