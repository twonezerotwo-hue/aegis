from typing import Dict


def validate_signal(macro_score: float, aegis_decision: str) -> Dict:
    """Combines macro score and AEGIS decision into actionable output."""
    decision = (aegis_decision or "HOLD").upper()

    if macro_score > 0.4 and decision == "BUY":
        return {
            "combined_decision": "GUCLU_AL",
            "position_multiplier": 1.25,
            "conflict": False,
            "reason": "Makro skor guclu pozitif ve AEGIS BUY uyumlu.",
        }

    if macro_score < -0.2 and decision == "BUY":
        return {
            "combined_decision": "CELISKI_POZISYON_KUCULT",
            "position_multiplier": 0.60,
            "conflict": True,
            "reason": "Makro negatif, AEGIS BUY ile celiski var.",
        }

    if macro_score < -0.2 and decision == "SELL":
        return {
            "combined_decision": "GUCLU_SAT",
            "position_multiplier": 1.15,
            "conflict": False,
            "reason": "Makro negatif ve AEGIS SELL uyumlu.",
        }

    if macro_score > 0.15 and decision == "BUY":
        return {
            "combined_decision": "ZAYIF_AL",
            "position_multiplier": 1.0,
            "conflict": False,
            "reason": "Pozitif makro ama guclu esik altinda.",
        }

    return {
        "combined_decision": "BEKLE",
        "position_multiplier": 0.8,
        "conflict": decision in {"BUY", "SELL"} and abs(macro_score) < 0.1,
        "reason": "Net uyum yok, ihtiyatli kal.",
    }
