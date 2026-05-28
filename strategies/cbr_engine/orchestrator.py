"""
AEGIS CBR Engine - Orchestrator
Tüm 6 fazı koordine eden master orchestration engine
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple
from datetime import datetime
import logging

try:
    from macro_enhancer import CBRMacroEnhancer
except Exception:
    CBRMacroEnhancer = None

logger = logging.getLogger(__name__)


class CBROrchestrator:
    """
    Case-Based Reasoning Orchestrator

    FAZ 1 → FAZ 2 → FAZ 3 → FAZ 4 → FAZ 5 → FAZ 6
    Pipeline: Fingerprint → Reduce → Search → Decide → Learn → Monitor
    """

    def __init__(
        self,
        fingerprint_extractor,
        dimensionality_reducer,
        similarity_engine,
        probabilistic_maker,
        auto_labeler,
        live_monitor,
        slippage_simulator,
    ):
        """
        Initialize orchestrator with all 6 phase components.

        Args:
            fingerprint_extractor: FAZ 1 - Feature extraction
            dimensionality_reducer: FAZ 2 - Dimensionality reduction
            similarity_engine: FAZ 3 - Similarity search
            probabilistic_maker: FAZ 4 - Decision making
            auto_labeler: FAZ 5 - Continuous learning
            live_monitor: FAZ 6 - Live monitoring
            slippage_simulator: FAZ 6 - Slippage simulation
        """
        self.extractor = fingerprint_extractor
        self.reducer = dimensionality_reducer
        self.similarity = similarity_engine
        self.decision_maker = probabilistic_maker
        self.labeler = auto_labeler
        self.monitor = live_monitor
        self.slippage = slippage_simulator
        self.macro_enhancer = CBRMacroEnhancer() if CBRMacroEnhancer else None

        self.pipeline_log = []
        logger.info("CBROrchestrator initialized with all 6 phases")

    @staticmethod
    def _payload_to_frame(payload: Dict) -> pd.DataFrame:
        if isinstance(payload, dict) and payload:
            if all(isinstance(value, list) for value in payload.values()):
                frame = pd.DataFrame(payload)
            else:
                frame = pd.DataFrame([payload])
        else:
            frame = pd.DataFrame(payload)

        if 'timestamp' in frame.columns:
            frame['timestamp'] = pd.to_datetime(frame['timestamp'])
            frame.set_index('timestamp', inplace=True)

        return frame

    def _build_macro_frame(self, market_data: Dict) -> pd.DataFrame:
        base_macro = self._payload_to_frame(market_data.get('macro', {}))

        if not self.macro_enhancer:
            return base_macro

        enriched_macro = self.macro_enhancer.enrich(market_data)
        if base_macro.empty:
            return self._payload_to_frame(enriched_macro)

        for key, value in enriched_macro.items():
            if isinstance(value, dict) or key == 'timestamp':
                continue

            if isinstance(value, list) and len(value) == len(base_macro.index):
                base_macro[key] = value
            elif not isinstance(value, list):
                base_macro[key] = value

        return base_macro

    def process_market_data(self, market_data: Dict) -> Tuple[Dict, Dict]:
        """
        Process market data through complete pipeline.

        Args:
            market_data: Current market data (price, indicators, etc.)

        Returns:
            (decision, pipeline_metrics)
        """
        start_time = datetime.now()
        metrics = {
            'start_time': start_time,
            'phases': {}
        }

        try:
            # ============ FAZ 1: FINGERPRINT ==============
            logger.info("FAZ 1: Extracting fingerprint...")
            faz1_start = datetime.now()

            # Convert payloads to point-in-time aligned DataFrames for extractor.
            ohlcv_df = self._payload_to_frame(market_data.get('ohlcv', {}))
            macro_df = self._build_macro_frame(market_data)
            onchain_df = self._payload_to_frame(market_data.get('on_chain', {}))

            fingerprint = self.extractor.extract(ohlcv_df, macro_df, onchain_df, idx=max(len(ohlcv_df) - 1, 0))
            fingerprint_dict = fingerprint.to_dict() if hasattr(fingerprint, 'to_dict') else fingerprint

            metrics['phases']['faz1_fingerprint'] = {
                'duration_ms': (datetime.now() - faz1_start).total_seconds() * 1000,
                'features_count': len(fingerprint_dict) if isinstance(fingerprint_dict, dict) else 0,
                'cat5_enabled': bool(self.macro_enhancer),
                'cat6_enabled': bool(self.macro_enhancer),
                'cat7_enabled': bool(self.macro_enhancer),
                'status': 'SUCCESS' if fingerprint else 'FAILED'
            }

            # ============ FAZ 2: DIMENSIONALITY REDUCTION ==============
            logger.info("FAZ 2: Reducing dimensionality...")
            faz2_start = datetime.now()

            # Convert fingerprint to dict if it's a Fingerprint object
            if hasattr(fingerprint, 'to_dict'):
                fingerprint_dict = fingerprint.to_dict()
            elif hasattr(fingerprint, '__dict__'):
                fingerprint_dict = fingerprint.__dict__
            else:
                fingerprint_dict = fingerprint

            fingerprint_df = pd.DataFrame([fingerprint_dict])
            embedding = self.reducer.transform(fingerprint_df)

            metrics['phases']['faz2_reduce'] = {
                'duration_ms': (datetime.now() - faz2_start).total_seconds() * 1000,
                'original_dims': len(fingerprint_dict) if isinstance(fingerprint_dict, dict) else len(fingerprint_dict.__dict__),
                'reduced_dims': embedding.shape[1] if embedding is not None else 0,
                'status': 'SUCCESS'
            }

            # ============ FAZ 3: SIMILARITY SEARCH ==============
            logger.info("FAZ 3: Searching similar cases...")
            faz3_start = datetime.now()

            embedding_vector = embedding.iloc[0].values
            similar_cases = self.similarity.search(
                embedding_vector,
                k=50,
                market_type=market_data.get('market_type')
            )

            metrics['phases']['faz3_search'] = {
                'duration_ms': (datetime.now() - faz3_start).total_seconds() * 1000,
                'cases_found': len(similar_cases),
                'avg_similarity': np.mean([c.similarity_score for c in similar_cases]) if similar_cases else 0,
                'status': 'SUCCESS'
            }

            # ============ FAZ 4: PROBABILISTIC DECISION ==============
            logger.info("FAZ 4: Making trading decision...")
            faz4_start = datetime.now()

            case_stats = self._calculate_case_statistics(similar_cases)
            decision = self.decision_maker.make_decision(
                current_price=market_data.get('price', 0),
                fingerprint=fingerprint,
                similar_cases_stats=case_stats,
                market_type=market_data.get('market_type', 'DIP')
            )

            metrics['phases']['faz4_decide'] = {
                'duration_ms': (datetime.now() - faz4_start).total_seconds() * 1000,
                'action': decision.action,
                'confidence': float(decision.confidence),
                'position_size': float(decision.position_size),
                'status': 'SUCCESS'
            }

            # ============ FAZ 5: CONTINUOUS LEARNING (async) ==============
            logger.info("FAZ 5: Logging for continuous learning...")
            faz5_start = datetime.now()

            # Label the trade for continuous learning
            self.labeler.label_trade(
                trade_id=f"TRADE_{start_time.strftime('%Y%m%d%H%M%S')}",
                entry_price=market_data.get('price', 0),
                confidence_score=decision.confidence,
                position_size=decision.position_size,
                forward_return=0.0,  # Will be updated later
                entry_time=start_time,
            )

            metrics['phases']['faz5_learn'] = {
                'duration_ms': (datetime.now() - faz5_start).total_seconds() * 1000,
                'trades_logged': len(self.labeler.trades_log),
                'status': 'SUCCESS'
            }

            # ============ FAZ 6: LIVE MONITORING ==============
            logger.info("FAZ 6: Monitoring trade...")
            faz6_start = datetime.now()

            # Simulate execution with slippage
            if decision.action != 'SKIP':
                execution = self.slippage.execute_order(
                    side='BUY' if decision.action == 'LONG' else 'SELL',
                    quantity=decision.position_size
                )

                metrics['phases']['faz6_monitor'] = {
                    'duration_ms': (datetime.now() - faz6_start).total_seconds() * 1000,
                    'execution_price': float(execution.average_fill_price),
                    'slippage_bps': float(execution.slippage_bps),
                    'status': 'SUCCESS'
                }
            else:
                metrics['phases']['faz6_monitor'] = {
                    'duration_ms': (datetime.now() - faz6_start).total_seconds() * 1000,
                    'status': 'SKIPPED'
                }

            # Total pipeline time
            metrics['total_duration_ms'] = (datetime.now() - start_time).total_seconds() * 1000
            metrics['status'] = 'SUCCESS'

            # Log pipeline
            self.pipeline_log.append({
                'timestamp': start_time,
                'market_type': market_data.get('market_type'),
                'decision': decision.action,
                'confidence': decision.confidence,
                'similar_cases': len(similar_cases),
                'pipeline_ms': metrics['total_duration_ms']
            })

            logger.info(
                f"Pipeline complete: {decision.action} "
                f"(confidence: {decision.confidence:.2f}, "
                f"time: {metrics['total_duration_ms']:.1f}ms)"
            )

            return {
                'action': decision.action,
                'confidence': decision.confidence,
                'position_size': decision.position_size,
                'entry_price': decision.entry_price,
                'stop_loss': decision.stop_loss,
                'take_profit': decision.take_profit,
                'similar_cases': len(similar_cases),
            }, metrics

        except Exception as e:
            logger.error(f"Pipeline error: {e}")
            metrics['status'] = 'ERROR'
            metrics['error'] = str(e)
            return None, metrics

    def _calculate_case_statistics(self, cases: List) -> Dict:
        """Calculate statistics from similar cases"""
        if not cases:
            return {
                'sample_count': 0,
                'mean_similarity': 0.0,
                'ensemble_return': 0.0,
                'agreement': 0.0,
            }

        similarities = [c.similarity_score for c in cases]
        returns = [c.forward_return_24h for c in cases if c.forward_return_24h]

        return {
            'sample_count': len(cases),
            'mean_similarity': float(np.mean(similarities)),
            'ensemble_return': float(np.mean(returns)) if returns else 0.0,
            'agreement': float(np.mean(similarities)),
        }

    def get_pipeline_statistics(self) -> Dict:
        """Get pipeline performance statistics"""
        if not self.pipeline_log:
            return {}

        df = pd.DataFrame(self.pipeline_log)

        return {
            'total_pipelines': len(self.pipeline_log),
            'avg_time_ms': float(df['pipeline_ms'].mean()),
            'max_time_ms': float(df['pipeline_ms'].max()),
            'min_time_ms': float(df['pipeline_ms'].min()),
            'signals_generated': int(df['decision'].ne('SKIP').sum()),
            'avg_confidence': float(df['confidence'].mean()),
            'avg_similar_cases': float(df['similar_cases'].mean()),
        }

    def get_performance_report(self) -> str:
        """Generate performance report"""
        stats = self.get_pipeline_statistics()
        labeler_stats = self.labeler.calculate_statistics()
        monitor_summary = self.monitor.get_summary()

        report = f"""
