import React, { useState, useRef, useEffect } from "react";

export interface SymbolOption {
  symbol: string;
  label:  string;
}

interface SymbolSelectorProps {
  currentSymbol:  string;
  onSymbolChange: (symbol: string) => void;
  /** Opsiyonel liste — verilmezse varsayılan AEGIS sembolleri kullanılır */
  symbols?: SymbolOption[];
}

const DEFAULT_SYMBOLS: SymbolOption[] = [
  { symbol: "BTC/USDT",  label: "BTC — Bitcoin" },
  { symbol: "ETH/USDT",  label: "ETH — Ethereum" },
  { symbol: "SOL/USDT",  label: "SOL — Solana" },
  { symbol: "XRP/USDT",  label: "XRP — Ripple" },
  { symbol: "XAU/USDT",  label: "XAU — Altın" },
  { symbol: "XAG/USDT",  label: "XAG — Gümüş" },
];

export const SymbolSelector: React.FC<SymbolSelectorProps> = ({
  currentSymbol,
  onSymbolChange,
  symbols = DEFAULT_SYMBOLS,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Dışarı tıklanınca kapat
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const current = symbols.find((s) => s.symbol === currentSymbol);
  const displayLabel = current ? current.label : currentSymbol;

  return (
    <div ref={ref} className="relative inline-block min-w-[160px]">
      <button
        onClick={() => setIsOpen((v) => !v)}
        className="flex w-full items-center justify-between rounded-lg border border-slate-600 bg-slate-800 px-3 py-2 text-sm text-slate-100 hover:border-slate-500 hover:bg-slate-700 focus:outline-none"
      >
        <span className="font-medium">{displayLabel}</span>
        <svg
          className={`ml-2 h-4 w-4 shrink-0 text-slate-400 transition-transform ${isOpen ? "rotate-180" : ""}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {isOpen && (
        <div className="absolute left-0 top-full z-50 mt-1 min-w-full rounded-lg border border-slate-700 bg-slate-800 shadow-xl">
          {symbols.map(({ symbol, label }) => (
            <button
              key={symbol}
              onClick={() => { onSymbolChange(symbol); setIsOpen(false); }}
              className={`flex w-full items-center gap-2 px-3 py-2 text-left text-sm transition-colors first:rounded-t-lg last:rounded-b-lg ${
                currentSymbol === symbol
                  ? "bg-cyan-600 text-white"
                  : "text-slate-300 hover:bg-slate-700"
              }`}
            >
              <span className="font-semibold">{symbol.split("/")[0]}</span>
              <span className="text-xs text-slate-400">{label.split("—")[1]?.trim()}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
};
