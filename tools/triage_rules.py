def check_red_flags(data: dict) -> str:
    """
    Deterministic safety-first triage logic.
    Features: Sticky Priorities and Cardiac-Safety for allergies.
    """
    # 1. Clean and Normalize Input
    red_flags = [str(f).lower().strip() for f in data.get("red_flags", [])]
    symptoms = [str(s).lower().strip() for s in data.get("symptoms", [])]
    risk_factors = [str(r).lower().strip() for r in data.get("risk_factors", [])]
    severity = str(data.get("severity", "moderate")).lower().strip()
    
    # NEW: Get the priority from the previous turn in the conversation
    previous_priority = str(data.get("previous_priority", "routine")).lower().strip()

    # Combined indicator pool
    all_indicators = red_flags + symptoms

    # 2. EMERGENCY: Immediate Life-Threatening
    emergency_keywords = {
        "chest pain", "shortness of breath", "sob", "difficulty breathing",
        "stroke", "facial drooping", "slurred speech", "unconscious", 
        "seizure", "heavy bleeding", "suicidal ideation", "heart attack"
    }

    # RULE A: The "Never Miss" keyword check
    is_emergency_event = False
    for indicator in all_indicators:
        if any(keyword in indicator for keyword in emergency_keywords):
            is_emergency_event = True
            break

    # RULE B: Sticky Priority Logic
    # If the patient was ALREADY an emergency, do not downgrade them
    # unless a human clinician has intervened.
    if previous_priority == "emergency" or is_emergency_event:
        return "emergency"

    # 3. URGENT: High-risk groups or escalating symptoms
    high_risk_groups = {"diabetes", "heart disease", "elderly", "infant", "immunocompromised"}
    is_high_risk = any(risk in high_risk_groups for risk in risk_factors)

    if severity == "severe" or (severity == "moderate" and is_high_risk):
        return "urgent"

    # 4. ROUTINE vs SELF-CARE
    if severity == "mild" and not is_high_risk:
        return "self-care"
    
    return "routine"