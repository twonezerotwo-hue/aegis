"""BrainChain-facing adapter for signal-only AEGIS Core output."""

from __future__ import annotations

MODULE_SCORE_MAP = {
    "technical_score": ("technical", "touche"),
    "fundamental_score": ("fundamental",),
    "macro_score": ("macro", "sentinel"),
    "sentiment_score": ("sentiment", "news"),
    "quant_score": ("quant", "quantum"),
}

FORBIDDEN_FIELDS = {"action", "position_size", "order", "execution", "broker"}


def _normalize_score(value) -> float:
    score = float(value)
    if 0.0 <= score <= 1.0:
        score *= 100.0
    return round(max(0.0, min(100.0, score)), 4)


def _extract_scores(module_scores: dict) -> tuple[dict, list[str]]:
    warnings: list[str] = []
    result: dict[str, float] = {}

    for output_key, aliases in MODULE_SCORE_MAP.items():
        selected = None
        for alias in aliases:
            if alias in module_scores:
                selected = module_scores[alias]
                break

        if selected is None:
            result[output_key] = 50.0
            warnings.append(
                f"Missing module score for '{output_key}'; using neutral fallback score 50.0."
            )
            continue

        try:
            result[output_key] = _normalize_score(selected)
        except (TypeError, ValueError):
            result[output_key] = 50.0
            warnings.append(
                f"Module score for '{output_key}' was non-numeric; using neutral fallback score 50.0."
            )

    return result, warnings


def to_brainchain_signal(aegis_signal: dict) -> dict:
    """Convert an AEGIS Core signal into the BrainChain integration contract."""
    warnings: list[str] = []
    if not isinstance(aegis_signal, dict):
        warnings.append("AEGIS signal payload was not a dictionary.")
        aegis_signal = {}

    forbidden_present = sorted(field for field in FORBIDDEN_FIELDS if field in aegis_signal)
    if forbidden_present:
        warnings.append(
            "Forbidden decision/execution fields were present in the input and were dropped: "
            + ", ".join(forbidden_present)
            + "."
        )

    module_scores = aegis_signal.get("module_scores")
    if not isinstance(module_scores, dict):
        warnings.append("AEGIS signal did not contain a valid module_scores dictionary.")
        module_scores = {}

    mapped_scores, score_warnings = _extract_scores(module_scores)
    warnings.extend(score_warnings)

    symbol = aegis_signal.get("symbol")
    if not symbol:
        symbol = "UNKNOWN"
        warnings.append("Missing symbol in AEGIS signal; using 'UNKNOWN'.")

    timeframe = aegis_signal.get("timeframe")
    if not timeframe:
        timeframe = "UNKNOWN"
        warnings.append("Missing timeframe in AEGIS signal; using 'UNKNOWN'.")

    raw_consensus = aegis_signal.get("consensus_score", 50.0)
    try:
        consensus_score = _normalize_score(raw_consensus)
    except (TypeError, ValueError):
        consensus_score = 50.0
        warnings.append("Consensus score was missing or non-numeric; using neutral fallback score 50.0.")

    confluence = aegis_signal.get("confluence")
    cross_validation_warnings: list[str] = []
    passed = False
    multiplier = 1.0

    if isinstance(confluence, dict):
        raw_multiplier = confluence.get("multiplier", 1.0)
        try:
            multiplier = float(raw_multiplier)
        except (TypeError, ValueError):
            multiplier = 1.0
            cross_validation_warnings.append(
                "Confluence multiplier was non-numeric; defaulted to 1.0."
            )

        status = str(confluence.get("status", "unknown")).lower()
        passed = status == "aligned"

        extra_warnings = confluence.get("warnings", [])
        if isinstance(extra_warnings, list):
            cross_validation_warnings.extend(str(item) for item in extra_warnings)
    else:
        cross_validation_warnings.append(
            "No confluence payload was supplied; cross validation defaults to not passed."
        )

    permission = aegis_signal.get("decision_permission", "SIGNAL_ONLY_NOT_FINAL")
    if permission != "SIGNAL_ONLY_NOT_FINAL":
        warnings.append(
            "AEGIS signal permission was not SIGNAL_ONLY_NOT_FINAL; adapter forced the safe contract."
        )

    return {
        "source_engine": "AEGIS",
        "source_version": "7.2_core",
        "signal_type": "market_signal",
        "symbol": symbol,
        "timeframe": timeframe,
        "scores": mapped_scores,
        "cross_validation": {
            "passed": passed,
            "method": "multi_tf_confluence",
            "multiplier": round(multiplier, 4),
            "warnings": cross_validation_warnings,
        },
        "regime_hint": aegis_signal.get("raw_regime", "UNKNOWN"),
        "consensus_score": consensus_score,
        "final_decision": False,
        "decision_permission": "SIGNAL_ONLY_NOT_FINAL",
        "warnings": warnings,
    }
