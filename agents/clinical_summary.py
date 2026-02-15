import json
import os
from google.genai import types

class ClinicalSummaryAgent:
    """
    Agent 3: Creates a clinician-ready structured summary.
    Optimized for February 24th with Schema Enforcement and Env-driven metadata.
    """

    def __init__(self, client):
        self.client = client
        self.model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    def create_summary(self, patient_data: dict, triage_data: dict):
        """
        Synthesizes extraction and triage results into a standardized clinical report.
        """

        # 1. Define the Strict Response Schema
        # This prevents the AI from changing key names like 'history' to 'background'
        summary_schema = {
            "type": "OBJECT",
            "properties": {
                "chief_complaint": {"type": "STRING"},
                "history": {"type": "STRING"},
                "red_flags_identified": {"type": "ARRAY", "items": {"type": "STRING"}},
                "risk_level": {
                    "type": "STRING", 
                    "enum": ["emergency", "urgent", "routine", "self-care"]
                },
                "recommended_action": {"type": "STRING"},
                "clinician_note": {"type": "STRING"}
            },
            "required": ["chief_complaint", "history", "risk_level", "clinician_note"]
        }

        system_instruction = """
        You are a Clinical Administrator producing a structured GP triage summary.
        Your goal is to synthesize patient data and triage results into a 
        concise, professional note.
        
        Style Guide:
        - Use medical terminology (e.g., 'febrile' instead of 'fever').
        - Ensure 'risk_level' matches the triage decision provided.
        """

        user_prompt = f"""
        INPUT DATA:
        PATIENT_EXTRACT: {json.dumps(patient_data)}
        TRIAGE_DECISION: {json.dumps(triage_data)}

        Task: Produce a summarized JSON report for GP review.
        """

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=summary_schema, # Forced structured output
                    temperature=0.2 
                )
            )

            return json.loads(response.text)

        except Exception as e:
            # High-reliability Fallback
            return {
                "chief_complaint": (patient_data.get("symptoms", ["Unknown"]))[0],
                "history": "Error generating clinical summary.",
                "red_flags_identified": patient_data.get("red_flags", []),
                "risk_level": triage_data.get("level", "unknown"),
                "recommended_action": "Manual triage review required.",
                "clinician_note": f"System Exception: {str(e)}"
            }