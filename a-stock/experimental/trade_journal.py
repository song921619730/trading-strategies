#!/usr/bin/env python3
"""
Trade Journal — 完整的交易记录和收益计算
记录每笔信号的入场、出场、盈亏、退出原因，支持实盘和影子模式。

用法:
  python trade_journal.py <strategy_dir> record <json_file>   # 记录新信号
  python trade_journal.py <strategy_dir> update <json_file>   # 更新结果
  python trade_journal.py <strategy_dir> report [days]        # 收益报告
  python trade_journal.py <strategy_dir> list [--closed]      # 交易列表
  python trade_journal.py <strategy_dir> sync_mt5             # 从 MT5 同步已平仓交易
"""
import sys
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

UTC8 = timezone(timedelta(hours=8))

def get_journal_path(strategy_dir):
    """获取交易日志路径 (JSONL 格式，每行一笔完整交易)"""
    log_dir = Path(strategy_dir) / "logs" / "journal"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "trades.jsonl"

def record(strategy_dir, data):
    """记录一笔新信号或交易"""
    journal = get_journal_path(strategy_dir)
    now = datetime.now(UTC8)
    
    entry = {
        "id": f"{now.strftime('%Y%m%d_%H%M%S')}_{data.get('symbol','?')}",
        "timestamp": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "mode": data.get("mode", "shadow"),  # real / shadow
        "status": "open",
        # 交易信息
        "symbol": data.get("symbol"),
        "direction": data.get("direction"),  # BUY / SELL
        "entry_price": data.get("entry_price"),
        "sl": data.get("sl"),
        "tp": data.get("tp"),
        "volume": data.get("volume"),
        "rr_planned": data.get("rr_planned"),
        "confidence": data.get("confidence", 5),
        "reason": data.get("reason", ""),
        "strategy": data.get("strategy", ""),
        "ticket": data.get("ticket"),
        # 结果字段 (平仓后填充)
        "exit_price": None,
        "exit_time": None,
        "exit_date": None,
        "exit_reason": None,
        "profit": None,
        "profit_pct": None,
        "pips": None,
        "rr_achieved": None,
        "hold_hours": None,
        "swap": None,
        "commission": None,
        "net_profit": None,
        "notes": data.get("notes", "")
    }
    
    with open(journal, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    
    print(f"✅ 记录: {entry['symbol']} {entry['direction']} @ {entry['entry_price']} "
          f"(SL={entry['sl']}, TP={entry['tp']}, RR={entry['rr_planned']})")
    return entry

def update(strategy_dir, data):
    """更新交易结果"""
    journal = get_journal_path(strategy_dir)
    if not journal.exists():
        print("❌ 交易日志不存在")
        return False
    
    entries = []
    with open(journal, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                entries.append(json.loads(line))
    
    updated = False
    ticket = data.get("ticket")
    trade_id = data.get("id")
    
    for entry in entries:
        match = False
        if ticket and entry.get("ticket") == ticket and entry.get("status") == "open":
            match = True
        elif trade_id and entry.get("id") == trade_id and entry.get("status") == "open":
            match = True
        
        if match:
            entry.update({
                "status": "closed",
                "exit_price": data.get("exit_price"),
                "exit_time": data.get("exit_time", datetime.now(UTC8).isoformat()),
                "exit_date": data.get("exit_date"),
                "exit_reason": data.get("exit_reason"),
                "profit": data.get("profit"),
                "pips": data.get("pips"),
                "rr_achieved": data.get("rr_achieved"),
                "swap": data.get("swap"),
                "commission": data.get("commission"),
                "notes": data.get("notes", entry.get("notes", ""))
            })
            
            # 计算持有时间
            if entry.get("exit_time") and entry.get("timestamp"):
                try:
                    t1 = datetime.fromisoformat(entry["timestamp"])
                    t2 = datetime.fromisoformat(entry["exit_time"])
                    entry["hold_hours"] = round((t2 - t1).total_seconds() / 3600, 1)
                except:
                    pass
            
            # 计算净盈亏
            profit = entry.get("profit") or 0
            swap = entry.get("swap") or 0
            commission = entry.get("commission") or 0
            entry["net_profit"] = profit + swap + commission
            
            updated = True
            break
    
    if not updated:
        print(f"❌ 未找到交易: ticket={ticket}, id={trade_id}")
        return False
    
    with open(journal, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    
    print(f"✅ 更新: {trade_id or ticket} 已平仓, 盈亏={data.get('profit')}, 原因={data.get('exit_reason')}")
    return True

def report(strategy_dir, days=30):
    """生成 P&L 报告"""
    journal = get_journal_path(strategy_dir)
    if not journal.exists():
        print("📊 暂无交易记录")
        return
    
    entries = []
    with open(journal, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                entries.append(json.loads(line))
    
    cutoff = datetime.now(UTC8) - timedelta(days=days)
    recent = [e for e in entries if datetime.fromisoformat(e["timestamp"]) >= cutoff]
    
    if not recent:
        print(f"📊 最近 {days} 天无交易")
        return
    
    total = len(recent)
    closed = [e for e in recent if e["status"] == "closed"]
    open_trades = [e for e in recent if e["status"] == "open"]
    
    wins = [e for e in closed if (e.get("profit") or 0) > 0]
    losses = [e for e in closed if (e.get("profit") or 0) <= 0]
    
    gross_profit = sum(e.get("profit", 0) or 0 for e in wins)
    gross_loss = abs(sum(e.get("profit", 0) or 0 for e in losses))
    total_pnl = gross_profit - gross_loss
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    win_rate = len(wins) / len(closed) * 100 if closed else 0
    avg_win = gross_profit / len(wins) if wins else 0
    avg_loss = gross_loss / len(losses) if losses else 0
    avg_rr = sum(e.get("rr_achieved", 0) or 0 for e in closed) / len(closed) if closed else 0
    max_win = max((e.get("profit", 0) or 0 for e in closed), default=0)
    max_loss = min((e.get("profit", 0) or 0 for e in closed), default=0)
    
    # 按品种统计
    by_symbol = {}
    for e in closed:
        sym = e.get("symbol", "?")
        if sym not in by_symbol:
            by_symbol[sym] = {"trades": 0, "wins": 0, "pnl": 0}
        by_symbol[sym]["trades"] += 1
        if (e.get("profit") or 0) > 0:
            by_symbol[sym]["wins"] += 1
        by_symbol[sym]["pnl"] += (e.get("profit") or 0)
    
    # 按退出原因统计
    by_reason = {}
    for e in closed:
        reason = e.get("exit_reason", "unknown")
        if reason not in by_reason:
            by_reason[reason] = {"count": 0, "pnl": 0}
        by_reason[reason]["count"] += 1
        by_reason[reason]["pnl"] += (e.get("profit") or 0)
    
    print(f"{'='*60}")
    print(f"📊 收益报告 (最近 {days} 天)")
    print(f"{'='*60}")
    print(f"总信号: {total} | 已平仓: {len(closed)} | 持仓中: {len(open_trades)}")
    print(f"胜率: {win_rate:.1f}% ({len(wins)}赢/{len(losses)}亏)")
    print(f"总盈亏: ${total_pnl:+.2f}")
    print(f"总盈利: ${gross_profit:.2f} | 总亏损: ${gross_loss:.2f}")
    print(f"盈亏比 (Profit Factor): {profit_factor:.2f}")
    print(f"平均盈利: ${avg_win:.2f} | 平均亏损: ${avg_loss:.2f}")
    print(f"平均实现盈亏比: {avg_rr:.2f}")
    print(f"最大单笔盈利: ${max_win:.2f} | 最大单笔亏损: ${max_loss:.2f}")
    
    if by_symbol:
        print(f"\n📈 按品种统计:")
        print(f"  {'品种':<12} {'交易数':>6} {'胜率':>6} {'盈亏':>10}")
        for sym, stats in sorted(by_symbol.items(), key=lambda x: x[1]["pnl"], reverse=True):
            wr = stats["wins"]/stats["trades"]*100 if stats["trades"] > 0 else 0
            print(f"  {sym:<12} {stats['trades']:>6} {wr:>5.0f}% ${stats['pnl']:>+9.2f}")
    
    if by_reason:
        print(f"\n🏷  按退出原因统计:")
        for reason, stats in sorted(by_reason.items(), key=lambda x: x[1]["pnl"], reverse=True):
            print(f"  {reason:<15} {stats['count']:>4} 笔  ${stats['pnl']:>+8.2f}")
    
    if closed:
        print(f"\n📋 交易明细:")
        print(f"{'#':>3} {'日期':<11} {'品种':<10} {'方向':<4} {'入场':<10} {'出场':<10} {'盈亏':>8} {'RR':>5} {'原因':<12}")
        print("-" * 80)
        for i, e in enumerate(closed, 1):
            print(f"{i:>3} {e.get('date','?'):<11} {e.get('symbol','?'):<10} "
                  f"{e.get('direction','?'):<4} {str(e.get('entry_price','?')):<10} "
                  f"{str(e.get('exit_price','?')):<10} ${(e.get('profit',0) or 0):>+7.2f} "
                  f"{str(e.get('rr_achieved','?')):>5} {e.get('exit_reason','?'):<12}")

def list_trades(strategy_dir, closed_only=False):
    """列出所有交易"""
    journal = get_journal_path(strategy_dir)
    if not journal.exists():
        print("📋 暂无交易记录")
        return
    
    entries = []
    with open(journal, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                entries.append(json.loads(line))
    
    if closed_only:
        entries = [e for e in entries if e["status"] == "closed"]
    
    print(f"📋 交易列表 ({len(entries)} 笔, {'已平仓' if closed_only else '全部'})")
    print(f"{'ID':<25} {'品种':<10} {'方向':<4} {'状态':<8} {'入场':<10} {'出场':<10} {'盈亏':>8}")
    print("-" * 80)
    for e in entries:
        print(f"{e.get('id','?'):<25} {e.get('symbol','?'):<10} {e.get('direction','?'):<4} "
              f"{e.get('status','?'):<8} {str(e.get('entry_price','?')):<10} "
              f"{str(e.get('exit_price','?')):<10} ${(e.get('profit',0) or 0):>7.2f}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python trade_journal.py <strategy_dir> <command> [args]")
        print("命令: record, update, report, list")
        sys.exit(1)
    
    strategy_dir = sys.argv[1]
    cmd = sys.argv[2]
    
    if cmd == "record":
        data = json.loads(sys.stdin.read()) if len(sys.argv) < 4 else json.load(open(sys.argv[3]))
        record(strategy_dir, data)
    elif cmd == "update":
        data = json.loads(sys.stdin.read()) if len(sys.argv) < 4 else json.load(open(sys.argv[3]))
        update(strategy_dir, data)
    elif cmd == "report":
        days = int(sys.argv[3]) if len(sys.argv) > 3 else 30
        report(strategy_dir, days)
    elif cmd == "list":
        list_trades(strategy_dir, closed_only="--closed" in sys.argv)
