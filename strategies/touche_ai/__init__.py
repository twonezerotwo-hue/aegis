"""
Touche AI Limited — AEGIS Holding Teknik Analiz Stratejisi

7 Fazlı EQS Pipeline:
  Faz 1 — Likidite Süpürmesi (Liquidity Sweep)
  Faz 2 — Piyasa Yapısı + Diverjans (Market Structure + Divergence)
  Faz 3 — Bölgeler & Confluence (Supply/Demand Zones)
  Faz 4 — Teyit (Accumulation/Distribution)
  Faz 5 — Giriş Zamanlaması (Entry Timing)
  Faz 6 — Risk Yönetimi (SL/TP + Position Sizing)
  Faz 7 — Makro Filtre (AEGIS Bridge)
"""
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

try:
    from .src.engine.orchestrator import ToucheOrchestrator
except Exception:  # pragma: no cover - optional heavy pipeline dependency
    ToucheOrchestrator = None  # type: ignore[assignment]

try:
    from .src.engine.scoring import EQSScorer
except Exception:  # pragma: no cover
    EQSScorer = None  # type: ignore[assignment]

__version__ = "1.0.0"
__strategy_id__ = "touche_ai"
__all__ = ["ToucheOrchestrator", "EQSScorer"]
