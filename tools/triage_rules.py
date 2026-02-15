def check_red_flags(data: dict) -> str:
    """
    Deterministic safety-first triage logic.
    Priority 1: Sticky Memory (Once Emergency, always Emergency)
    Priority 2: Keyword Detection (New Emergency)
    Priority 3: Risk-based Triage (Urgent/Routine)
    """
    # 1. Normalize All Inputs
    red_flags = [str(f).lower().strip() for f in data.get("red_flags", [])]
    symptoms = [str(s).lower().strip() for s in data.get("symptoms", [])]
    risk_factors = [str(r).lower().strip() for r in data.get("risk_factors", [])]
    severity = str(data.get("severity", "moderate")).lower().strip()
    
    # Extract previous state passed from engine.py
    previous_priority = str(data.get("previous_priority", "routine")).lower().strip()

    # --- RULE 1: THE STICKY GUARDRAIL (THE LATCH) ---
    # If the previous turn was an emergency, we lock the status.
    # This prevents downgrading when the patient mentions a non-emergency detail.
    if previous_priority == "emergency":
        return "emergency"

    # 2. EMERGENCY: Immediate Life-Threatening Keywords
    emergency_keywords = {
        "chest pain", "shortness of breath", "sob", "difficulty breathing",
        "stroke", "facial drooping", "slurred speech", "unconscious", 
        "seizure", "heavy bleeding", "suicidal ideation", "heart attack",
        "dizzy", "radiating pain", "arm pain"
    }

    # Combined indicator pool for new detection
    all_indicators = red_flags + symptoms

    # --- RULE 2: NEW EMERGENCY DETECTION ---
    for indicator in all_indicators:
        if any(keyword in indicator for keyword in emergency_keywords):
            return "emergency"

    # 3. URGENT: High-risk groups or escalating symptoms
    high_risk_groups = {"diabetes", "heart disease", "elderly", "infant", "immunocompromised", "hypertension"}
    is_high_risk = any(risk in high_risk_groups for risk in risk_factors)

    # --- RULE 3: URGENT ESCALATION ---
    if severity == "severe" or (severity == "moderate" and is_high_risk):
        return "urgent"

    # 4. ROUTINE vs SELF-CARE
    # --- RULE 4: DEFAULTING ---
    if severity == "mild" and not is_high_risk:
        return "self-care"
    
    return "routine"