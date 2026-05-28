from pydantic import BaseModel, Field


class ModuleAttributionStats(BaseModel):
    total_trades: int = Field(default=0, ge=0)
    win_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    attribution_score: float = 0.0
    role: str = "Neutral"


class ExitAttributionResponse(BaseModel):
    period: str
    modules: dict[str, ModuleAttributionStats]
