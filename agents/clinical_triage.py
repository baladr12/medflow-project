import json
from google.genai import types
from tools.triage_rules import check_red_flags

class ClinicalTriageAgent:
    """
    Agent 2: Hybrid Clinical Triage.
    Combines deterministic rules with Gemini's clinical reasoning.
    Now with Mandatory Latch for Emergency Status.
    """

    def __init__(self, client):
        self.client = client
        self.model_name = "gemini-2.0-flash"

    def triage(self, structured_input: dict):
        # 1. Deterministic Rule-Based Check (Hard Guardrail)
        # This will return 'emergency' if 'previous_priority' was 'emergency'
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
                "confidence_score": {"type": "NUMBER"}
            },
            "required": ["level", "reasoning", "action", "confidence_score"]
        }

        # 3. Enhanced Instructions
        # We tell the AI EXPLICITLY about the session history and the rule result.
        system_instruction = f"""
        You are a Clinical Triage Validator. 
        
        SAFETY MANDATE:
        The safety tool has classified this session as: "{rule_result.upper()}".
        
        If the safety tool says 'emergency', you MUST return 'emergency'. 
        This is because a life-threatening condition was identified earlier in this 
        patient encounter (Sticky Priority). Even if the latest message seems minor, 
        the patient is still in an active emergency state.
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
                    temperature=0.0  # Zero temperature for maximum consistency
                )
            )

            result = json.loads(response.text)

            # --- THE FINAL GUARDRAIL (Python Level) ---
            # If the rules say emergency but Gemini tried to downgrade, we force it back.
            if rule_result == "emergency" and result["level"] != "emergency":
                result["level"] = "emergency"
                result["reasoning"] = f"EMERGENCY LATCH: {result['reasoning']} (Priority maintained due to active emergency status in this session)."
            
            return result

        except Exception as e:
            return {
                "level": rule_result if rule_result else "emergency",
                "reasoning": f"Fail-safe triggered: {str(e)}",
                "action": "Seek immediate medical consultation.",
                "confidence_score": 0.0
            }