import json
import os
from google.cloud import storage
from google.api_core import exceptions

class MemoryStore:
    """
    Cloud-based memory store using Google Cloud Storage.
    Uses environment variables for project and bucket configuration.
    """

    def __init__(self):
        # Dynamically pull from Environment
        self.project_id = os.getenv("GCP_PROJECT_ID")
        self.bucket_name = os.getenv("GCS_MEMORY_BUCKET")
        
        # Default blob name (engine.py overrides this per patient)
        self.blob_name = "memory/default_patient.json"
        
        # Initialize GCS Client using the detected project
        # If project_id is None, it defaults to the environment's default service account project
        self.storage_client = storage.Client(project=self.project_id)
        self.bucket = None
        
        # Initial connection attempt
        if self.bucket_name:
            try:
                self.bucket = self.storage_client.get_bucket(self.bucket_name)
            except Exception as e:
                print(f"⚠️ Memory Store Init: Could not pre-load bucket '{self.bucket_name}': {e}")

    def _ensure_bucket(self):
        """Standard check for bucket presence before I/O."""
        if self.bucket:
            return True
        if not self.bucket_name:
            print("❌ Memory Error: GCS_MEMORY_BUCKET environment variable is NOT SET.")
            return False
        try:
            self.bucket = self.storage_client.get_bucket(self.bucket_name)
            return True
        except Exception as e:
            print(f"❌ Memory Error: Access denied or bucket '{self.bucket_name}' not found: {e}")
            return False

    def load(self):
        """Loads memory from GCS. Returns empty dict if file missing or bucket error."""
        if not self._ensure_bucket():
            return {}

        blob = self.bucket.blob(self.blob_name)
        
        try:
            # This is the "New Patient" check
            if not blob.exists():
                return {}
            
            content = blob.download_as_text()
            return json.loads(content)
        except Exception as e:
            # We log this because if the file exists but can't be read, that's a real issue
            print(f"❌ Memory Load Error for {self.blob_name}: {e}")
            return {}

    def save(self, memory):
        """Persists memory to GCS."""
        if not self._ensure_bucket():
            return

        try:
            blob = self.bucket.blob(self.blob_name)
            blob.upload_from_string(
                data=json.dumps(memory, indent=2),
                content_type='application/json'
            )
        except Exception as e:
            print(f"❌ Memory Save Error for {self.blob_name}: {e}")

    def update(self, new_data: dict):
        """Atomic-style update: Load -> Merge -> Save."""
        current_memory = self.load()
        current_memory.update(new_data)
        self.save(current_memory)
        return current_memory