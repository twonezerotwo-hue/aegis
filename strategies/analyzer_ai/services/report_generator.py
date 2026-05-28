import logging
from datetime import datetime, timezone
from models.schemas import (
    AnalysisReport, ToucheAnalysis, FundamentalAnalysis,
    QuantumAnalysis, SentinelAnalysis, NewsAnalysis, ConsensusAnalysis
)

logger = logging.getLogger(__name__)

class ReportGenerator:
    @staticmethod
    def generate(
        symbol: str,
        timeframe: str,
        touche: ToucheAnalysis,
        fundamental: FundamentalAnalysis,
        quantum: QuantumAnalysis,
        sentinel: SentinelAnalysis,
        news: NewsAnalysis,
        consensus: ConsensusAnalysis
    ) -> AnalysisReport:
        """Generate complete analysis report"""

        # Determine final recommendation
        recommendation, reason, risk_notes, action_points = ReportGenerator._generate_recommendations(
            touche, fundamental, quantum, sentinel, news, consensus
        )

        report = AnalysisReport(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=datetime.now(timezone.utc),
            touche=touche,
            fundamental=fundamental,
            quantum=quantum,
            sentinel=sentinel,
            news=news,
            consensus=consensus,
            final_recommendation=recommendation,
            final_reason=reason,
            risk_notes=risk_notes,
            action_points=action_points
        )

        return report

    @staticmethod
    def _generate_recommendations(
        touche: ToucheAnalysis,
        fundamental: FundamentalAnalysis,
        quantum: QuantumAnalysis,
        sentinel: SentinelAnalysis,
        news: NewsAnalysis,
        consensus: ConsensusAnalysis
    ) -> tuple:
        """Generate final recommendation, reason, risk notes, and action points"""

        # Count LONG/SHORT votes
        long_votes = sum([
            1 for direction in [touche.direction, fundamental.direction, quantum.direction,
                               sentinel.direction, news.direction]
            if direction == "LONG"
        ])

        short_votes = sum([
            1 for direction in [touche.direction, fundamental.direction, quantum.direction,
                               sentinel.direction, news.direction]
            if direction == "SHORT"
        ])

        # Determine recommendation based on consensus
        if consensus.final_direction == "LONG" and long_votes >= 3:
            recommendation = "LONG (AL)"
            reason = f"Teknik ({touche.direction}), On-Chain ({fundamental.direction}), ve Likidite ({quantum.direction}) AL sesi verdi. {long_votes}/5 analiz LONG işaret ediyor."
        elif consensus.final_direction == "SHORT" and short_votes >= 3:
            recommendation = "SHORT (SAT)"
            reason = f"Teknik ({touche.direction}), On-Chain ({fundamental.direction}) SAT sesi verdi. {short_votes}/5 analiz SHORT işaret ediyor."
        else:
            recommendation = "HOLD (BEKLE)"
            reason = f"Analizler kararsız ({long_votes} LONG, {short_votes} SHORT). {consensus.weighted_score:.1f}% skor NÖTR bölgede."

        # Generate risk notes
        risk_notes = []

        if sentinel.fear_greed_index and sentinel.fear_greed_index > 70:
            risk_notes.append(f"⚠️ Fear & Greed {sentinel.fear_greed_index:.0f} (Açgözlülük) - Ani düşüş olabilir")

        if quantum.spread and quantum.spread > 0.1:
            risk_notes.append(f"⚠️ Yüksek Spread ({quantum.spread:.3f}%) - Slippage riski var")

        if sentiment_score := news.sentiment_score:
            if sentiment_score < 40:
                risk_notes.append(f"⚠️ Haberler Negatif ({sentiment_score:.0f}%) - İyileşme bekle")
            elif sentiment_score > 75:
                risk_notes.append(f"⚠️ Haberler Çok Pozitif ({sentiment_score:.0f}%) - Profit al zamanı")

        if not risk_notes:
            risk_notes.append("✅ Belirgin risk yok, pazar sağlıklı görünüyor")

        # Generate action points
        action_points = []

        if recommendation == "LONG (AL)":
            if touche.current_level:
                action_points.append(f"📍 AL: Fibonacci {touche.current_level} seviyesinde destek bul")
            action_points.append("🎯 TP1: Mevcut fiyatın %2 üstü, TP2: Fibonacci 0.618 üstü")
            action_points.append("🛑 SL: Fibonacci 0.382 altında")
            action_points.append("⏱️ Zaman Dilimi: Al → 4 saatlik kapanışı bekle, eğer destek kırılırsa çık")

        elif recommendation == "SHORT (SAT)":
            if touche.current_level:
                action_points.append(f"📍 SAT: Fibonacci {touche.current_level} seviyesinde direnç ara")
            action_points.append("🎯 TP1: Mevcut fiyatın %2 altı, TP2: Fibonacci 0.382 altı")
            action_points.append("🛑 SL: Fibonacci 0.618 üstünde")
            action_points.append("⏱️ Zaman Dilimi: Sat → 4 saatlik kapanışı bekle, eğer destek çıkarsa geri al")

        else:  # HOLD
            action_points.append("⏸️ Aksiyonsuz: Analyzerler net yön vermiyor, beklemeye devam et")
            action_points.append("👁️ Monitör: 1 saat sonra raporu yenile ve durumu kontrol et")
            if consensus.weighted_score > 0.55:
                action_points.append(f"💡 İpucu: Skor LONG'a yaklaşıyor ({consensus.weighted_score:.1f}%), yakında AL sinyali gelebilir")
            elif consensus.weighted_score < 0.45:
                action_points.append(f"💡 İpucu: Skor SHORT'a yaklaşıyor ({consensus.weighted_score:.1f}%), yakında SAT sinyali gelebilir")

        return recommendation, reason, risk_notes, action_points

    @staticmethod
    def format_text(report: AnalysisReport) -> str:
        """Format report as readable text"""

        newline = "\n"
        risk_notes_list = [f"  {note}" for note in report.risk_notes]
        action_points_list = [f"  {point}" for point in report.action_points]
        fibonacci_list = [f"{f.level} (${f.price:,.0f})" for f in report.touche.fibonacci_levels]
        news_list = [f"  * \"{n['title']}\" → {n['sentiment']}" for n in report.news.top_news[:3]]

        risk_notes_str = newline.join(risk_notes_list)
        action_points_str = newline.join(action_points_list)
        fibonacci_str = ", ".join(fibonacci_list)
        news_str = newline.join(news_list)

        text = f"""
=== AEGIS ANALİZ RAPORU ===
Sembol: {report.symbol}
Zaman Dilimi: {report.timeframe}
Tarih: {report.timestamp.strftime('%Y-%m-%d %H:%M:%S')}

📈 TOUCHE ANALİZİ (Teknik):
- Fibonacci seviyeleri: {fibonacci_str}
- Mevcut fiyat: {report.touche.current_level} seviyesinde (${report.touche.current_price:,.0f})
- RSI (14): {report.touche.rsi:.1f} ({report.touche.rsi_description})
- MACD: Histogram {report.touche.macd_status}
- StochRSI: {report.touche.stoch_rsi:.0f} {report.touche.stoch_rsi_status}
- Mum formasyonu: {report.touche.candle_pattern}
- Yön: {report.touche.direction} (Confidence: {report.touche.confidence*100:.1f}%)

🔗 FUNDAMENTAL ANALİZİ (On-Chain):
- MVRV Z-Score: {report.fundamental.mvrv_z_score:.2f} (normal bölge, aşırı değer yok)
- Puell Multiple: {report.fundamental.puell_multiple:.2f} (miner satışı {"yok" if report.fundamental.puell_multiple < 1 else "var"})
- Exchange Netflow: {report.fundamental.exchange_netflow:,.0f} BTC (son 24 saat, borsalardan {"çıkış" if report.fundamental.exchange_netflow > 0 else "giriş"} var)
- Stablecoin Supply: +{report.fundamental.stablecoin_supply_change:.1f}% (alım gücü {"artıyor" if report.fundamental.stablecoin_supply_change > 0 else "azalıyor"})
- Aktif Adresler: +{report.fundamental.active_addresses_change:.1f}% (ağ aktivitesi {"arttı" if report.fundamental.active_addresses_change > 0 else "azaldı"})
- Yön: {report.fundamental.direction} (Confidence: {report.fundamental.confidence*100:.1f}%)

💧 QUANTUM ANALİZİ (Likidite):
- Order Book Derinliği: ${report.quantum.order_book_depth:.0f}M ({report.quantum.liquidity_status})
- Spread: {report.quantum.spread:.3f}% ({"dar spread, işlem için uygun" if report.quantum.spread < 0.1 else "geniş spread, dikkatli ol"})
- Alış/Satış Dengesi: {report.quantum.buy_sell_ratio[0]*100:.0f}/{report.quantum.buy_sell_ratio[1]*100:.0f} ({"alış baskısı" if report.quantum.buy_sell_ratio[0] > 0.52 else "satış baskısı" if report.quantum.buy_sell_ratio[1] > 0.52 else "dengeli"})
- Yön: {report.quantum.direction} (Confidence: {report.quantum.confidence*100:.1f}%)

⚠️ SENTINEL ANALİZİ (Risk):
- VIX: {report.sentinel.vix:.1f} ({"düşük risk" if report.sentinel.vix < 20 else "yüksek risk"})
- DXY: {report.sentinel.dxy:.1f} ({"dolar zayıf, risk iştahı yüksek" if report.sentinel.dxy < 105 else "dolar güçlü"})
- Fear & Greed: {report.sentinel.fear_greed_index:.0f} ({"Açgözlülük bölgesi, dikkatli ol" if report.sentinel.fear_greed_index > 70 else "Korku bölgesi" if report.sentinel.fear_greed_index < 30 else "Nötr bölgesi"})
- Fed Faiz Oranı: {report.sentinel.fed_rate:.1f}%
- Yön: {report.sentinel.direction} (Confidence: {report.sentinel.confidence*100:.1f}%)

📰 NEWS ANALİZİ (Haberler):
- Son {report.timeframe} içinde {report.news.articles_analyzed} haber analiz edildi
- Önemli haberler:
{news_str}
- Net Sentiment: {report.news.sentiment_score:.1f}% ({"Pozitif" if report.news.sentiment_score > 60 else "Negatif" if report.news.sentiment_score < 40 else "Kararsız, hafif pozitif"})
- Yön: {report.news.direction} (Confidence: {report.news.confidence*100:.1f}%)

🤝 CONSENSUS KARARI:
- Touche: {report.consensus.touche_score:.1f}% ({report.touche.direction}) - ağırlık 35%
- Fundamental: {report.consensus.fundamental_score:.1f}% ({report.fundamental.direction}) - ağırlık 30%
- Quantum: {report.consensus.quantum_score:.1f}% ({report.quantum.direction}) - ağırlık 15%
- Sentinel: {report.consensus.sentinel_score:.1f}% ({report.sentinel.direction}) - ağırlık 15%
- News: {report.consensus.news_score:.1f}% ({report.news.direction}) - ağırlık 5%
- Toplam Skor: {report.consensus.weighted_score:.2f}% ({report.consensus.final_direction})
- Confidence: {report.consensus.confidence*100:.1f}%

🎯 NİHAİ ÖNERİ:
- Yön: {report.final_recommendation}
- Nedeni: {report.final_reason}

⚠️ Risk Notları:
{risk_notes_str}

📋 Aksiyon Noktaları:
{action_points_str}

=== RAPOR SONU ===
"""
        return text

