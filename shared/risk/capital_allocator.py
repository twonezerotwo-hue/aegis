import numpy as np
import pandas as pd
from scipy.optimize import minimize
from pydantic import BaseModel, Field
from typing import Dict, Optional
from datetime import datetime, timedelta
import structlog

logger = structlog.get_logger(__name__)

class AllocationResult(BaseModel):
    allocations: Dict[str, float] = Field(..., description="Strateji başına sermaye dağılım yüzdesi")
    method_used: str = Field(..., description="Dağılım yöntemi: 'black_litterman' veya 'risk_parity'")
    target_volatility: Optional[float] = Field(None, description="Opsiyonel hedef volatilite")

class CapitalAllocator:
    """
    Sermaye dağıtım modülü:
    - Black-Litterman Modeli (Piyasa Görüşü + Prior Entegrasyonu)
    - Risk Parity (Alternatif eşit risk katkılı dağılım)
    - Volatility Targeting (Hedef volatilite doğrultusunda kaldıraç/ağırlık ayarı)
    - Haftalık Yeniden Hesaplama limiti (Caching mekanizması)
    """
    def __init__(self, target_volatility: Optional[float] = None, use_risk_parity: bool = False):
        self.target_volatility = target_volatility
        self.use_risk_parity = use_risk_parity
        
        self.last_recalc_time: Optional[datetime] = None
        self.cached_allocations: Optional[AllocationResult] = None

    def _risk_parity(self, covariance_matrix: np.ndarray) -> np.ndarray:
        """
        Risk Parity Algoritması: Toplam portföy riskine edilen payın her varlık 
        için eşitlenmesini hedefler.
        """
        num_assets = covariance_matrix.shape[0]
        
        def risk_budget_objective(weights, cov_matrix):
            port_var = weights.T @ cov_matrix @ weights
            # Her bir varlığın marjinal risk ve net risk katkısı (Risk Contribution)
            mrc = cov_matrix @ weights
            rc = weights * mrc
            
            # Eşit risk dağılımı (risk contribution / total) hedefleniyor
            target_rc = port_var / num_assets
            return np.sum(np.square(rc - target_rc))

        init_weights = np.ones(num_assets) / num_assets
        constraints = ({'type': 'eq', 'fun': lambda w: np.sum(w) - 1.0})
        bounds = tuple((0.0, 1.0) for _ in range(num_assets))
        
        result = minimize(
            risk_budget_objective,
            init_weights,
            args=(covariance_matrix,),
            method='SLSQP',
            bounds=bounds,
            constraints=constraints
        )
        return result.x

    def _black_litterman(self, prior_weights: pd.Series, covariance_matrix: pd.DataFrame, views: Dict[str, float], uncertainty: float = 0.05) -> np.ndarray:
        """
        Basitleştirilmiş Black-Litterman Implementasyonu.
        views: {'Strat_A': 0.15} şeklinde yıllık bazda net beklentiler.
        """
        tau = uncertainty
        tickers = prior_weights.index
        num_assets = len(tickers)
        
        Q_list = []
        P_list = []
        
        for idx, k in enumerate(tickers):
            if k in views:
                p_row = np.zeros(num_assets)
                p_row[idx] = 1.0
                P_list.append(p_row)
                Q_list.append(views[k])
                
        # Eğer girilmiş bir görüş (view) yoksa, prior ağırlıklarıyla devam et
        if len(Q_list) == 0:
            logger.info("no_views_provided", using_prior=True)
            return prior_weights.values 

        P = np.array(P_list)
        Q = np.array(Q_list)
        
        cov_vals = covariance_matrix.values
        risk_aversion = 2.5 # Varsayılan piyasa riskten kaçınma katsayısı
        prior_Pi = risk_aversion * cov_vals @ prior_weights.values
        
        # Omega (Matrix of view uncertainties)
        Omega = np.diag(np.diag(tau * P @ cov_vals @ P.T))
        # Singularity engellemek için eps ekle
        Omega += np.eye(Omega.shape[0]) * 1e-8
        
        tau_cov_inv = np.linalg.inv(tau * cov_vals)
        P_omega_inv = P.T @ np.linalg.inv(Omega)
        
        # BL Getiri Hesaplaması (BL Returns vector E(R))
        term1 = np.linalg.inv(tau_cov_inv + P_omega_inv @ P)
        term2 = tau_cov_inv @ prior_Pi + P_omega_inv @ Q
        BL_returns = term1 @ term2
        
        # Eldeki BL Getirilerine göre Max-Sharpe varyans maksimizasyonu
        def mv_objective(w):
            port_var = w.T @ cov_vals @ w
            port_ret = w.T @ BL_returns
            # Maksimize return and Minimize Variance => Minimize Negatif Return + Risk
            return -(port_ret - (risk_aversion / 2) * port_var)
            
        init_weights = np.ones(num_assets) / num_assets
        constraints = ({'type': 'eq', 'fun': lambda w: np.sum(w) - 1.0})
        # Short sallamadığımız varsayılmıştır (Only Long 0-1)
        bounds = tuple((0.0, 1.0) for _ in range(num_assets))
        
        res = minimize(mv_objective, init_weights, method='SLSQP', bounds=bounds, constraints=constraints)
        return res.x

    def _apply_volatility_targeting(self, weights: np.ndarray, covariance_matrix: np.ndarray) -> np.ndarray:
        """
        Belirlenen risk (volatilite) bütçesi için toplam ağırlıkları yeniden ölçekler (Scaling).
        Kaldıraçlı veya defansif hedefleri ayarlar.
        """
        if self.target_volatility is None:
            return weights
            
        port_vol = np.sqrt(weights.T @ covariance_matrix @ weights)
        if port_vol > 0:
            leverage = self.target_volatility / port_vol
            weights = weights * leverage
        return weights

    def calculate_allocation(self, returns_df: pd.DataFrame, market_views: Dict[str, float], override_cache: bool = False) -> AllocationResult:
        """
        Ana tetikleme metodu. 
        Tüm stratejilerin geçmiş(günlük) günlük varyasyon DF'ini alır ve oranları çıkarır.
        """
        now = datetime.now()
        
        # Haftalık yeniden hesaplama gereksinimi (7 günlük TTL önbelleği)
        if not override_cache and self.last_recalc_time is not None and self.cached_allocations is not None:
            if (now - self.last_recalc_time) < timedelta(days=7):
                logger.debug("capital_allocator_using_cache")
                return self.cached_allocations

        tickers = returns_df.columns
        # Yıllıklaştırılmış kovaryans matrisi
        covariance_matrix = returns_df.cov() * 252 
        
        # Matris dönüşümlerinde singularity engellemek üzere ufak epsilon tespiti
        cov_matrix_vals = covariance_matrix.values + np.eye(len(tickers)) * 1e-8
        covariance_matrix = pd.DataFrame(cov_matrix_vals, index=tickers, columns=tickers)

        # Temel modeli belirle
        if self.use_risk_parity:
            weights = self._risk_parity(covariance_matrix.values)
            method = "risk_parity"
        else:
            # Black-Litterman için basit eşit ağırlıklı pazar payı priors kabul edilir
            prior_weights = pd.Series(1.0 / len(tickers), index=tickers)
            weights = self._black_litterman(prior_weights, covariance_matrix, market_views)
            method = "black_litterman"
            
        # Volatility Targeting (varsa) uygula
        weights = self._apply_volatility_targeting(weights, covariance_matrix.values)
        
        # Çıktıyı Pydantic formatına uyarla
        allocations = {str(c): float(weights[i]) for i, c in enumerate(tickers)}
        
        res = AllocationResult(
            allocations=allocations,
            method_used=method,
            target_volatility=self.target_volatility
        )
        
        # Test modunda cache TTL baz alabilmek adına sakla
        self.cached_allocations = res
        self.last_recalc_time = now
        
        logger.info("allocation_calculated", method=method, target_volatility=self.target_volatility)
        return res
