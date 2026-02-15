def check_red_flags(data: dict) -> str:
    """
    Deterministic safety-first triage logic.
    Acts as the 'Hard Guardrail' for the MedFlow Engine.
    """
    # 1. Clean and Normalize Input
    red_flags = [str(f).lower().strip() for f in data.get("red_flags", [])]
    symptoms = [str(s).lower().strip() for s in data.get("symptoms", [])]
    severity = str(data.get("severity", "moderate")).lower().strip()
    risk_factors = [str(r).lower().strip() for r in data.get("risk_factors", [])]

    # Combined indicator pool
    all_indicators = red_flags + symptoms

    # 2. EMERGENCY: Immediate Life-Threatening (The 'Never Miss' List)
    emergency_keywords = {
        "chest pain", "shortness of breath", "sob", "difficulty breathing",
        "stroke", "facial drooping", "slurred speech", "unconscious", 
        "seizure", "heavy bleeding", "suicidal ideation"
    }

    # Check for any overlap with emergency keywords
    # Using partial matching (e.g., 'sharp chest pain' matches 'chest pain')
    for indicator in all_indicators:
        if any(keyword in indicator for keyword in emergency_keywords):
            return "emergency"

    # 3. URGENT: High-risk groups or escalating symptoms
    high_risk_groups = {"diabetes", "heart disease", "elderly", "infant", "immunocompromised"}
    is_high_risk = any(risk in high_risk_groups for risk in risk_factors)

    if severity == "severe":
        return "urgent"
    
    if severity == "moderate" and is_high_risk:
        return "urgent"

    # 4. ROUTINE vs SELF-CARE
    if severity == "mild" and not is_high_risk:
        return "self-care"
    
    return "routine"