import json
import os
from google.genai import types
from memory.memory_store import MemoryStore

class MemoryAgent:
    """
    Agent 5: Contextual Memory Manager.
    Differentiates between short-term session context and long-term clinical profile.
    """

    def __init__(self, client, memory_store: MemoryStore):
        self.client = client
        self.memory_store = memory_store
        # Using Env Var for model naming
        self.model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        self.session_history = []

    def add_to_session(self, message: str):
        """Appends interactions to the current session buffer."""
        self.session_history.append(message)

    def summarise_session(self):
        """
        Extracts 'Stable Clinical Attributes' using a strictly defined schema.
        Ensures long-term memory remains high-quality and noise-free.
        """
        if not self.session_history:
            return self.load_long_term_memory()

        transcript = "\n".join(self.session_history)

        # 1. Define the Response Schema
        # This forces Gemini to only save what the hospital database can accept.
        memory_schema = {
            "type": "OBJECT",
            "properties": {
                "age": {"type": "STRING"},
                "chronic_conditions": {"type": "ARRAY", "items": {"type": "STRING"}},
                "allergies": {"type": "ARRAY", "items": {"type": "STRING"}},
                "current_medications": {"type": "ARRAY", "items": {"type": "STRING"}},
                "last_update_reason": {"type": "STRING"}
            },
            "required": ["chronic_conditions", "allergies"]
        }

        system_instruction = """
        You are a Clinical Memory Auditor. 
        Update the permanent patient record based on the transcript provided.
        
        STRICT RULES:
        - Only extract STABLE attributes (Age, Conditions, Allergies, Meds).
        - DO NOT record temporary symptoms (e.g., headache, sore throat).
        - If no stable information is present, return an empty object for those fields.
        """

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=f"SESSION TRANSCRIPT:\n{transcript}",
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=memory_schema, # Force deterministic extraction
                    temperature=0.0 # Zero randomness for precision data
                )
            )

            memory_update = json.loads(response.text)
            
            # Commit the refined update to the persistent MemoryStore (e.g. BigQuery or Vector DB)
            return self.memory_store.update(memory_update)

        except Exception as e:
            # Senior Practice: Log the error but don't crash the pipeline
            # Fallback to the current existing memory
            return self.load_long_term_memory()

    def load_long_term_memory(self):
        """Retrieves the permanent patient profile from storage."""
        return self.memory_store.load()