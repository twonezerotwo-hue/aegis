/**
 * NewsHeadlines — gerçek canlı kripto haber akışı paneli.
 * /api/news/live'dan RSS başlıklarını çeker (CoinDesk/Cointelegraph/Decrypt).
 * Her başlık: duygu rengi, kaynak, yaş, link.
 */
import React, { useState, useEffect } from "react";

const API_BASE = (import.meta as any).env?.VITE_API_URL || "http://localhost:8502";

interface Headline {
  title: string;
  source: string;
  link?: string;
  age_h: number;
  sentiment: number;
  symbols: string[];
}

interface LiveNews {
  available: boolean;
  symbol?: string;
  impact_score?: number;
  sentiment?: number;
  count_24h?: number;
  count_total?: number;
  sources?: string[];
  fetched_at?: string;
  headlines?: Headline[];
}

interface Props {
  symbol?: string;
}

export const NewsHeadlines: React.FC<Props> = ({ symbol = "BTC" }) => {
  const [news, setNews] = useState<LiveNews | null>(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    const sym = symbol.replace("/USDT", "").replace("/", "");
    const fetchNews = () =>
      fetch(`${API_BASE}/api/news/live?symbol=${sym}`)
        .then(r => r.json())
        .then(setNews)
        .catch(() => {});
    fetchNews();
    const id = setInterval(fetchNews, 120_000);  // 2 dk
    return () => clearInterval(id);
  }, [symbol]);

  if (!news) return null;

  if (!news.available) {
    return (
      <div className="rounded-2xl border border-slate-700/60 bg-slate-900 p-4">
        <p className="text-[11px] text-slate-500">📰 Haber akışı geçici olarak yok</p>
      </div>
    );
  }

  const headlines = news.headlines ?? [];
  const shown = expanded ? headlines : headlines.slice(0, 4);
  const sentColor = (s: number) =>
    s > 0.1 ? "text-emerald-400" : s < -0.1 ? "text-rose-400" : "text-slate-500";
  const sentDot = (s: number) =>
    s > 0.1 ? "bg-emerald-400" : s < -0.1 ? "bg-rose-400" : "bg-slate-600";

  const aggSent = news.sentiment ?? 0;
  const aggLabel = aggSent > 0.1 ? "Pozitif" : aggSent < -0.1 ? "Negatif" : "Nötr";
  const aggCls = aggSent > 0.1 ? "text-emerald-400" : aggSent < -0.1 ? "text-rose-400" : "text-amber-400";

  return (
    <div className="rounded-2xl border border-slate-700/60 bg-slate-900 p-4">
      {/* Başlık + özet */}
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-semibold uppercase tracking-widest text-slate-400">
            📰 Canlı Haber Akışı
          </span>
          <span className="flex items-center gap-1 text-[9px] text-slate-600">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
            {news.sources?.length ?? 0} kaynak
          </span>
        </div>
        <div className="flex items-center gap-3 text-[10px]">
          <span className="text-slate-500">
            <span className="font-mono font-bold text-slate-300">{news.count_24h}</span>/24s
          </span>
          <span className={`font-semibold ${aggCls}`}>
            {aggLabel} ({aggSent >= 0 ? "+" : ""}{aggSent.toFixed(2)})
          </span>
          <span className="text-slate-500">
            Etki <span className="font-mono font-bold text-slate-300">{news.impact_score}</span>
          </span>
        </div>
      </div>

      {/* Başlıklar */}
      <div className="space-y-1.5">
        {shown.map((h, i) => (
          <a
            key={i}
            href={h.link || "#"}
            target="_blank"
            rel="noopener noreferrer"
            className="group flex items-start gap-2 rounded-lg px-2 py-1.5 transition-colors hover:bg-slate-800/50"
          >
            <span className={`mt-1 h-1.5 w-1.5 shrink-0 rounded-full ${sentDot(h.sentiment)}`} />
            <div className="min-w-0 flex-1">
              <p className="truncate text-[11px] leading-4 text-slate-300 group-hover:text-white">
                {h.title}
              </p>
              <div className="flex items-center gap-2 text-[8px] text-slate-600">
                <span className="font-semibold text-slate-500">{h.source}</span>
                <span>{h.age_h < 1 ? "az önce" : `${Math.round(h.age_h)}s önce`}</span>
                {h.symbols.length > 0 && (
                  <span className="flex gap-0.5">
                    {h.symbols.map(s => (
                      <span key={s} className="rounded bg-slate-800 px-1 font-mono text-slate-400">{s}</span>
                    ))}
                  </span>
                )}
                <span className={`font-mono ${sentColor(h.sentiment)}`}>
                  {h.sentiment > 0 ? "+" : ""}{h.sentiment.toFixed(2)}
                </span>
              </div>
            </div>
          </a>
        ))}
      </div>

      {/* Genişlet/daralt */}
      {headlines.length > 4 && (
        <button
          onClick={() => setExpanded(v => !v)}
          className="mt-2 w-full rounded-lg border border-slate-700/50 py-1 text-[10px] font-semibold text-slate-500 hover:bg-slate-800/50 hover:text-slate-300"
        >
          {expanded ? "▲ Daha az" : `▼ ${headlines.length - 4} başlık daha`}
        </button>
      )}
    </div>
  );
};
