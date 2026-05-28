import React from "react";

interface TimeframeSelectorProps {
  currentTimeframe: string;
  onTimeframeChange: (timeframe: string) => void;
}

const TIMEFRAMES = [
  { value: "5m", label: "5m" },
  { value: "15m", label: "15m" },
  { value: "1h", label: "1h" },
  { value: "4h", label: "4h" },
  { value: "1d", label: "1d" },
  { value: "1w", label: "1w" },
  { value: "1month", label: "1mo" },
];

export const TimeframeSelector: React.FC<TimeframeSelectorProps> = ({
  currentTimeframe,
  onTimeframeChange,
}) => {
  return (
    <div className="flex gap-2 items-center">
      <span className="text-sm text-gray-400 font-medium">Timeframe:</span>
      <div className="flex gap-1 bg-gray-800 rounded-lg p-1">
        {TIMEFRAMES.map((timeframe) => (
          <button
            key={timeframe.value}
            onClick={() => onTimeframeChange(timeframe.value)}
            className={`px-3 py-1.5 text-xs font-medium rounded transition-all ${
              currentTimeframe === timeframe.value
                ? "bg-cyan-600 text-white shadow-lg shadow-cyan-600/50"
                : "bg-gray-700 text-gray-300 hover:bg-gray-600"
            }`}
            title={`Show data for ${timeframe.label}`}
          >
            {timeframe.label}
          </button>
        ))}
      </div>
    </div>
  );
};
