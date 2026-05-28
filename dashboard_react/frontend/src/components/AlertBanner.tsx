import React from "react";
import { ConsensusData, DashboardData } from "../types";

interface AlertBannerProps {
  data: DashboardData;
}

export const AlertBanner: React.FC<AlertBannerProps> = ({ data }) => {
  const touche = data.metrics.touche.score;
  const news = data.metrics.news.score;
  const consensus = data.consensus.weighted_score;

  // Check for divergences
  const isBullishTechBearishNews = touche > 0.6 && news < 0.4;
  const isBearishTechBullishNews = touche < 0.4 && news > 0.6;
  const isHighRisk =
    data.metrics.sentinel.score > 0.7 && data.consensus.action === "BUY";
  const isLowConfidence = data.consensus.confidence < 0.5;

  if (!isBullishTechBearishNews && !isBearishTechBullishNews && !isHighRisk && !isLowConfidence) {
    return null; // No alerts
  }

  return (
    <div className="mb-6 space-y-3">
      {/* Bullish tech but bearish news */}
      {isBullishTechBearishNews && (
        <div className="rounded-lg border border-yellow-600 bg-yellow-900 bg-opacity-20 p-4 text-yellow-100">
          <div className="flex items-start gap-3">
            <span className="text-xl">⚠️</span>
            <div>
              <p className="font-semibold">UYUMSUZLUK: Boğa Tuzağı Riski</p>
              <p className="mt-1 text-sm">
                Touche {(touche * 100).toFixed(0)}% AL diyor ama News {(news * 100).toFixed(0)}% olumsuz!
                Bu bir boğa tuzağı olabilir. Fundamental ({(data.metrics.fundamental.score * 100).toFixed(0)}%) ile
                teyit et.
              </p>
              <p className="mt-2 text-xs text-yellow-200">
                💡 Tavsiye: Haber teyidini bekle veya pozisyonu küçült
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Bearish tech but bullish news */}
      {isBearishTechBullishNews && (
        <div className="rounded-lg border border-orange-600 bg-orange-900 bg-opacity-20 p-4 text-orange-100">
          <div className="flex items-start gap-3">
            <span className="text-xl">⚠️</span>
            <div>
              <p className="font-semibold">UYUMSUZLUK: Ayı Tuzağı Riski</p>
              <p className="mt-1 text-sm">
                Touche {(touche * 100).toFixed(0)}% SAT diyor ama News {(news * 100).toFixed(0)}% olumlu!
                Bu bir ayı tuzağı olabilir. Fundamental ({(data.metrics.fundamental.score * 100).toFixed(0)}%) ile
                teyit et.
              </p>
              <p className="mt-2 text-xs text-orange-200">
                💡 Tavsiye: İyi haberi teyidini bekle veya karşı pozisyon al
              </p>
            </div>
          </div>
        </div>
      )}

      {/* High risk buying */}
      {isHighRisk && (
        <div className="rounded-lg border border-red-600 bg-red-900 bg-opacity-20 p-4 text-red-100">
          <div className="flex items-start gap-3">
            <span className="text-xl">🚨</span>
            <div>
              <p className="font-semibold">YÜKSEK RİSK: Piyasa Gergin</p>
              <p className="mt-1 text-sm">
                Sentinel riski yüksek ({(data.metrics.sentinel.score * 100).toFixed(0)}%) ama sistem AL diyor!
                Piyasa çok gergin (VIX yüksek, Fear&Greed düşük). AL sinyalini göz ardı et.
              </p>
              <p className="mt-2 text-xs text-red-200">
                💡 Tavsiye: Piyasa sakinleşene kadar BEKLE, işlem yapma!
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Low confidence */}
      {isLowConfidence && (
        <div className="rounded-lg border border-gray-600 bg-gray-800 bg-opacity-50 p-4 text-gray-200">
          <div className="flex items-start gap-3">
            <span className="text-xl">ℹ️</span>
            <div>
              <p className="font-semibold">DÜŞÜK GÜVENİLİRLİK</p>
              <p className="mt-1 text-sm">
                Konsensus sinyali zayıf ({(data.consensus.confidence * 100).toFixed(0)}% confidence).
                Sistem kararsız. Büyük pozisyon almadan önce daha fazla kanıt bekle.
              </p>
              <p className="mt-2 text-xs text-gray-300">
                💡 Tavsiye: Daha yüksek confidence seviyesi gelmesini bekle
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
