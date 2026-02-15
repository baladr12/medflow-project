import json
from google.genai import types
from tools.triage_rules import check_red_flags

class ClinicalTriageAgent:
    """
    Agent 2: Hybrid Clinical Triage.
    Combines deterministic rules with Gemini's clinical reasoning.
    """

    def __init__(self, client):
        self.client = client
        self.model_name = "gemini-2.0-flash"

    def triage(self, structured_input: dict):
        # 1. Deterministic Rule-Based Check (Hard Guardrail)
        rule_result = check_red_flags(structured_input)

        # 2. Define the Strict Response Schema
        triage_schema = {
            "type": "OBJECT",
            "properties": {
                "level": {
                    "type": "STRING", 
                    "enum": ["emergency", "urgent", "routine", "self-care"]
                },
                "reasoning": {"type": "STRING"},
                "action": {"type": "STRING"},
                "confidence_score": {"type": "NUMBER"} # Scale 0.0 to 1.0
            },
            "required": ["level", "reasoning", "action", "confidence_score"]
        }

        system_instruction = f"""
        You are a Clinical Triage Validator. 
        Your task is to review patient symptoms and categorize the risk.
        
        CRITICAL: A rule-based safety tool suggested: "{rule_result}". 
        Favor this result unless the clinical context suggests a higher risk level. 
        Never downgrade an 'emergency' or 'urgent' rating without extreme justification.
        """

        prompt = f"PATIENT DATA: {json.dumps(structured_input)}"

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=triage_schema,
                    temperature=0.1 
                )
            )

            return json.loads(response.text)

        except Exception as e:
            # Emergency Fail-Safe
            return {
                "level": rule_result if rule_result else "emergency",
                "reasoning": f"Fail-safe triggered: {str(e)}",
                "action": "Seek immediate medical consultation.",
                "confidence_score": 0.0
            }