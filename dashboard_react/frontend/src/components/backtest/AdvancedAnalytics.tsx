import React from "react";

interface LeadLagEntry {
  corr: number;
  lag_days: number;
  leads: boolean;
}

interface AdvancedAnalyticsProps {
  leadLag: Record<string, LeadLagEntry>;
}

export const AdvancedAnalytics: React.FC<AdvancedAnalyticsProps> = ({ leadLag }) => {
  if (!leadLag || Object.keys(leadLag).length === 0) return null;

  return (
    <div className="rounded-xl border border-slate-700/50 bg-slate-900/80 p-5">
      <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-500 mb-3">
        📊 Advanced Analytics (Lead-Lag)
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-slate-500 border-b border-slate-700">
              <th className="py-2 text-left font-semibold">Asset</th>
              <th className="py-2 text-center font-semibold">Correlation</th>
              <th className="py-2 text-center font-semibold">Lag</th>
              <th className="py-2 text-center font-semibold">Direction</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(leadLag)
              .sort(([, a], [, b]) => Math.abs(b.corr) - Math.abs(a.corr))
              .map(([sym, d]) => (
                <tr key={sym} className="border-b border-slate-800/50">
                  <td className="py-2 font-semibold text-white">{sym}</td>
                  <td className="py-2 text-center">
                    <span
                      className={`font-mono ${
                        Math.abs(d.corr) > 0.5 ? "text-white" : "text-slate-400"
                      }`}
                    >
                      {d.corr.toFixed(2)}
                    </span>
                  </td>
                  <td className="py-2 text-center text-slate-300 font-mono">
                    {d.lag_days > 0 ? "+" : ""}
                    {d.lag_days}d
                  </td>
                  <td className="py-2 text-center">
                    <span
                      className={`px-2 py-0.5 rounded-full text-xs font-semibold ${
                        d.leads
                          ? "bg-emerald-500/20 text-emerald-300"
                          : "bg-amber-500/20 text-amber-300"
                      }`}
                    >
                      {d.leads ? "Leading" : "Lagging"}
                    </span>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
