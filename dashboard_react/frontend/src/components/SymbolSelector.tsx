import React, { useState, useEffect } from "react";

interface SymbolSelectorProps {
  currentSymbol: string;
  onSymbolChange: (symbol: string) => void;
}

export const SymbolSelector: React.FC<SymbolSelectorProps> = ({
  currentSymbol,
  onSymbolChange,
}) => {
  const [symbols, setSymbols] = useState<string[]>([
    "BTC/USDT",
    "ETH/USDT",
    "SOL/USDT",
    "XRP/USDT",
  ]);
  const [isOpen, setIsOpen] = useState(false);

  const handleSymbolSelect = (symbol: string) => {
    onSymbolChange(symbol);
    setIsOpen(false);
  };

  return (
    <div className="relative inline-block w-full md:w-48">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full rounded-lg border border-gray-600 bg-gray-800 px-4 py-2 text-left text-white hover:border-gray-500 focus:border-cyan-400 focus:outline-none"
      >
        <div className="flex items-center justify-between">
          <span className="font-medium">{currentSymbol}</span>
          <svg
            className={`h-5 w-5 transition-transform ${
              isOpen ? "rotate-180" : ""
            }`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M19 14l-7 7m0 0l-7-7m7 7V3"
            />
          </svg>
        </div>
      </button>

      {isOpen && (
        <div className="absolute top-full z-50 mt-1 w-full rounded-lg border border-gray-600 bg-gray-800 shadow-lg">
          {symbols.map((symbol) => (
            <button
              key={symbol}
              onClick={() => handleSymbolSelect(symbol)}
              className={`w-full px-4 py-2 text-left transition-colors first:rounded-t-lg last:rounded-b-lg ${
                currentSymbol === symbol
                  ? "bg-cyan-500 text-white"
                  : "text-gray-300 hover:bg-gray-700"
              }`}
            >
              {symbol}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};
