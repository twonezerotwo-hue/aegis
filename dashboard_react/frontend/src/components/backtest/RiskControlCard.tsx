import React, { useState, useEffect } from "react";

interface RiskControlCardProps {
  onProfileChange?: (profile: string) => void;
  onCustomChange?: (kelly: number, sl: number, tp: number) => void;
}

const PRESETS: Record<string, [number, number, number]> = {
  conservative: [0.15, 1.5, 3],
  moderate: [0.25, 2, 4],
  aggressive: [0.35, 3, 6],
};

export const RiskControlCard: React.FC<RiskControlCardProps> = ({
  onProfileChange,
  onCustomChange,
}) => {
  const [profile, setProfile] = useState("moderate");
  const [kelly, setKelly] = useState(0.25);
  const [sl, setSl] = useState(2.0);
  const [tp, setTp] = useState(4.0);

  useEffect(() => {
    const [k, s, t] = PRESETS[profile] || PRESETS.moderate;
    setKelly(k);
    setSl(s);
    setTp(t);
    onProfileChange?.(profile);
    onCustomChange?.(k, s, t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profile]);

  const profileColors: Record<string, string> = {
    conservative: "bg-emerald-600",
    moderate: "bg-blue-600",
    aggressive: "bg-amber-600",
  };

  return (
    <div className="rounded-xl border border-slate-700/50 bg-slate-900/80 p-5">
      <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-500 mb-3">
        🛡️ Risk Profile & Controls
      </h3>
      <div className="flex gap-2 mb-4">
        {(["conservative", "moderate", "aggressive"] as const).map((p) => (
          <button
            key={p}
            onClick={() => setProfile(p)}
            className={`flex-1 py-2 text-xs font-semibold rounded-lg transition-all ${
              profile === p
                ? `${profileColors[p]} text-white ring-1 ring-white/20`
                : "bg-slate-800 text-slate-400 hover:bg-slate-700"
            }`}
          >
            {p.charAt(0).toUpperCase() + p.slice(1)}
          </button>
        ))}
      </div>
      <div className="grid grid-cols-3 gap-3 text-xs">
        <div>
          <label className="text-slate-500 block mb-1">Kelly Cap</label>
          <input
            type="number"
            step={0.05}
            min={0.05}
            max={0.5}
            value={kelly}
            onChange={(e) => {
              const v = +e.target.value;
              setKelly(v);
              onCustomChange?.(v, sl, tp);
            }}
            className="w-full bg-slate-800 border border-slate-600 rounded-lg px-2 py-1.5 text-white text-center font-mono focus:ring-1 focus:ring-blue-500 outline-none"
          />
        </div>
        <div>
          <label className="text-slate-500 block mb-1">Stop Loss %</label>
          <input
            type="number"
            step={0.5}
            min={0.5}
            max={10}
            value={sl}
            onChange={(e) => {
              const v = +e.target.value;
              setSl(v);
              onCustomChange?.(kelly, v, tp);
            }}
            className="w-full bg-slate-800 border border-slate-600 rounded-lg px-2 py-1.5 text-white text-center font-mono focus:ring-1 focus:ring-blue-500 outline-none"
          />
        </div>
        <div>
          <label className="text-slate-500 block mb-1">Take Profit %</label>
          <input
            type="number"
            step={0.5}
            min={1}
            max={20}
            value={tp}
            onChange={(e) => {
              const v = +e.target.value;
              setTp(v);
              onCustomChange?.(kelly, sl, v);
            }}
            className="w-full bg-slate-800 border border-slate-600 rounded-lg px-2 py-1.5 text-white text-center font-mono focus:ring-1 focus:ring-blue-500 outline-none"
          />
        </div>
      </div>
    </div>
  );
};
