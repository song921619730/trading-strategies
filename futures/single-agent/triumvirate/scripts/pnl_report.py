#!/usr/bin/env python3
"""
pnl_report.py — 多 Magic 盈亏统计
查询 MT5 上指定 Magic 的持仓浮亏和已平仓盈亏。

用法:
  C:/Users/gj/AppData/Local/Programs/Python/Python312/python.exe \\
    F:/AIcoding_space/Hermes/strategies/futures/single-agent/triumvirate/scripts/pnl_report.py
"""
import json, os, sys
from datetime import datetime, timezone

MAGICS = {
    234004: "Triumvirate",
    234003: "CIO(废弃)",
    234010: "日内扫描",
}

def connect_mt5():
    import MetaTrader5 as mt5
    path = os.getenv("MT5_PATH", "C:/Program Files/MetaTrader 5/terminal64.exe")
    login = int(os.getenv("MT5_LOGIN", "0"))
    password = os.getenv("MT5_PASSWORD", "")
    server = os.getenv("MT5_SERVER", "")
    if not mt5.initialize(path=path, login=login, password=password, server=server):
        return None, f"MT5 init failed: {mt5.last_error()}"
    acct = mt5.account_info()
    if not acct:
        mt5.shutdown()
        return None, "No account info"
    return mt5, {"balance": acct.balance, "equity": acct.equity, "login": acct.login}

def main():
    mt5, account = connect_mt5()
    if mt5 is None:
        print(json.dumps({"error": account}))
        sys.exit(1)

    try:
        # 当前持仓浮亏
        positions = mt5.positions_get() or []
        # 已平仓历史（最近30天）
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=30)
        deals = mt5.history_deals_get(start, now) or []

        report = {
            "time_utc": now.isoformat(),
            "account": {
                "balance": account["balance"],
                "equity": account["equity"],
                "float_pnl": account["equity"] - account["balance"],
            },
            "systems": {},
        }

        for magic, label in MAGICS.items():
            # 当前持仓（该 Magic）
            my_positions = [p for p in positions if p.magic == magic]
            pos_pnl = sum(p.profit for p in my_positions)
            pos_count = len(my_positions)
            pos_details = []
            for p in my_positions:
                pos_details.append({
                    "symbol": p.symbol,
                    "type": "BUY" if p.type == 0 else "SELL",
                    "volume": p.volume,
                    "price_open": p.price_open,
                    "price_current": p.price_current,
                    "sl": p.sl,
                    "tp": p.tp,
                    "profit": round(p.profit, 2),
                })

            # 已平仓历史（该 Magic）
            my_deals = [d for d in deals if d.magic == magic and d.profit != 0]
            closed_count = len(my_deals)
            closed_pnl = sum(d.profit for d in my_deals)
            wins = sum(1 for d in my_deals if d.profit > 0)
            losses = sum(1 for d in my_deals if d.profit < 0)
            win_rate = round(wins / (wins + losses) * 100, 1) if (wins + losses) > 0 else 0
            top_win = max((d.profit for d in my_deals), default=0)
            top_loss = min((d.profit for d in my_deals), default=0)

            report["systems"][label] = {
                "magic": magic,
                "open_positions": {
                    "count": pos_count,
                    "float_pnl": round(pos_pnl, 2),
                    "details": pos_details,
                },
                "closed_trades_30d": {
                    "count": closed_count,
                    "total_pnl": round(closed_pnl, 2),
                    "wins": wins,
                    "losses": losses,
                    "win_rate_pct": win_rate,
                    "best_trade": round(top_win, 2),
                    "worst_trade": round(top_loss, 2),
                },
                "total_pnl": round(pos_pnl + closed_pnl, 2),
            }

        print(json.dumps(report, ensure_ascii=False, indent=2))

    finally:
        mt5.shutdown()

if __name__ == "__main__":
    main()
