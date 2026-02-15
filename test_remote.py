import os
import vertexai
from vertexai.preview import reasoning_engines
from dotenv import load_dotenv

# 1. Load your variables
load_dotenv()
PROJECT_ID = os.getenv("GCP_PROJECT_ID")
LOCATION = os.getenv("GCP_LOCATION", "us-central1")

# 2. Get your Engine ID (Found in your GCP Console or Deployment Logs)
# It looks like: projects/123456789/locations/us-central1/reasoningEngines/987654321
ENGINE_RESOURCE_NAME = "PASTE_YOUR_RESOURCE_NAME_HERE"

print(f"🔗 Connecting to Engine: {ENGINE_RESOURCE_NAME}")

# 3. Initialize Vertex AI
vertexai.init(project=PROJECT_ID, location=LOCATION)

try:
    # 4. Bind to the remote engine
    remote_app = reasoning_engines.ReasoningEngine(ENGINE_RESOURCE_NAME)
    
    # 5. Send a test clinical query
    print("🧠 Sending Test Query...")
    response = remote_app.query(
        message="I have a minor headache, but I am otherwise feeling fine. No known allergies.",
        consent=True,
        patient_id="TEST-VERIFY-001"
    )
    
    # 6. Check the results
    print("\n✅ CONNECTION SUCCESSFUL!")
    print(f"Triage Level: {response.get('triage', {}).get('priority', 'Unknown')}")
    print(f"Workflow Status: {response.get('workflow_status')}")
    print(f"Trace ID: {response.get('metadata', {}).get('trace_id')}")

except Exception as e:
    print(f"\n❌ CONNECTION FAILED")
    print(f"Error Details: {str(e)}")