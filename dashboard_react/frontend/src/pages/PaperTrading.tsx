/**
 * PaperTrading — Otonom paper trading sayfası.
 * Agent'ın OOS-doğrulanmış config'ini gerçek zamanlı, parasız test eder.
 * (Eski manuel buy/sell paneli kaldırıldı — legacy runtime varsayılan kapalı.)
 */
import React from 'react';
import { PaperAutoPanel } from '../components/paper/PaperAutoPanel';

const PaperTrading: React.FC = () => {
  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-slate-700/60 bg-slate-900 px-5 py-4">
        <h1 className="text-xl font-bold text-white">📝 Paper Trading</h1>
        <p className="mt-1 text-sm text-slate-400">
          Agent'ın seçtiği config gerçek zamanlı, $100.000 sanal sermaye ile test edilir —
          gerçek emir yok. Backtest'in canlıda gerçekten çalışıp çalışmadığını gösterir.
        </p>
      </div>

      <PaperAutoPanel />
    </div>
  );
};

export default PaperTrading;
