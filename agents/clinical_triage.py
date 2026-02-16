import json
from google.genai import types
from tools.triage_rules import check_red_flags

class ClinicalTriageAgent:
    """
    Agent 2: Hybrid Clinical Triage.
    Combines deterministic rules with Gemini's clinical reasoning.
    Now with Mandatory Follow-up Questions for non-emergency cases.
    """

    def __init__(self, client):
        self.client = client
        self.model_name = "gemini-2.0-flash"

    def triage(self, structured_input: dict):
        # 1. Deterministic Rule-Based Check (Hard Guardrail)
        rule_result = check_red_flags(structured_input)

        # 2. Define the Strict Response Schema
        # Added 'questions' as a required array to ensure UI compatibility
        triage_schema = {
            "type": "OBJECT",
            "properties": {
                "level": {
                    "type": "STRING", 
                    "enum": ["emergency", "urgent", "routine", "self-care"]
                },
                "reasoning": {"type": "STRING"},
                "action": {"type": "STRING"},
                "questions": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"}
                },
                "confidence_score": {"type": "NUMBER"}
            },
            "required": ["level", "reasoning", "action", "questions", "confidence_score"]
        }

        # 3. Enhanced Instructions
        # We mandate questions for 'routine' or 'urgent' to improve diagnostic depth.
        system_instruction = f"""
        You are a Clinical Triage Validator. 
        
        SAFETY MANDATE:
        The safety tool has classified this session as: "{rule_result.upper()}".
        If the safety tool says 'emergency', you MUST return 'emergency'. 
        
        INVESTIGATION MANDATE:
        If the triage level is 'routine' or 'urgent', you MUST generate 3-5 clinical follow-up 
        questions to rule out life-threatening conditions (e.g., asking about fever, 
        pain location, or associated symptoms). 
        If the level is 'emergency', the 'questions' array should be empty as immediate action is required.
        """

        prompt = f"NEW PATIENT DATA: {json.dumps(structured_input)}"

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=triage_schema,
                    temperature=0.0 
                )
            )

            result = json.loads(response.text)

            # --- THE FINAL GUARDRAIL (Python Level) ---
            if rule_result == "emergency":
                result["level"] = "emergency"
                result["reasoning"] = f"EMERGENCY LATCH ACTIVE: {result.get('reasoning', '')}"
                result["action"] = "IMMEDIATE EMERGENCY ACTION REQUIRED: Call 911/EMS."
                result["questions"] = [] # Clear questions for emergency
            
            return result

        except Exception as e:
            return {
                "level": rule_result if rule_result else "emergency",
                "reasoning": f"Fail-safe triggered: {str(e)}",
                "action": "Seek immediate medical consultation.",
                "questions": ["Can you describe your symptoms in more detail?"],
                "confidence_score": 0.0
            }