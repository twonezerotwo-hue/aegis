import React, { useState, useEffect } from 'react';
import { DataStatusBadge } from './ui/DataStatusBadge';
import { formatDataAge } from '../utils/dataFreshness';

interface AnalysisData {
  success: boolean;
  timestamp?: string | null;
  last_updated?: string | null;
  source?: string;
  fallback_used?: boolean;
  data_status?: string;
  report?: {
    symbol: string;
    timeframe: string;
    timestamp: string | null;
    consensus: {
      weighted_score: number;
      final_direction: string;
      confidence: number;
    };
    final_recommendation: string;
    final_reason: string;
    risk_notes: string[];
    action_points: string[];
  };
  error?: string;
}

interface AIAnalysisCardProps {
  symbol?: string;
  timeframe?: string;
}

const AIAnalysisCard: React.FC<AIAnalysisCardProps> = ({ symbol = 'BTC/USDT', timeframe = '4h' }) => {
  const [loading, setLoading] = useState(false);
  const [analysis, setAnalysis] = useState<AnalysisData | null>(null);
  const [lastSuccessfulAnalysis, setLastSuccessfulAnalysis] = useState<AnalysisData | null>(null);
  const [error, setError] = useState<string | null>(null);

  const getAnalysisTimestamp = (payload: AnalysisData | null): string | null =>
    payload?.report?.timestamp ?? payload?.last_updated ?? payload?.timestamp ?? null;

  const fetchAnalysis = async () => {
    setLoading(true);
    setError(null);
    setAnalysis(null);

    try {
      // ✅ Backend API'yi çağır (backend analyzer'ı çağıracak)
      const backendUrl = import.meta.env.VITE_API_URL || "http://localhost:8502";

      const response = await fetch(
        `${backendUrl}/api/analysis?symbol=${symbol}&timeframe=${timeframe}`,
        {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
          },
        }
      );

      if (!response.ok) {
        throw new Error(`API Error: ${response.statusText}`);
      }

      const data = await response.json();
      setAnalysis(data);
      if (data?.success && data?.report) {
        setLastSuccessfulAnalysis(data);
      }
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Failed to fetch analysis';
      setAnalysis(null);
      setError(errorMsg);
      console.error('Analysis error:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAnalysis();
  }, [symbol, timeframe]);

  const getRecommendationColor = (direction: string) => {
    switch (direction) {
      case 'LONG':
        return 'text-green-500';
      case 'SHORT':
        return 'text-red-500';
      case 'HOLD':
        return 'text-yellow-500';
      default:
        return 'text-gray-500';
    }
  };

  const getScoreColor = (score: number) => {
    if (score > 65) return 'text-green-500';
    if (score < 35) return 'text-red-500';
    return 'text-yellow-500';
  };

  return (
    <div className="bg-white dark:bg-gray-900 rounded-lg shadow-lg p-6 border border-gray-200 dark:border-gray-700">
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-bold text-gray-800 dark:text-white">
          🤖 AEGIS AI Analysis
        </h2>
        <button
          onClick={fetchAnalysis}
          disabled={loading}
          className="px-4 py-2 bg-blue-500 hover:bg-blue-600 disabled:bg-gray-400 text-white rounded-lg transition"
        >
          {loading ? '⏳ Loading...' : '🔄 Refresh'}
        </button>
      </div>

      {error && (
        <div className="mb-4 p-4 bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-200 rounded-lg">
          ⚠️ Error: {error}
          <div className="mt-3">
            <p className="text-xs text-red-200">
              Last successful update: {getAnalysisTimestamp(lastSuccessfulAnalysis) ? formatDataAge(getAnalysisTimestamp(lastSuccessfulAnalysis)) : 'none recorded'}
            </p>
            <p className="mt-1 text-xs text-red-200">
              Source: {lastSuccessfulAnalysis?.source ?? 'unknown'}
            </p>
          </div>
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-8">
          <div className="spinner animate-spin h-8 w-8 border border-blue-500 rounded-full border-t-transparent"></div>
          <span className="ml-2 text-gray-600 dark:text-gray-400">Analyzing all AI modules...</span>
        </div>
      ) : analysis && analysis.success && analysis.report ? (
        <div className="space-y-6">
          <DataStatusBadge
            data={analysis}
            source={analysis.source ?? "analyzer_bridge"}
            timestamp={getAnalysisTimestamp(analysis)}
          />

          {/* Header Info */}
          <div className="grid grid-cols-3 gap-4 pb-4 border-b border-gray-200 dark:border-gray-700">
            <div>
              <p className="text-sm text-gray-600 dark:text-gray-400">Symbol</p>
              <p className="text-lg font-semibold text-gray-800 dark:text-white">{analysis.report.symbol}</p>
            </div>
            <div>
              <p className="text-sm text-gray-600 dark:text-gray-400">Timeframe</p>
              <p className="text-lg font-semibold text-gray-800 dark:text-white">{analysis.report.timeframe}</p>
            </div>
            <div>
              <p className="text-sm text-gray-600 dark:text-gray-400">Updated</p>
              <p className="text-lg font-semibold text-gray-800 dark:text-white">
                {analysis.report.timestamp ? new Date(analysis.report.timestamp).toLocaleTimeString() : 'timestamp unavailable'}
              </p>
            </div>
          </div>

          {/* Consensus Score */}
          <div className="bg-gray-50 dark:bg-gray-800 p-4 rounded-lg">
            <h3 className="font-semibold text-gray-800 dark:text-white mb-3">📊 Consensus Analysis</h3>
            <div className="flex items-center justify-between">
              <div>
                <p className={`text-4xl font-bold ${getScoreColor(analysis.report.consensus.weighted_score)}`}>
                  {analysis.report.consensus.weighted_score.toFixed(2)}%
                </p>
                <p className="text-sm text-gray-600 dark:text-gray-400">Weighted Score</p>
              </div>
              <div className="text-right">
                <p className={`text-3xl font-bold ${getRecommendationColor(analysis.report.consensus.final_direction)}`}>
                  {analysis.report.consensus.final_direction}
                </p>
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  Confidence: {(analysis.report.consensus.confidence * 100).toFixed(1)}%
                </p>
              </div>
            </div>

            {/* Progress Bar */}
            <div className="mt-4">
              <div className="w-full bg-gray-300 dark:bg-gray-700 rounded-full h-2">
                <div
                  className={`h-2 rounded-full transition-all ${
                    analysis.report.consensus.weighted_score > 65
                      ? 'bg-green-500'
                      : analysis.report.consensus.weighted_score < 35
                        ? 'bg-red-500'
                        : 'bg-yellow-500'
                  }`}
                  style={{ width: `${Math.min(analysis.report.consensus.weighted_score, 100)}%` }}
                ></div>
              </div>
            </div>
          </div>

          {/* Final Recommendation */}
          <div className="bg-blue-50 dark:bg-blue-900 p-4 rounded-lg border-l-4 border-blue-500">
            <h3 className="font-semibold text-gray-800 dark:text-white mb-2">🎯 Final Recommendation</h3>
            <p className={`text-lg font-bold mb-2 ${getRecommendationColor(analysis.report.final_recommendation.split(' ')[0])}`}>
              {analysis.report.final_recommendation}
            </p>
            <p className="text-gray-700 dark:text-gray-300">{analysis.report.final_reason}</p>
          </div>

          {/* Risk Notes */}
          {analysis.report.risk_notes.length > 0 && (
            <div className="bg-amber-50 dark:bg-amber-900 p-4 rounded-lg">
              <h3 className="font-semibold text-gray-800 dark:text-white mb-3">⚠️ Risk Notes</h3>
              <ul className="space-y-2">
                {analysis.report.risk_notes.map((note, idx) => (
                  <li key={idx} className="text-sm text-gray-700 dark:text-gray-300">
                    {note}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Action Points */}
          {analysis.report.action_points.length > 0 && (
            <div className="bg-green-50 dark:bg-green-900 p-4 rounded-lg">
              <h3 className="font-semibold text-gray-800 dark:text-white mb-3">📋 Action Points</h3>
              <ul className="space-y-2">
                {analysis.report.action_points.map((point, idx) => (
                  <li key={idx} className="text-sm text-gray-700 dark:text-gray-300">
                    {point}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      ) : (
        <div className="text-center py-8">
          <p className="text-gray-600 dark:text-gray-400">No analysis available yet</p>
        </div>
      )}
    </div>
  );
};

export default AIAnalysisCard;
