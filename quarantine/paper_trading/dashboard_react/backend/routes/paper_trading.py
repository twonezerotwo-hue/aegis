"""
Paper Trading Routes - Virtual trading endpoints
"""
from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone
from typing import Dict
import logging
import uuid

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/paper", tags=["paper_trading"])

# In-memory session storage (in production, use database)
SESSIONS: Dict[str, Dict] = {}


@router.get("/status")
async def get_status():
    """Get current paper trading session status"""
    if not SESSIONS:
        raise HTTPException(status_code=404, detail="No active session")

    session_id = list(SESSIONS.keys())[0]
    session = SESSIONS[session_id]

    return {
        "id": session_id,
        "symbol": session["symbol"],
        "initial_capital": session["initial_capital"],
        "current_balance": session["current_balance"],
        "positions": session["positions"],
        "trades": session["trades"],
        "pnl": session["current_balance"] - session["initial_capital"],
        "pnl_pct": (
            (session["current_balance"] - session["initial_capital"])
            / session["initial_capital"]
            * 100
        ),
        "status": "running",
        "created_at": session["created_at"],
        "equity_curve": session["equity_curve"],
    }


@router.post("/start")
async def start_session(request_data: Dict):
    """Start a new paper trading session"""
    try:
        symbol = request_data.get("symbol", "BTC/USDT")
        initial_capital = request_data.get("initial_capital", 100000)
        strategy = request_data.get("strategy", "sma_crossover")

        session_id = str(uuid.uuid4())

        SESSIONS[session_id] = {
            "symbol": symbol,
            "initial_capital": initial_capital,
            "current_balance": initial_capital,
            "positions": [],
            "trades": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "equity_curve": [
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "balance": initial_capital,
                }
            ],
            "strategy": strategy,
        }

        return {
            "id": session_id,
            "symbol": symbol,
            "initial_capital": initial_capital,
            "current_balance": initial_capital,
            "positions": [],
            "trades": [],
            "pnl": 0,
            "pnl_pct": 0,
            "status": "running",
            "created_at": SESSIONS[session_id]["created_at"],
            "equity_curve": SESSIONS[session_id]["equity_curve"],
        }

    except Exception as e:
        logger.error(f"Error starting paper trading: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stop")
async def stop_session():
    """Stop current paper trading session"""
    if not SESSIONS:
        raise HTTPException(status_code=404, detail="No active session")

    session_id = list(SESSIONS.keys())[0]
    session = SESSIONS.pop(session_id)

    final_balance = session["current_balance"]
    pnl = final_balance - session["initial_capital"]

    return {
        "message": "Paper trading session stopped",
        "final_balance": final_balance,
        "pnl": pnl,
        "pnl_pct": (pnl / session["initial_capital"] * 100),
    }


@router.post("/buy")
async def place_buy_order(request_data: Dict):
    """Place a buy order"""
    if not SESSIONS:
        raise HTTPException(status_code=404, detail="No active session")

    session_id = list(SESSIONS.keys())[0]
    session = SESSIONS[session_id]

    symbol = request_data.get("symbol", session["symbol"])
    quantity = request_data.get("quantity", 1)
    price = request_data.get("price", 50000)  # Mock price

    # Calculate cost with commission
    commission = price * quantity * 0.001  # 0.1% commission
    total_cost = (price * quantity) + commission

    if total_cost > session["current_balance"]:
        raise HTTPException(status_code=400, detail="Insufficient balance")

    # Update balance
    session["current_balance"] -= total_cost

    # Create trade
    trade = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "side": "BUY",
        "price": price,
        "quantity": quantity,
        "commission": commission,
    }

    session["trades"].append(trade)

    # Update or create position
    position_exists = False
    for pos in session["positions"]:
        if pos["symbol"] == symbol:
            pos["quantity"] += quantity
            pos["entry_price"] = (
                (pos["entry_price"] * (pos["quantity"] - quantity) + price * quantity)
                / pos["quantity"]
            )
            position_exists = True
            break

    if not position_exists:
        session["positions"].append(
            {
                "symbol": symbol,
                "quantity": quantity,
                "entry_price": price,
                "current_price": price,
                "pnl": 0,
                "pnl_pct": 0,
            }
        )

    # Update equity curve
    session["equity_curve"].append(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "balance": session["current_balance"],
        }
    )

    return trade


@router.post("/sell")
async def place_sell_order(request_data: Dict):
    """Place a sell order"""
    if not SESSIONS:
        raise HTTPException(status_code=404, detail="No active session")

    session_id = list(SESSIONS.keys())[0]
    session = SESSIONS[session_id]

    symbol = request_data.get("symbol", session["symbol"])
    quantity = request_data.get("quantity", 1)
    price = request_data.get("price", 50000)  # Mock price

    # Check if position exists and has enough quantity
    position_found = False
    for pos in session["positions"]:
        if pos["symbol"] == symbol:
            if pos["quantity"] < quantity:
                raise HTTPException(status_code=400, detail="Insufficient position")

            position_found = True

            # Calculate PnL
            pnl = (price - pos["entry_price"]) * quantity
            commission = price * quantity * 0.001

            # Update balance
            session["current_balance"] += (price * quantity) - commission

            # Update position
            pos["quantity"] -= quantity
            if pos["quantity"] == 0:
                session["positions"].remove(pos)
            else:
                pos["current_price"] = price

            break

    if not position_found:
        raise HTTPException(status_code=400, detail="No position found")

    # Create trade
    trade = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "side": "SELL",
        "price": price,
        "quantity": quantity,
        "commission": commission,
        "pnl": pnl,
    }

    session["trades"].append(trade)

    # Update equity curve
    session["equity_curve"].append(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "balance": session["current_balance"],
        }
    )

    return trade


@router.get("/equity-curve")
async def get_equity_curve():
    """Get equity curve of current session"""
    if not SESSIONS:
        raise HTTPException(status_code=404, detail="No active session")

    session_id = list(SESSIONS.keys())[0]
    session = SESSIONS[session_id]

    return session["equity_curve"]


@router.get("/export")
async def export_statement():
    """Export paper trading statement"""
    if not SESSIONS:
        raise HTTPException(status_code=404, detail="No active session")

    session_id = list(SESSIONS.keys())[0]
    session = SESSIONS[session_id]

    # Generate CSV content
    csv_content = "Paper Trading Statement\n"
    csv_content += f"Session ID: {session_id}\n"
    csv_content += f"Symbol: {session['symbol']}\n"
    csv_content += f"Initial Capital: ${session['initial_capital']:.2f}\n"
    csv_content += f"Final Balance: ${session['current_balance']:.2f}\n"
    csv_content += f"PnL: ${session['current_balance'] - session['initial_capital']:.2f}\n\n"

    csv_content += "Trade History\n"
    csv_content += "Timestamp,Side,Symbol,Price,Quantity,Commission,PnL\n"

    for trade in session["trades"]:
        csv_content += (
            f"{trade['timestamp']},{trade['side']},{trade['symbol']},"
            f"${trade['price']:.2f},{trade['quantity']:.4f},"
            f"${trade['commission']:.2f},"
            f"${trade.get('pnl', 0):.2f}\n"
        )

    return {"content": csv_content, "filename": f"paper_trading_{session_id}.csv"}
