import json
import os
from google.genai import types

class FollowUpAgent:
    """
    Agent 6: Risk-Stratified Safety Netting.
    Generates dynamic next-steps based on clinical severity.
    """

    def __init__(self, client):
        self.client = client
        self.model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    def generate_followup(self, patient_data: dict, triage_data: dict, summary_data: dict):
        """
        Synthesizes the pipeline output to provide contextual safety instructions.
        """
        
        # 1. Define the Response Schema
        # Ensures the front-end UI never breaks when rendering these questions.
        followup_schema = {
            "type": "OBJECT",
            "properties": {
                "triage_level": {
                    "type": "STRING",
                    "enum": ["emergency", "urgent", "routine", "self-care"]
                },
                "follow_up_questions": {
                    "type": "ARRAY", 
                    "items": {"type": "STRING"}
                },
                "safety_net_advice": {"type": "STRING"},
                "critical_flag": {"type": "BOOLEAN"}, # UI helper: true if high risk
                "rationale": {"type": "STRING"}
            },
            "required": ["triage_level", "follow_up_questions", "safety_net_advice", "critical_flag"]
        }

        system_instruction = """
        You are a Clinical Safety Assistant. Your goal is to provide 
        immediate, relevant follow-up questions and safety-netting advice.

        STRATEGY BY PRIORITY:
        - EMERGENCY: Prioritize immediate physical safety and location.
        - URGENT: Identify progression or worsening of specific symptoms.
        - ROUTINE/SELF-CARE: Provide monitoring guidelines and "red flag" triggers for re-contact.
        """

        user_prompt = f"""
        TRIAGE LEVEL: {triage_data.get('level', 'unknown')}
        CHIEF COMPLAINT: {summary_data.get('chief_complaint', 'unknown')}
        RED FLAGS IDENTIFIED: {json.dumps(patient_data.get('red_flags', []))}

        Task: Generate structured safety-netting questions and advice.
        """

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=followup_schema,
                    temperature=0.3 
                )
            )

            return json.loads(response.text)

        except Exception as e:
            # High-safety default fallback
            level = triage_data.get("level", "urgent")
            return {
                "triage_level": level,
                "follow_up_questions": ["Has your condition worsened?", "Are you experiencing any new pain?"],
                "safety_net_advice": "If symptoms worsen, contact emergency services immediately.",
                "critical_flag": True if level in ["emergency", "urgent"] else False,
                "rationale": f"Fallback triggered: {str(e)}"
            }