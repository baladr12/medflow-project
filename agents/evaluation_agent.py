import json
import os
from google.genai import types

class EvaluationAgent:
    """
    Agent 7: The Auditor.
    Combines deterministic Safety Checks with LLM-as-a-Judge.
    Ensures the pipeline adheres to clinical safety standards before finalizing.
    """

    def __init__(self, client):
        self.client = client
        self.model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    # 1. Deterministic Safety Check (Hard-coded Logic)
    def rule_based_score(self, structured_data: dict, triage_data: dict):
        """
        Hard guardrails: Checks that do not rely on AI 'feelings'.
        """
        score = 0
        notes = []

        # Check: Red Flag recognition
        if structured_data.get("red_flags"):
            score += 20
            notes.append("Red flags correctly parsed.")
        
        # Check: Critical Symptom Triage Alignment
        symptoms = [s.lower() for s in structured_data.get("symptoms", [])]
        triage_level = triage_data.get("level", "").lower()
        
        # Senior logic: Chest pain or difficulty breathing must be emergency
        critical_triggers = ["chest pain", "difficulty breathing", "shortness of breath", "stroke"]
        if any(trigger in symptoms for trigger in critical_triggers) and triage_level != "emergency":
            score -= 60  # Critical safety penalty
            notes.append("CRITICAL FAILURE: High-risk symptom not triaged as emergency.")
        else:
            score += 20
            notes.append("Triage level appears safe for symptoms provided.")

        return score, notes

    # 2. LLM-AS-A-JUDGE (Qualitative Audit)
    def llm_judge(self, structured_data: dict, triage_data: dict, summary_data: dict):
        
        evaluation_schema = {
            "type": "OBJECT",
            "properties": {
                "clinical_accuracy": {"type": "NUMBER"}, # Scale 1-10
                "triage_appropriateness": {"type": "NUMBER"}, # Scale 1-10
                "summary_clarity": {"type": "NUMBER"}, # Scale 1-10
                "dangerous_omissions": {"type": "BOOLEAN"},
                "comment": {"type": "STRING"}
            },
            "required": ["clinical_accuracy", "dangerous_omissions", "comment"]
        }

        system_instruction = """
        You are a Senior Medical Auditor. Grade the output of a clinical AI pipeline.
        Evaluate if the triage level is medically sound and if the GP summary is accurate.
        Identify if any critical patient information was lost during processing.
        """

        prompt = f"""
        INPUTS TO AUDIT:
        - EXTRACTION: {json.dumps(structured_data)}
        - TRIAGE: {json.dumps(triage_data)}
        - SUMMARY: {json.dumps(summary_data)}
        """

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=evaluation_schema,
                    temperature=0.0 # Strict audit
                )
            )
            return json.loads(response.text)
        except Exception as e:
            return {
                "clinical_accuracy": 0, 
                "dangerous_omissions": True, 
                "comment": f"Auditor error: {str(e)}"
            }

    # 3. Final Aggregation
    def evaluate(self, structured_data, triage_data, summary_data):
        rb_score, rb_notes = self.rule_based_score(structured_data, triage_data)
        llm_eval = self.llm_judge(structured_data, triage_data, summary_data)

        # Weighted calculation for a "Clinical Grade"
        # We penalize more heavily for dangerous omissions
        total_score = (rb_score + 
                      (llm_eval.get("clinical_accuracy", 0) * 3) + 
                      (llm_eval.get("summary_clarity", 0) * 2))
        
        # Fail if audit score is low OR if the judge found dangerous omissions
        safety_pass = total_score > 50 and not llm_eval.get("dangerous_omissions", False)

        return {
            "final_safety_score": total_score,
            "safety_pass": safety_pass,
            "rule_audit": rb_notes,
            "judge_report": llm_eval
        }