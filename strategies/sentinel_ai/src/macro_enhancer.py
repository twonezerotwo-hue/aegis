import pandas as pd
import yfinance as yf
import requests
import os
import io


class MacroEnhancer:
    """Temel makro veriyi zenginlestirilmis girdiye donusturur."""

    def __init__(self):
        self.symbols = {
            "dxy": "DX-Y.NYB",
            "us10y": "^TNX",
            "vix": "^VIX",
            "brent": "BZ=F",
            "sp500": "^GSPC",
        }
        # Free-source URLs (expected CSV-like datasets with date + value columns).
        self.exchange_netflow_github_url = os.getenv(
            "EXCHANGE_NETFLOW_GITHUB_URL",
            "",
        )
        self.miner_reserves_github_url = os.getenv(
            "MINER_RESERVES_GITHUB_URL",
            "",
        )

    def fetch_crypto_flows(self) -> dict:
        """Kategori 2: Kripto likidite akis metriklerini getirir."""
        return {
            "btc_dominance_change_7d": self._get_btc_dominance_change_7d(),
            "stablecoin_supply_change_7d": self._get_stablecoin_supply_change_7d(),
            "exchange_netflow_btc": self._get_exchange_netflow_btc(),
            "miner_reserves_change_7d": self._get_miner_reserves_change_7d(),
        }

    def fetch_risk_sentiment(self) -> dict:
        """Kategori 3: Risk sentiment metriklerini getirir."""
        results = {
            "hyg_lqd_ratio": 0.0,
            "put_call_ratio": 0.0,
            "credit_spread_ig": 0.0,
            "global_liquidity_index": 0.0,
        }

        try:
            hyg = self._download_last_close("HYG", period="5d")
            lqd = self._download_last_close("LQD", period="5d")
            if lqd > 0:
                results["hyg_lqd_ratio"] = round(hyg / lqd, 4)
        except Exception as e:
            print(f"HYG/LQD hatasi: {e}")

        try:
            put_call = self._download_last_close("PCALL", period="5d")
            results["put_call_ratio"] = round(put_call, 2)
        except Exception:
            results["put_call_ratio"] = 1.0

        try:
            baa = self._get_fred_latest("BAA10Y")
            aaa = self._get_fred_latest("AAA10Y")
            if baa > 0 and aaa > 0:
                results["credit_spread_ig"] = round((baa - aaa) * 100.0, 2)
            else:
                baa_y = self._download_last_close("BAA10Y", period="5d")
                aaa_y = self._download_last_close("AAA10Y", period="5d")
                results["credit_spread_ig"] = round((baa_y - aaa_y) * 100.0, 2)
        except Exception:
            results["credit_spread_ig"] = 120.0

        try:
            walcl = self._get_fred_latest("WALCL")
            if walcl > 0:
                # FRED WALCL degeri milyon USD cinsindedir; trillion USD'ye normalize edilir.
                results["global_liquidity_index"] = round(walcl / 1_000_000.0, 4)
            else:
                # WALCL okunamazsa S&P500 level fallback kullan.
                results["global_liquidity_index"] = round(
                    self._download_last_close("^GSPC", period="5d"), 2
                )
        except Exception:
            try:
                results["global_liquidity_index"] = round(
                    self._download_last_close("^GSPC", period="5d"), 2
                )
            except Exception:
                results["global_liquidity_index"] = 0.0

        return results

    def fetch_correlations(self) -> dict:
        """Kategori 4: Korelasyon ve divergence metriklerini getirir."""
        results = {
            "btc_nasdaq_corr_30d": 0.0,
            "btc_dxy_corr_30d": 0.0,
            "divergence_flag": "none",
            "correlation_break_signal": False,
        }

        try:
            btc = self._download_close_series("BTC-USD", period="60d")
            nasdaq = self._download_close_series("^IXIC", period="60d")
            dxy = self._download_close_series("DX-Y.NYB", period="60d")

            btc_nasdaq_df = pd.concat([btc, nasdaq], axis=1, join="inner").dropna()
            btc_dxy_df = pd.concat([btc, dxy], axis=1, join="inner").dropna()

            if len(btc_nasdaq_df) >= 30:
                btc_nasdaq_corr = float(
                    btc_nasdaq_df.iloc[-30:, 0].corr(btc_nasdaq_df.iloc[-30:, 1])
                )
                results["btc_nasdaq_corr_30d"] = round(btc_nasdaq_corr, 4)
            else:
                btc_nasdaq_corr = 0.0

            if len(btc_dxy_df) >= 30:
                btc_dxy_corr = float(
                    btc_dxy_df.iloc[-30:, 0].corr(btc_dxy_df.iloc[-30:, 1])
                )
                results["btc_dxy_corr_30d"] = round(btc_dxy_corr, 4)
            else:
                btc_dxy_corr = 0.0

            if btc_nasdaq_corr < 0.3:
                results["divergence_flag"] = "macro_crypto_decouple"
            elif btc_dxy_corr > -0.1:
                results["divergence_flag"] = "macro_signal_weak"

            if len(btc_nasdaq_df) >= 37:
                old_corr = float(
                    btc_nasdaq_df.iloc[-37:-7, 0].corr(btc_nasdaq_df.iloc[-37:-7, 1])
                )
                if abs(btc_nasdaq_corr - old_corr) > 0.2:
                    results["correlation_break_signal"] = True
        except Exception as e:
            print(f"Korelasyon hatasi: {e}")

        return results

    def calculate_trends(self, base_data: dict) -> dict:
        """7 gunluk trend hesapla."""
        trends = {}

        dxy_history = self._get_historical("dxy", 7)
        trends["dxy_trend_7d"] = self._calculate_change(dxy_history)

        us10y_history = self._get_historical("us10y", 7)
        trends["us10y_trend_7d"] = self._calculate_change(us10y_history)

        vix_history = self._get_historical("vix", 7)
        trends["vix_trend_7d"] = self._calculate_change(vix_history)

        brent_history = self._get_historical("brent", 7)
        trends["brent_trend_7d"] = self._calculate_change(brent_history)

        trends["hg_trend_signal"] = self._get_copper_trend()
        trends["sp500_vs_ma200"] = self._get_sp500_vs_ma200()

        return trends

    def _get_historical(self, symbol: str, days: int) -> pd.Series:
        """Gecmis veriyi cek."""
        ticker = self.symbols.get(symbol, symbol)
        data = yf.download(ticker, period=f"{days + 2}d", interval="1d", progress=False)
        if "Close" not in data:
            return pd.Series(dtype="float64")
        close = data["Close"]
        if isinstance(close, pd.DataFrame):
            if close.empty:
                return pd.Series(dtype="float64")
            close = close.iloc[:, 0]
        return close.dropna()

    def _download_last_close(self, ticker: str, period: str = "5d") -> float:
        """Downloads latest close value from Yahoo Finance with MultiIndex-safe handling."""
        data = yf.download(ticker, period=period, interval="1d", progress=False)
        if "Close" not in data:
            raise ValueError(f"Close not found for {ticker}")
        close = data["Close"]
        if isinstance(close, pd.DataFrame):
            if close.empty:
                raise ValueError(f"Close frame empty for {ticker}")
            close = close.iloc[:, 0]
        close = close.dropna()
        if close.empty:
            raise ValueError(f"Close series empty for {ticker}")
        return float(close.iloc[-1])

    def _download_close_series(self, ticker: str, period: str = "60d") -> pd.Series:
        """Downloads close series from Yahoo Finance with MultiIndex-safe handling."""
        data = yf.download(ticker, period=period, interval="1d", progress=False)
        if "Close" not in data:
            return pd.Series(dtype="float64")
        close = data["Close"]
        if isinstance(close, pd.DataFrame):
            if close.empty:
                return pd.Series(dtype="float64")
            close = close.iloc[:, 0]
        return pd.to_numeric(close, errors="coerce").dropna()

    def _get_fred_latest(self, series_id: str) -> float:
        """Reads latest FRED value from CSV endpoint without API key."""
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
        response = requests.get(url, timeout=8)
        response.raise_for_status()
        df = pd.read_csv(io.StringIO(response.text))
        if df.empty or series_id not in df.columns:
            return 0.0
        values = pd.to_numeric(df[series_id], errors="coerce").dropna()
        if values.empty:
            return 0.0
        return float(values.iloc[-1])

    def _calculate_change(self, series: pd.Series) -> float:
        """7 gunluk yuzde degisim hesapla."""
        if len(series) < 2:
            return 0.0
        first = float(series.iloc[0])
        last = float(series.iloc[-1])
        if first == 0:
            return 0.0
        change = (last - first) / first
        return round(float(change), 4)

    def _get_copper_trend(self) -> str:
        """Bakir trend yonu (up/down/neutral)."""
        copper = yf.download("HG=F", period="8d", interval="1d", progress=False)
        if "Close" not in copper:
            return "neutral"
        close = copper["Close"]
        if isinstance(close, pd.DataFrame):
            if close.empty:
                return "neutral"
            close = close.iloc[:, 0]
        close = close.dropna()
        if len(close) < 2:
            return "neutral"
        prev = float(close.iloc[-2])
        curr = float(close.iloc[-1])
        if prev == 0:
            return "neutral"
        change = (curr - prev) / prev
        if change > 0.01:
            return "up"
        if change < -0.01:
            return "down"
        return "neutral"

    def _get_sp500_vs_ma200(self) -> float:
        """SP500'un 200 gunluk ortalamaya orani."""
        sp500 = yf.download("^GSPC", period="1y", interval="1d", progress=False)
        if "Close" not in sp500:
            return 1.0
        close = sp500["Close"]
        if isinstance(close, pd.DataFrame):
            if close.empty:
                return 1.0
            close = close.iloc[:, 0]
        close = close.dropna()
        if close.empty:
            return 1.0
        ma200 = close.rolling(200).mean().iloc[-1]
        current = close.iloc[-1]
        if pd.isna(ma200) or ma200 == 0:
            return 1.0
        return round(float(current / ma200), 4)

    def _get_btc_dominance_change_7d(self) -> float:
        """BTC dominance 7d degisimi (% puan)."""
        try:
            url = "https://api.coingecko.com/api/v3/global"
            now_resp = requests.get(url, timeout=8)
            now_resp.raise_for_status()
            current = float(
                now_resp.json().get("data", {}).get("market_cap_percentage", {}).get("btc", 0.0)
            )

            hist_url = "https://api.coingecko.com/api/v3/global/market_cap_chart"
            hist_params = {"vs_currency": "usd", "days": "8"}
            hist_resp = requests.get(hist_url, params=hist_params, timeout=8)
            if hist_resp.status_code == 200:
                series = hist_resp.json().get("market_cap_percentage", {}).get("btc", [])
                if len(series) >= 2:
                    start = float(series[0][1])
                    end = float(series[-1][1])
                    return round(end - start, 4)

            # Fallback if historical endpoint isn't available in plan/rate limit.
            return round(current - current, 4)
        except Exception:
            return 0.0

    def _coingecko_supply(self, coin_id: str) -> tuple[float, float]:
        """Returns (start_supply, end_supply) inferred from market cap / price over ~7d."""
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
        params = {"vs_currency": "usd", "days": "8", "interval": "daily"}
        response = requests.get(url, params=params, timeout=8)
        response.raise_for_status()
        payload = response.json()
        prices = payload.get("prices", [])
        market_caps = payload.get("market_caps", [])

        if len(prices) < 2 or len(market_caps) < 2:
            return 0.0, 0.0

        p0 = float(prices[0][1] or 0.0)
        p1 = float(prices[-1][1] or 0.0)
        m0 = float(market_caps[0][1] or 0.0)
        m1 = float(market_caps[-1][1] or 0.0)

        s0 = (m0 / p0) if p0 > 0 else 0.0
        s1 = (m1 / p1) if p1 > 0 else 0.0
        return s0, s1

    def _get_stablecoin_supply_change_7d(self) -> float:
        """USDT + USDC arz degisimi 7d (%)."""
        try:
            usdt_s0, usdt_s1 = self._coingecko_supply("tether")
            usdc_s0, usdc_s1 = self._coingecko_supply("usd-coin")
            start_total = usdt_s0 + usdc_s0
            end_total = usdt_s1 + usdc_s1
            if start_total <= 0:
                return 0.0
            return round(((end_total - start_total) / start_total) * 100.0, 4)
        except Exception:
            return 0.0

    def _github_series(self, dataset_url: str) -> pd.Series:
        """Reads a value series from a GitHub raw CSV/TSV endpoint."""
        if not dataset_url:
            return pd.Series(dtype="float64")
        try:
            response = requests.get(dataset_url, timeout=10)
            response.raise_for_status()
            text = response.text
            if not text.strip():
                return pd.Series(dtype="float64")

            # Try CSV then TSV fallback.
            try:
                df = pd.read_csv(io.StringIO(text))
            except Exception:
                df = pd.read_csv(io.StringIO(text), sep="\t")

            if df.empty:
                return pd.Series(dtype="float64")

            # Prefer standard value-like columns.
            for col in ["value", "netflow", "net_flow", "reserve", "close", "v"]:
                if col in df.columns:
                    return pd.to_numeric(df[col], errors="coerce").dropna()

            # Fallback: last numeric column.
            numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
            if numeric_cols:
                return pd.to_numeric(df[numeric_cols[-1]], errors="coerce").dropna()

            return pd.Series(dtype="float64")
        except Exception:
            return pd.Series(dtype="float64")

    def _get_exchange_netflow_btc(self) -> float:
        """Borsalara BTC net flow (negatif = cekiliyor), GitHub kaynagi."""
        series = self._github_series(self.exchange_netflow_github_url)
        if series.empty:
            return 0.0
        return round(float(series.iloc[-1]), 4)

    def _get_miner_reserves_change_7d(self) -> float:
        """Madenci rezerv degisimi 7d (%), GitHub kaynagi."""
        series = self._github_series(self.miner_reserves_github_url)
        if len(series) < 2:
            return 0.0

        tail = series.iloc[-8:] if len(series) >= 8 else series
        start = float(tail.iloc[0])
        end = float(tail.iloc[-1])
        if start <= 0:
            return 0.0

        return round(((end - start) / start) * 100.0, 4)

    def enhance(self, base_data: dict) -> dict:
        """Temel veriyi zenginlestir."""
        enhanced = base_data.copy()
        trends = self.calculate_trends(base_data)
        flows = self.fetch_crypto_flows()
        risk_sentiment = self.fetch_risk_sentiment()
        correlations = self.fetch_correlations()
        enhanced.update(trends)
        enhanced.update(flows)
        enhanced.update(risk_sentiment)
        enhanced.update(correlations)
        return enhanced