╔════════════════════════════════════════════════════════════╗
║           AEGIS CBR ENGINE - FULL PIPELINE REPORT          ║
╚════════════════════════════════════════════════════════════╝

📊 PIPELINE PERFORMANCE:
  Total Processed:    {stats.get('total_pipelines', 0)} market updates
  Avg Processing:     {stats.get('avg_time_ms', 0):.1f}ms
  Signals Generated:  {stats.get('signals_generated', 0)}
  Avg Confidence:     {stats.get('avg_confidence', 0):.2f}
  Avg Similar Cases:  {stats.get('avg_similar_cases', 0):.1f}

💰 TRADING PERFORMANCE:
  Capital:            ${monitor_summary.get('current_capital', 0):,.2f}
  Total Return:       {monitor_summary.get('total_return', 0):+.2%}
  Trades:             {monitor_summary.get('trade_count', 0)}
  Win Rate:           {monitor_summary.get('win_rate', 0):.1%}
  Sharpe Ratio:       {monitor_summary.get('sharpe_ratio', 0):.2f}

📉 RISK METRICS:
  Current Drawdown:   {monitor_summary.get('current_drawdown', 0):.2%}
  Max Drawdown:       {monitor_summary.get('max_drawdown', 0):.2%}
  Consecutive Losses: {monitor_summary.get('consecutive_losses', 0)}

✅ FAZ 1-6: Tümü Operasyonel
"""
        return report

    def export_logs(self, filepath: str):
        """Export pipeline logs to file"""
        df = pd.DataFrame(self.pipeline_log)
        df.to_csv(filepath, index=False)
        logger.info(f"Pipeline logs exported to {filepath}")
