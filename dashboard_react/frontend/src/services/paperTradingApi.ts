/**
 * Paper Trading API Service
 */

export interface PaperTradingSession {
  id: string;
  symbol: string;
  initial_capital: number;
  current_balance: number;
  positions: Position[];
  trades: PaperTrade[];
  pnl: number;
  pnl_pct: number;
  status: 'running' | 'stopped';
  created_at: string;
  equity_curve: EquityPoint[];
}

export interface Position {
  symbol: string;
  quantity: number;
  entry_price: number;
  current_price: number;
  pnl: number;
  pnl_pct: number;
}

export interface PaperTrade {
  id: string;
  timestamp: string;
  symbol: string;
  side: 'BUY' | 'SELL';
  price: number;
  quantity: number;
  commission: number;
  pnl?: number;
}

export interface EquityPoint {
  timestamp: string;
  balance: number;
}

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8502';

export const paperTradingApi = {
  async getStatus(): Promise<PaperTradingSession> {
    const response = await fetch(`${API_BASE_URL}/api/paper/status`);

    if (!response.ok) {
      throw new Error(`Failed to fetch status: ${response.statusText}`);
    }

    return response.json();
  },

  async start(params: {
    symbol: string;
    initial_capital: number;
    strategy?: string;
  }): Promise<PaperTradingSession> {
    const response = await fetch(`${API_BASE_URL}/api/paper/start`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(params),
    });

    if (!response.ok) {
      throw new Error(`Failed to start paper trading: ${response.statusText}`);
    }

    return response.json();
  },

  async stop(): Promise<{ message: string; final_balance: number }> {
    const response = await fetch(`${API_BASE_URL}/api/paper/stop`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      throw new Error(`Failed to stop paper trading: ${response.statusText}`);
    }

    return response.json();
  },

  async placeBuyOrder(params: {
    symbol: string;
    quantity: number;
    price?: number;
  }): Promise<PaperTrade> {
    const response = await fetch(`${API_BASE_URL}/api/paper/buy`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(params),
    });

    if (!response.ok) {
      throw new Error(`Failed to place buy order: ${response.statusText}`);
    }

    return response.json();
  },

  async placeSellOrder(params: {
    symbol: string;
    quantity: number;
    price?: number;
  }): Promise<PaperTrade> {
    const response = await fetch(`${API_BASE_URL}/api/paper/sell`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(params),
    });

    if (!response.ok) {
      throw new Error(`Failed to place sell order: ${response.statusText}`);
    }

    return response.json();
  },

  async getEquityCurve(): Promise<EquityPoint[]> {
    const response = await fetch(`${API_BASE_URL}/api/paper/equity-curve`);

    if (!response.ok) {
      throw new Error(`Failed to fetch equity curve: ${response.statusText}`);
    }

    return response.json();
  },

  async exportStatement(): Promise<Blob> {
    const response = await fetch(`${API_BASE_URL}/api/paper/export`, {
      method: 'GET',
    });

    if (!response.ok) {
      throw new Error(`Failed to export statement: ${response.statusText}`);
    }

    return response.blob();
  },
};
