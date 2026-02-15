import json
from google.genai import types

class PatientUnderstandingAgent:
    """
    Agent 1: Extracts structured clinical information.
    Enhanced with explicit schemas for production reliability.
    """

    def __init__(self, client):
        self.client = client
        self.model_name = "gemini-2.0-flash" 

    def analyse(self, message: str):
        # 1. Define the EXACT structure we want (The Schema)
        # This ensures the rest of your 7 agents don't crash due to missing keys.
        extraction_schema = {
            "type": "OBJECT",
            "properties": {
                "symptoms": {"type": "ARRAY", "items": {"type": "STRING"}},
                "duration": {"type": "STRING"},
                "severity": {"type": "STRING", "enum": ["low", "medium", "high", "unknown"]},
                "red_flags": {"type": "ARRAY", "items": {"type": "STRING"}},
                "brief_summary": {"type": "STRING"}
            },
            "required": ["symptoms", "severity", "red_flags"]
        }

        system_instruction = """
        You are a MedFlow Clinical Intake Specialist. 
        Extract symptoms, duration, severity, and red flags from the patient's message.
        If a specific field is not mentioned, use 'unknown' or an empty list.
        """

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=f"Patient Message: {message}",
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    # This tells Gemini: "You MUST follow this exact JSON shape"
                    response_schema=extraction_schema, 
                    temperature=0.1
                )
            )

            return json.loads(response.text)

        except Exception as e:
            # Senior practice: Return a valid object even on failure so the pipeline continues
            return {
                "symptoms": [],
                "duration": "unknown",
                "severity": "unknown",
                "red_flags": [],
                "brief_summary": f"System error: {str(e)}"
            }