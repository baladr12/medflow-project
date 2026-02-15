import json
import os
from google.cloud import storage
from google.api_core import exceptions

class MemoryStore:
    """
    Cloud-based memory store using Google Cloud Storage.
    Features: Cache-busting, Atomic Bucket Resolution, and Consistency Checks.
    """

    def __init__(self):
        self.project_id = os.getenv("GCP_PROJECT_ID")
        self.bucket_name = os.getenv("GCS_MEMORY_BUCKET")
        self.blob_name = "memory/default_patient.json"
        
        # Initialize Client
        self.storage_client = storage.Client(project=self.project_id)
        self.bucket = None

    def _ensure_bucket(self):
        """Standard check for bucket presence. Re-fetches if bucket name changed."""
        # Always re-sync bucket_name from env in case engine.py updated it
        self.bucket_name = os.getenv("GCS_MEMORY_BUCKET")
        
        if self.bucket and self.bucket.name == self.bucket_name:
            return True
            
        if not self.bucket_name:
            print("❌ Memory Error: GCS_MEMORY_BUCKET environment variable is NOT SET.")
            return False
            
        try:
            self.bucket = self.storage_client.bucket(self.bucket_name)
            return True
        except Exception as e:
            print(f"❌ Memory Error: Access denied or bucket '{self.bucket_name}' not found: {e}")
            return False

    def load(self):
        """Loads memory from GCS. Returns empty dict if file missing."""
        if not self._ensure_bucket():
            return {}

        blob = self.bucket.blob(self.blob_name)
        
        try:
            # Reload blob to ensure we have the latest metadata from the cloud
            if not blob.exists():
                return {}
            
            content = blob.download_as_text()
            return json.loads(content)
        except Exception as e:
            print(f"❌ Memory Load Error for {self.blob_name}: {e}")
            return {}

    def save(self, memory):
        """
        Persists memory to GCS. 
        Includes cache-control to prevent 'stale reads' on the next turn.
        """
        if not self._ensure_bucket():
            return

        try:
            blob = self.bucket.blob(self.blob_name)
            
            # Use Cache-Control: no-cache to ensure turn 2 doesn't read old data
            blob.cache_control = "no-cache, max-age=0"
            
            blob.upload_from_string(
                data=json.dumps(memory, indent=2),
                content_type='application/json'
            )
            
            # --- CONSISTENCY CHECK ---
            if not blob.exists():
                print(f"⚠️ Warning: Save call finished but blob {self.blob_name} is not visible yet.")
                
        except Exception as e:
            print(f"❌ Memory Save Error for {self.blob_name}: {e}")

    def update(self, new_data: dict):
        """Atomic-style update: Load -> Merge -> Save."""
        current_memory = self.load()
        current_memory.update(new_data)
        self.save(current_memory)
        return current_memory