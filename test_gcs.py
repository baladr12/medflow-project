import os
from google.cloud import storage
from google.auth.credentials import AnonymousCredentials

# Set this to your service account JSON path if you have it, 
# otherwise it uses your active gcloud login
os.environ["GCS_MEMORY_BUCKET"] = "medflow-memory-486618"

def test_write():
    bucket_name = os.getenv("GCS_MEMORY_BUCKET")
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob("permission_test.json")
    
    print(f"Testing write access to: gs://{bucket_name}/permission_test.json")
    try:
        blob.upload_from_string('{"status": "permissions_ok"}', content_type='application/json')
        print("✅ SUCCESS: Service account can write to bucket!")
        # Clean up
        blob.delete()
        print("🗑️ TEST FILE DELETED.")
    except Exception as e:
        print(f"❌ FAILURE: Could not write to bucket. Error: {e}")

if __name__ == "__main__":
    test_write()