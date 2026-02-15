import hashlib
import json
import os
from datetime import datetime, timezone
from tools.ehr_store import EHRStore

class WorkflowAutomationAgent:
    """
    Agent 4: Clinical Data Governance & Workflow.
    Uses SHA-256 hashing to ensure data integrity between stages.
    """

    def __init__(self, ehr_store: EHRStore):
        self.ehr_store = ehr_store
        # App versioning helps in debugging data migrations later
        self.app_version = os.getenv("APP_VERSION", "v21-prod")

    def _generate_integrity_hash(self, data: dict) -> str:
        """
        Creates a SHA-256 snapshot of the clinical content.
        Uses sort_keys=True to ensure the hash is identical for identical data.
        """
        content = json.dumps(data, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()

    def prepare_case(self, patient_data: dict, triage_data: dict, summary_data: dict):
        """
        Packages data for the pending state. 
        Crucial for high-compliance workflows involving user consent.
        """
        clinical_content = {
            "patient": patient_data,
            "triage": triage_data,
            "summary": summary_data
        }

        case_payload = {
            "metadata": {
                "version": self.app_version,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source": "MedFlow-ADK-Engine"
            },
            "clinical_data": clinical_content
        }

        # Create a unique 'fingerprint' of this exact clinical state
        case_hash = self._generate_integrity_hash(clinical_content)

        return {
            "status": "pending_consent",
            "message": "Clinical case ready for EHR upload.",
            "payload": case_payload,
            "integrity_hash": case_hash
        }

    def confirm_and_save(self, prepared_case: dict, consent: bool):
        """
        The final "Commit" step. Re-verifies integrity before saving to BigQuery.
        """
        # 1. Verification Logic
        if not consent:
            return {"status": "cancelled", "message": "Consent withheld. Case purged."}

        # 2. Re-calculate hash to prevent 'Man-in-the-Middle' data changes
        current_hash = self._generate_integrity_hash(prepared_case["payload"]["clinical_data"])
        
        if current_hash != prepared_case.get("integrity_hash"):
            return {
                "status": "security_error", 
                "message": "Data integrity mismatch. Potential unauthorized modification detected."
            }

        # 3. Final persistence to Cloud EHR (BigQuery)
        try:
            final_record = prepared_case["payload"]
            final_record["consent_captured"] = True
            final_record["integrity_hash"] = prepared_case["integrity_hash"]
            
            # This calls your EHRStore BigQuery insert_rows_json method
            case_id = self.ehr_store.save_case(final_record)

            return {
                "status": "saved",
                "case_id": case_id,
                "message": f"Successfully committed to BigQuery archive."
            }
        except Exception as e:
            return {"status": "failed", "message": f"Cloud Storage Error: {str(e)}"}