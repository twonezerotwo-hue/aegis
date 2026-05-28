"""
AEGIS Holding — Stage Attribution Logger

Her trade'den sonra hangi aşamaların kar/zarara katkısını analiz eder.
7 aşamanın sinyal gücü ile final PnL arasındaki korelasyonu hesaplar.

Phase 1 enhancement: Post-trade attribution analysis
"""
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone
import numpy as np
import yaml
import logging
import os

logger = logging.getLogger(__name__)


@dataclass
class AttributionReport:
    """Aşama atribüt analiz sonucu."""
    timestamp: str
    total_trades_analyzed: int
    winning_trades: int
    losing_trades: int

    # Per-phase attribution scores (Pearson correlation: -1.0 to 1.0)
    phase_attribution: Dict[int, float]  # Correlation between signal and PnL

    # PnL contribution estimate (% of total)
    phase_pnl_contribution: Dict[int, float]

    # Confidence scores (0.0-1.0)
    phase_confidence: Dict[int, float]

    # Summary statistics
    total_pnl: float
    win_rate: float
    avg_phase_signals: Dict[int, float]

    # Recommendations
    recommendations: List[str] = field(default_factory=list)


class AttributionLogger:
    """
    Aşama atribüsyon hesapları.
    İstatistiksel yöntem: Pearson correlation
    """

    def __init__(self, min_trades_for_correlation: int = 30):
        """
        Args:
            min_trades_for_correlation: Correlation hesapı için gerekli min trade sayısı
        """
        self.min_trades = min_trades_for_correlation
        self.logger = logging.getLogger(__name__)

    def calculate_attribution(
        self,
        trades: List,  # List[TradeRecord]
        phases: List[int] = None,
    ) -> AttributionReport:
        """
        Trade geçmişinden aşama atribüsyon hesapla.

        Yöntem:
        1. stage_signals ve PnL'yi matrise çıkart
        2. Her aşama için signal strength vs trade PnL'in korelasyonunu hesapla
        3. PnL katkısını tahmin et (ağırlıklı ortalama)
        4. Rekomendasyonlar oluştur

        Args:
            trades: Tamamlanan işlem listesi (stage_signals dolu olmalı)
            phases: Analiz edilecek aşama IDs (default: [1-7])

        Returns:
            AttributionReport detaylı özellik kırılımı ile
        """
        if not phases:
            phases = list(range(1, 8))

        if len(trades) < self.min_trades:
            self.logger.warning(f"Yetersiz trade sayısı ({len(trades)}) atribüsyon için")
            return self._create_neutral_report(trades)

        # Sinyal ve PnL'yi matrise çıkart
        signal_matrix = self._extract_signal_matrix(trades, phases)  # (n_trades, n_phases)
        pnl_vector = np.array([t.pnl for t in trades])

        # Per-aşama atribüsyon hesapla
        phase_attribution = {}
        phase_confidence = {}

        for phase_idx, phase_id in enumerate(phases):
            signals = signal_matrix[:, phase_idx]

            # Correlation-based attribution (variance > 0.01 ise)
            if np.std(signals) > 0.01:
                corr = np.corrcoef(signals, pnl_vector)[0, 1]
                phase_attribution[phase_id] = np.nan_to_num(corr, nan=0.0)

                # Confidence = |correlation| + trade count factor
                trade_factor = min(1.0, len(trades) / 100.0)
                phase_confidence[phase_id] = min(1.0, abs(corr) + trade_factor * 0.3)
            else:
                phase_attribution[phase_id] = 0.0
                phase_confidence[phase_id] = 0.1

        # PnL katkı hesapla (weighted by signal strength × correlation)
        phase_pnl_contribution = self._calculate_pnl_contribution(
            signal_matrix, pnl_vector, phase_attribution, phases
        )

        # Rekomendasyonlar oluştur
        recommendations = self._generate_recommendations(
            phase_attribution, phase_confidence, phase_pnl_contribution
        )

        # Aşama başına ortalama sinyaller
        avg_signals = {
            phases[i]: float(np.mean(signal_matrix[:, i]))
            for i in range(len(phases))
        }

        report = AttributionReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
            total_trades_analyzed=len(trades),
            winning_trades=sum(1 for t in trades if t.is_winning),
            losing_trades=sum(1 for t in trades if not t.is_winning),
            phase_attribution=phase_attribution,
            phase_pnl_contribution=phase_pnl_contribution,
            phase_confidence=phase_confidence,
            total_pnl=float(pnl_vector.sum()),
            win_rate=sum(1 for t in trades if t.is_winning) / len(trades),
            avg_phase_signals=avg_signals,
            recommendations=recommendations,
        )

        return report

    def _extract_signal_matrix(
        self,
        trades: List,
        phases: List[int],
    ) -> np.ndarray:
        """Aşama sinyallerini matrise çıkart (n_trades × n_phases)."""
        n_trades = len(trades)
        n_phases = len(phases)
        matrix = np.zeros((n_trades, n_phases))

        for trade_idx, trade in enumerate(trades):
            for phase_idx, phase_id in enumerate(phases):
                matrix[trade_idx, phase_idx] = trade.stage_signals.get(phase_id, 0.0)

        return matrix

    def _calculate_pnl_contribution(
        self,
        signal_matrix: np.ndarray,
        pnl_vector: np.ndarray,
        attribution: Dict[int, float],
        phases: List[int],
    ) -> Dict[int, float]:
        """Her aşamanın total PnL'ye katkısını tahmin et."""
        total_pnl = pnl_vector.sum()
        if total_pnl == 0:
            return {phase_id: 0.0 for phase_id in phases}

        contribution = {}
        for phase_idx, phase_id in enumerate(phases):
            signals = signal_matrix[:, phase_idx]
            corr_weight = abs(attribution[phase_id])
            signal_weight = np.mean(signals)

            # Katkı = correlation × ortalama sinyal × total PnL
            phase_pnl = corr_weight * signal_weight * total_pnl
            contribution[phase_id] = phase_pnl / total_pnl * 100  # % cinsinden

        return contribution

    def _generate_recommendations(
        self,
        attribution: Dict[int, float],
        confidence: Dict[int, float],
        contribution: Dict[int, float],
    ) -> List[str]:
        """Atribüsyon sonuçlarından tuning rekomendasyonları oluştur."""
        recommendations = []

        # Aşamaları korelasyonun mutlak değerine göre sırala
        for phase_id, attr_score in sorted(
            attribution.items(), key=lambda x: abs(x[1]), reverse=True
        ):
            conf = confidence[phase_id]
            contrib = contribution[phase_id]

            if conf < 0.3:
                recommendations.append(
                    f"Aşama {phase_id}: Düşük güven ({conf:.2%}) - daha fazla veri toplayın"
                )
            elif attr_score > 0.5 and contrib > 10:
                recommendations.append(
                    f"Aşama {phase_id}: Güçlü pozitif korelasyon ({attr_score:.2f}) - ağırlığı artırın"
                )
            elif attr_score < -0.5:
                recommendations.append(
                    f"Aşama {phase_id}: Negatif korelasyon ({attr_score:.2f}) - parametreleri gözden geçirin"
                )

        return recommendations

    def _create_neutral_report(self, trades: List) -> AttributionReport:
        """Yetersiz veri için tarafsız rapor oluştur."""
        return AttributionReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
            total_trades_analyzed=len(trades),
            winning_trades=sum(1 for t in trades if t.is_winning),
            losing_trades=sum(1 for t in trades if not t.is_winning),
            phase_attribution={i: 0.0 for i in range(1, 8)},
            phase_pnl_contribution={i: 0.0 for i in range(1, 8)},
            phase_confidence={i: 0.0 for i in range(1, 8)},
            total_pnl=sum(t.pnl for t in trades),
            win_rate=sum(1 for t in trades if t.is_winning) / max(len(trades), 1),
            avg_phase_signals={i: 0.0 for i in range(1, 8)},
            recommendations=["Atribüsyon analizi için yetersiz işlem"],
        )

    def save_report(self, report: AttributionReport, filepath: str) -> None:
        """Attribution raporunu YAML'a kaydet."""
        # Dizini oluştur (gerekirse)
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)

        report_dict = {
            "timestamp": report.timestamp,
            "summary": {
                "total_trades": report.total_trades_analyzed,
                "winning": report.winning_trades,
                "losing": report.losing_trades,
                "win_rate": f"{report.win_rate:.2%}",
                "total_pnl": round(report.total_pnl, 2),
            },
            "phase_attribution": {
                f"phase_{k}": round(v, 3) for k, v in report.phase_attribution.items()
            },
            "pnl_contribution_pct": {
                f"phase_{k}": round(v, 1) for k, v in report.phase_pnl_contribution.items()
            },
            "confidence": {
                f"phase_{k}": round(v, 2) for k, v in report.phase_confidence.items()
            },
            "average_signals": {
                f"phase_{k}": round(v, 3) for k, v in report.avg_phase_signals.items()
            },
            "recommendations": report.recommendations,
        }

        with open(filepath, 'w') as f:
            yaml.dump(report_dict, f, default_flow_style=False)

        logger.info(f"Attribution raporu kaydedildi: {filepath}")

    def load_report(self, filepath: str) -> Optional[AttributionReport]:
        """Attribution raporunu YAML'dan yükle."""
        try:
            with open(filepath, 'r') as f:
                data = yaml.safe_load(f)

            # AttributionReport'u YAML dict'ten reconstruct et
            return AttributionReport(
                timestamp=data.get("timestamp", ""),
                total_trades_analyzed=data.get("summary", {}).get("total_trades", 0),
                winning_trades=data.get("summary", {}).get("winning", 0),
                losing_trades=data.get("summary", {}).get("losing", 0),
                phase_attribution={
                    int(k.split("_")[1]): v
                    for k, v in data.get("phase_attribution", {}).items()
                },
                phase_pnl_contribution={
                    int(k.split("_")[1]): v
                    for k, v in data.get("pnl_contribution_pct", {}).items()
                },
                phase_confidence={
                    int(k.split("_")[1]): v
                    for k, v in data.get("confidence", {}).items()
                },
                total_pnl=data.get("summary", {}).get("total_pnl", 0.0),
                win_rate=0.0,
                avg_phase_signals={
                    int(k.split("_")[1]): v
                    for k, v in data.get("average_signals", {}).items()
                },
                recommendations=data.get("recommendations", []),
            )
        except Exception as e:
            logger.error(f"Attribution raporu yükleme hatası: {e}")
            return None
