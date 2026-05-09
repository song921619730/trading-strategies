#!/usr/bin/env python3
"""
交易日志记录器: 记录每一笔信号/交易的完整信息
用法:
  python trade_logger.py record <trade_file.json>   # 记录一笔新信号/交易
  python trade_logger.py update <ticket> <outcome>  # 更新交易结果
  python trade_logger.py report [days]              # 生成 P&L 报告
  python trade_logger.py list [--closed]            # 列出交易
"""
import sys
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

UTC8 = timezone(timedelta(hours=8))

def get_journal_path(strategy_dir):
    """获取交易日志文件路径"""
    log_dir = Path(strategy_dir) / "logs" / "shadow"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "trades.jsonl"

def record_trade(strategy_dir, data):
    """记录一笔新交易/信号"""
    journal = get_journal_path(strategy_dir)
    entry = {
        "timestamp": datetime.now(UTC8).isoformat(),
        "type": data.get("type", "signal"),  # signal / trade
        "status": data.get("status", "open"),  # open / closed / pending
        "symbol": data.get("symbol"),
        "direction": data.get("direction"),  # BUY / SELL
        "entry_price": data.get("entry_price"),
        "sl": data.get("sl"),
        "tp": data.get("tp"),
        "volume": data.get("volume"),
        "rr_ratio": data.get("rr_ratio"),
        "confidence": data.get("confidence"),
        "reason": data.get("reason"),
        "strategy": data.get("strategy"),
        "ticket": data.get("ticket"),
        # 结果字段 (平仓后填充)
        "exit_price": None,
        "exit_time": None,
        "exit_reason": None,  # SL_HIT / TP_HIT / STRUCTURE / TIME_EXIT / NEWS_RISK
        "profit": None,
        "pips": None,
        "rr_achieved": None,
        "hold_duration_hours": None,
        "notes": data.get("notes", "")
    }
    
    with open(journal, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    
    print(f"✅ Recorded: {entry['symbol']} {entry['direction']} @ {entry['entry_price']}")
    return entry

def update_trade(strategy_dir, ticket, outcome_data):
    """更新交易结果"""
    journal = get_journal_path(strategy_dir)
    if not journal.exists():
        print(f"❌ No journal found")
        return False
    
    # Read all entries
    entries = []
    with open(journal, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                entries.append(json.loads(line))
    
    # Find and update
    updated = False
    for entry in entries:
        if entry.get("ticket") == ticket and entry.get("status") == "open":
            entry.update({
                "status": "closed",
                "exit_price": outcome_data.get("exit_price"),
                "exit_time": outcome_data.get("exit_time", datetime.now(UTC8).isoformat()),
                "exit_reason": outcome_data.get("exit_reason"),
                "profit": outcome_data.get("profit"),
                "pips": outcome_data.get("pips"),
                "rr_achieved": outcome_data.get("rr_achieved"),
                "notes": outcome_data.get("notes", entry.get("notes", ""))
            })
            # Calculate hold duration
            if entry.get("exit_time") and entry.get("timestamp"):
                try:
                    t1 = datetime.fromisoformat(entry["timestamp"])
                    t2 = datetime.fromisoformat(entry["exit_time"])
                    entry["hold_duration_hours"] = round((t2 - t1).total_seconds() / 3600, 1)
                except:
                    pass
            updated = True
            break
    
    if not updated:
        print(f"❌ Trade {ticket} not found or already closed")
        return False
    
    # Rewrite journal
    with open(journal, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    
    print(f"✅ Updated: {ticket} closed at {outcome_data.get('exit_price')} profit={outcome_data.get('profit')}")
    return True

def generate_report(strategy_dir, days=30):
    """生成 P&L 报告"""
    journal = get_journal_path(strategy_dir)
    if not journal.exists():
        print("📊 No trades recorded yet")
        return
    
    entries = []
    with open(journal, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                entries.append(json.loads(line))
    
    # Filter by date
    cutoff = datetime.now(UTC8) - timedelta(days=days)
    recent = [e for e in entries if datetime.fromisoformat(e["timestamp"]) >= cutoff]
    
    if not recent:
        print(f"📊 No trades in last {days} days")
        return
    
    total = len(recent)
    closed = [e for e in recent if e["status"] == "closed"]
    open_trades = [e for e in recent if e["status"] == "open"]
    
    wins = [e for e in closed if e.get("profit", 0) > 0]
    losses = [e for e in closed if e.get("profit", 0) <= 0]
    
    total_profit = sum(e.get("profit", 0) or 0 for e in closed)
    gross_profit = sum(e.get("profit", 0) for e in wins)
    gross_loss = abs(sum(e.get("profit", 0) for e in losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    win_rate = len(wins) / len(closed) if closed else 0
    avg_win = gross_profit / len(wins) if wins else 0
    avg_loss = gross_loss / len(losses) if losses else 0
    
    print(f"📊 P&L Report (Last {days} days)")
    print(f"{'='*50}")
    print(f"Total Signals: {total}")
    print(f"Closed: {len(closed)} | Open: {len(open_trades)}")
    print(f"Win Rate: {win_rate*100:.1f}% ({len(wins)}/{len(closed)})")
    print(f"Total P&L: ${total_profit:.2f}")
    print(f"Gross Profit: ${gross_profit:.2f} | Gross Loss: ${gross_loss:.2f}")
    print(f"Profit Factor: {profit_factor:.2f}")
    print(f"Avg Win: ${avg_win:.2f} | Avg Loss: ${avg_loss:.2f}")
    print(f"Avg RR Achieved: {sum(e.get('rr_achieved', 0) or 0 for e in wins)/len(wins):.2f}" if wins else "Avg RR: N/A")
    
    # Print trade list
    if closed:
        print(f"\n📋 Trade List:")
        print(f"{'#':>3} {'Symbol':<10} {'Dir':<4} {'Entry':<10} {'Exit':<10} {'P&L':>8} {'RR':>5} {'Exit Reason':<12}")
        print("-" * 70)
        for i, e in enumerate(closed, 1):
            print(f"{i:>3} {e.get('symbol','?'):<10} {e.get('direction','?'):<4} "
                  f"{str(e.get('entry_price','?')):<10} {str(e.get('exit_price','?')):<10} "
                  f"${e.get('profit',0):>7.2f} {str(e.get('rr_achieved','?')):>5} "
                  f"{e.get('exit_reason','?'):<12}")

def list_trades(strategy_dir, closed_only=False):
    """列出所有交易"""
    journal = get_journal_path(strategy_dir)
    if not journal.exists():
        print("📋 No trades recorded yet")
        return
    
    entries = []
    with open(journal, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                entries.append(json.loads(line))
    
    if closed_only:
        entries = [e for e in entries if e["status"] == "closed"]
    
    print(f"📋 Trades ({len(entries)} total, {'closed' if closed_only else 'all'})")
    print(f"{'Ticket':<12} {'Symbol':<10} {'Dir':<4} {'Status':<8} {'Entry':<10} {'Exit':<10} {'P&L':>8}")
    print("-" * 70)
    for e in entries:
        print(f"{str(e.get('ticket','?')):<12} {e.get('symbol','?'):<10} {e.get('direction','?'):<4} "
              f"{e.get('status','?'):<8} {str(e.get('entry_price','?')):<10} "
              f"{str(e.get('exit_price','?')):<10} ${str(e.get('profit','?')):>7}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python trade_logger.py <command> [args]")
        print("命令: record, update, report, list")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    # 默认策略目录 (当前目录或传入)
    strategy_dir = sys.argv[2] if len(sys.argv) > 2 else "."
    
    if cmd == "record":
        # 从 stdin 读取 JSON 或从文件读取
        if len(sys.argv) > 3:
            with open(sys.argv[3], "r") as f:
                data = json.load(f)
        else:
            data = json.loads(sys.stdin.read())
        record_trade(strategy_dir, data)
    
    elif cmd == "update":
        ticket = sys.argv[3]
        if len(sys.argv) > 4:
            with open(sys.argv[4], "r") as f:
                data = json.load(f)
        else:
            data = json.loads(sys.stdin.read())
        update_trade(strategy_dir, ticket, data)
    
    elif cmd == "report":
        days = int(sys.argv[3]) if len(sys.argv) > 3 else 30
        generate_report(strategy_dir, days)
    
    elif cmd == "list":
        closed_only = "--closed" in sys.argv
        list_trades(strategy_dir, closed_only)
