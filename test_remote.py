import os
import vertexai
import time
from vertexai.preview import reasoning_engines
from dotenv import load_dotenv

load_dotenv()
PROJECT_ID = os.getenv("GCP_PROJECT_ID")
LOCATION = os.getenv("GCP_LOCATION", "us-central1")

# Use your deployed engine ID
ENGINE_RESOURCE_NAME = "PASTE_YOUR_RESOURCE_NAME_HERE"

vertexai.init(project=PROJECT_ID, location=LOCATION)
remote_app = reasoning_engines.ReasoningEngine(ENGINE_RESOURCE_NAME)

# Use a unique ID for this specific test run
test_patient = f"STRESS-TEST-{int(time.time())}"

def run_test():
    print(f"🚀 Starting Sticky Memory Test for Patient: {test_patient}")

    # --- TURN 1: THE EMERGENCY ---
    print("\n💉 TURN 1: Reporting Stroke Symptoms...")
    msg1 = "My grandmother's face is drooping on the left side and she can't speak."
    resp1 = remote_app.query(message=msg1, patient_id=test_patient)
    
    level1 = resp1.get('triage', {}).get('level')
    print(f"Result 1: {level1.upper()}")

    if level1 != "emergency":
        print("❌ FAILED: Turn 1 should have been EMERGENCY.")
        return

    # Wait 2 seconds to ensure GCS consistency
    print("⏳ Waiting for cloud persistence...")
    time.sleep(2)

    # --- TURN 2: THE STICKY CHECK ---
    print("\n💉 TURN 2: Reporting a Minor Symptom (The Latch Test)...")
    msg2 = "She also has a slightly itchy toe."
    resp2 = remote_app.query(message=msg2, patient_id=test_patient)
    
    level2 = resp2.get('triage', {}).get('level')
    reasoning2 = resp2.get('triage', {}).get('reasoning', '')

    print(f"Result 2: {level2.upper()}")
    print(f"Reasoning: {reasoning2[:100]}...")

    # --- FINAL VERDICT ---
    if level2 == "emergency":
        print("\n✅ TEST PASSED: Memory is STICKY. Emergency status maintained!")
    else:
        print("\n❌ TEST FAILED: Status reverted to routine. Check GCS bucket permissions.")

if __name__ == "__main__":
    try:
        run_test()
    except Exception as e:
        print(f"💥 Error: {e}")