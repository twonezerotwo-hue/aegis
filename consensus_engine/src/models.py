"""
AEGIS Holding — Consensus Engine: Veri Modelleri

Touche AI, Fundamental AI ve diğer sinyal kaynakları için
standart Pydantic modelleri.
"""
from typing import Any, Dict, Optional
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field


# ─── Touche AI Signal ─────────────────────────────────────────────────────────

class ToucheSignal(BaseModel):
    """Touche AI'dan gelen Al/Sat/Bekle sinyali."""
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    symbol: str
    timeframe: str
    signal: str                          # AL, SAT, BEKLE
    eqs: float = Field(..., ge=0, le=100)  # 0-100
    score: float = Field(..., ge=0, le=100)
    reason: str
    phase_results: Dict[str, Any]       # Her fazdan sonuç
    metadata: Dict[str, Any] = {}
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    @property
    def is_bullish(self) -> bool:
        return self.signal == "AL"
    
    @property
    def is_bearish(self) -> bool:
        return self.signal == "SAT"
    
    @property
    def confidence(self) -> float:
        """EQS'den güven skoru (0-1)."""
        return self.eqs / 100.0


# ─── Fundamental AI Signal ───────────────────────────────────────────────────

class FundamentalSignal(BaseModel):
    """Fundamental AI'dan gelen bulish/bearish/neutral sinyali."""
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    symbol: str
    signal: str                          # BULLISH, BEARISH, NEUTRAL
    score: float = Field(..., ge=0, le=100)  # 0-100
    factors: Dict[str, float]           # Temel faktörler (P/E, büyüme vs.)
    reason: str
    metadata: Dict[str, Any] = {}
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    @property
    def confidence(self) -> float:
        """Score'dan güven skoru (0-1)."""
        return self.score / 100.0


# ─── Consensus Decision ──────────────────────────────────────────────────────

class ConsensusDecision(BaseModel):
    """Consensus Engine'in nihai kararı."""
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    symbol: str
    action: str                         # AL, SAT, BEKLE
    confidence: float = Field(..., ge=0, le=1)  # 0-1
    position_size: float = Field(..., ge=0, le=1)  # 0-1 (% of portfolio)
    
    # Kaynaklar
    touche_signal: ToucheSignal
    fundamental_signal: FundamentalSignal
    
    # Hesaplanan multiplilers
    fundamental_multiplier: float       # 0.3 - 1.2
    position_multiplier: float          # Position sizing
    kelly_fraction: float               # Kelly criterion share
    
    # Detaylı mantık
    alignment_score: float = Field(..., ge=0, le=1)  # Sinyal uyumu
    contradiction_score: float = Field(..., ge=0, le=1)  # Sinyal çelişkisi
    aggregate_score: float = Field(..., ge=0, le=1)  # Nihai skor
    
    # Risk bilgileri
    risk_level: str                     # LOW, MEDIUM, HIGH
    stop_loss_percent: float            # %
    take_profit_target: float           # Multiplier (e.g., 1.5x)
    
    # Metadata
    reasoning: str                      # Nihai kararın açıklaması
    metadata: Dict[str, Any] = {}
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ─── Portfolio Position ──────────────────────────────────────────────────────

class PortfolioPosition(BaseModel):
    """Portfolio'da bir pozisyon."""
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    symbol: str
    quantity: float
    entry_price: float
    current_price: float
    stop_loss: float
    take_profit: float
    position_size: float               # % of portfolio
    confidence: float = Field(..., ge=0, le=1)
    
    @property
    def unrealized_pnl(self) -> float:
        """Gerçekleşmemiş kar/zarar."""
        return (self.current_price - self.entry_price) * self.quantity
    
    @property
    def unrealized_pnl_percent(self) -> float:
        """Gerçekleşmemiş kar/zarar %."""
        if self.entry_price == 0:
            return 0.0
        return (self.current_price - self.entry_price) / self.entry_price


# ─── Risk Metrics ───────────────────────────────────────────────────────────

class RiskMetrics(BaseModel):
    """Sistem risk metrikleri."""
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    portfolio_value: float
    cash_reserve: float
    total_exposure: float              # Toplam pozisyon değeri
    max_single_position: float         # En büyük pozisyon
    portfolio_volatility: float        # Beklenen volatilite
    sharpe_ratio: float                # Risk-adjusted return
    max_drawdown: float                # Maksimum düşüş
    correlation_with_benchmark: float  # Benchmark korelasyonu
    
    @property
    def leverage(self) -> float:
        """Kaldıraç oranı."""
        if self.portfolio_value == 0:
            return 0.0
        return self.total_exposure / self.portfolio_value
    
    @property
    def cash_percent(self) -> float:
        """Nakit yüzdesi."""
        if self.portfolio_value == 0:
            return 0.0
        return self.cash_reserve / self.portfolio_value


# ─── Consensus Config ───────────────────────────────────────────────────────

class ConsensusConfig(BaseModel):
    """Consensus Engine konfigürasyonu."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    # Ağırlıklar (eski 2-way weighting için - YAML'dan yüklenir)
    touche_weight: float = 0.50
    fundamental_weight: float = 0.35
    news_weight: float = 0.15

    # Eşikler
    eqs_weak_signal: float = 40.0
    eqs_strong_signal: float = 60.0

    # Multipliers
    fundamental_conservative: float = 30.0
    fundamental_conservative_mult: float = 0.3
    fundamental_bullish: float = 70.0
    fundamental_bullish_mult: float = 1.2

    # Güven
    min_confidence: float = 0.40
    alignment_bonus: float = 0.15
    contradiction_penalty: float = 0.30

    # Kelly & Position Sizing
    kelly_fraction: float = 0.25
    kelly_safety_margin: float = 0.5
    max_position_size: float = 0.15


# ─── Aggregation Result ─────────────────────────────────────────────────────

class AggregationResult(BaseModel):
    """Sinyal birleştirme sonucu."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    symbol: str
    touche_signal: ToucheSignal
    fundamental_signal: FundamentalSignal
    news_signal: Optional[Dict[str, Any]] = None  # News AI Limited sinyali

    # Raw scores
    touche_score: float                # 0-1
    fundamental_score: float           # 0-1
    news_score: float = 0.0            # -1 to 1 (0 = neutral)

    # Alignment
    signals_aligned: bool              # Aynı yönde mi?
    alignment_degree: float = Field(..., ge=0, le=1)  # Uyum derecesi

    # Aggregated
    aggregate_bullish_score: float = Field(..., ge=0, le=1)
    aggregate_bearish_score: float = Field(..., ge=0, le=1)
    aggregate_neutral_score: float = Field(..., ge=0, le=1)

    # Decision
    recommended_action: str            # AL, SAT, BEKLE
    confidence: float = Field(..., ge=0, le=1)

    # Reasoning
    summary: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
