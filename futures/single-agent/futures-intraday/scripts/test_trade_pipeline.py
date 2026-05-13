#!/usr/bin/env python3
"""MT5 下单链路测试 — dry-run + 实盘可选"""
import json, os, sys, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from execute_trade import load_config, check_risk, calculate_lot_size, place_order, connect_mt5
from signal_scanner import connect_mt5 as scanner_connect, scan_strategy

import MetaTrader5 as mt5

cfg = load_config()
risk_cfg = cfg.get("risk", {})
magic = cfg.get("magic_number", 234010)

print("=" * 60)
print("MT5 下单链路测试")
print("=" * 60)

# 1. 连接
print("\n[1/5] 连接 MT5 ...")
mt5_conn, account = connect_mt5()
if mt5_conn is None:
    print(f"  ❌ 连接失败: {account}")
    sys.exit(1)
print(f"  ✅ 已连接 账户={account.get('login','?')} 余额={account.get('balance','?')} 净值={account.get('equity','?')}")

# 2. 检查已有持仓
print("\n[2/5] 检查现有持仓 ...")
positions = mt5_conn.positions_get()
existing = [p for p in (positions or []) if p.magic == magic]
if existing:
    print(f"  当前已有 {len(existing)} 个持仓:")
    for p in existing:
        print(f"    #{p.ticket} {p.symbol} {'BUY' if p.type==0 else 'SELL'} vol={p.volume} SL={p.sl} TP={p.tp}")
else:
    print(f"  无持仓 (魔法号: {magic})")

# 3. 获取市场实时行情
print(f"\n[3/5] 获取当前行情 ...")
test_symbols = {
    "EURUSD": {"direction": "long", "tf": "H1", "reason": "测试品种"},
    "GBPUSD": {"direction": "long", "tf": "H1", "reason": "深度超卖"},
}

print(f"\n{'品种':<10} {'价格':<12} {'点差':<8} {'RSI':<8} {'ATR%':<8}")
print("-" * 46)
for sym in test_symbols:
    tick = mt5_conn.symbol_info_tick(sym)
    price = tick.ask if tick else 0
    
    # Get RSI/ATR (same logic as scanner)
    bars = mt5_conn.copy_rates_from_pos(sym, mt5_conn.TIMEFRAME_H1, 0, 30)
    if bars is not None and len(bars) >= 20:
        closes = [b["close"] for b in bars]
        from signal_scanner import calc_rsi, calc_atr
        rsi = calc_rsi(closes)
        atr = calc_atr([
            {"close": b["close"], "high": b["high"], "low": b["low"], "open": b["open"]}
            for b in bars
        ])
        atr_pct = atr / closes[-1] * 100 if closes[-1] > 0 else 0
    else:
        rsi = 0
        atr_pct = 0
    
    spread = (tick.ask - tick.bid) * 10000 if tick else 0
    print(f"{sym:<10} {price:<12.5f} {spread:<8.1f} {rsi:<8.1f} {atr_pct:<8.3f}")

# 4. 创建测试信号 → dry-run
print(f"\n[4/5] 测试风控+手数计算（Dry-run）...")
for sym, info in test_symbols.items():
    tick = mt5_conn.symbol_info_tick(sym)
    if not tick:
        continue
    
    price = tick.ask if info["direction"] == "long" else tick.bid
    
    # 获取真实 ATR 用于 SL/TP 计算
    bars = mt5_conn.copy_rates_from_pos(sym, mt5_conn.TIMEFRAME_H1, 0, 30)
    atr = 0
    if bars is not None and len(bars) >= 14:
        from signal_scanner import calc_atr as ca
        atr = ca([
            {"close": b["close"] if isinstance(b, (dict, np.void)) else b.close,
             "high": b["high"] if isinstance(b, (dict, np.void)) else b.high,
             "low": b["low"] if isinstance(b, (dict, np.void)) else b.low,
             "open": b["open"] if isinstance(b, (dict, np.void)) else b.open}
            for b in bars
        ])
    
    sig = {
        "strategy_id": "test_manual_01",
        "symbol": sym,
        "timeframe": "H1",
        "direction": info["direction"],
        "current_price": price,
        "rsi": 30.0,
        "atr": atr,
        "atr_pct": atr / price * 100 if price > 0 else 0,
        "session": "test",
        "consecutive_bears": 0,
        "utc_hour": 0,
        "match_reasons": "test diagnostic order",
    }
    
    print(f"\n  🔸 {sym} ({info['direction']}) @ {price:.5f}  ATR={atr:.5f}")
    
    # Risk check
    allowed, reason = check_risk(mt5_conn, sig, risk_cfg, magic)
    print(f"     风控检查: {'✅' if allowed else '❌'} {reason}")
    
    if allowed:
        # Lot size
        lot = calculate_lot_size(mt5_conn, sym, sig,
                                 risk_cfg.get("risk_per_trade_pct", 0.05),
                                 account.get("equity", 2000),
                                 risk_cfg)
        print(f"     计算手数: {lot:.2f}")
        
        # Calculate SL/TP (same logic as place_order)
        sl_atr_mult = risk_cfg.get("sl_atr_multiple", 2.0)
        tp_rr_mult = risk_cfg.get("tp_rr_multiple", 2.0)
        sl_dist = atr * sl_atr_mult
        tp_dist = sl_dist * tp_rr_mult
        sl = price - sl_dist if info["direction"] == "long" else price + sl_dist
        tp = price + tp_dist if info["direction"] == "long" else price - tp_dist
        sym_info = mt5_conn.symbol_info(sym)
        digits = sym_info.digits if sym_info else 5
        print(f"     SL={round(sl, digits)}  TP={round(tp, digits)}  RR={tp_rr_mult}:1")
        print(f"     每手风险={sl_dist:.5f}")

# 5. 实际下小单测试
print(f"\n[5/5] 实际下单测试（0.01手，可取消）...")
print(f"\n  即将发送真实市价单:")
print(f"    品种: EURUSD")
print(f"    方向: BUY")
print(f"    手数: 0.01（最小）")
print(f"    魔法号: {magic}")
print(f"    说明: 测试单，ATR×2 SL，ATR×4 TP")

confirmed = os.environ.get("TEST_CONFIRM", "").lower() in ("yes", "y", "1", "true")
if not confirmed:
    print(f"\n  ⚠️ 如需执行实盘测试，请设置环境变量: TEST_CONFIRM=yes")
    print(f"  或手动运行:")
    print(f"    TEST_CONFIRM=yes $WINDOWS_PYTHON {__file__}")
else:
    # 取最新 EURUSD 数据
    tick = mt5_conn.symbol_info_tick("EURUSD")
    bars = mt5_conn.copy_rates_from_pos("EURUSD", mt5_conn.TIMEFRAME_H1, 0, 30)
    atr = 0
    if bars is not None and len(bars) >= 14:
        from signal_scanner import calc_atr as ca
        atr = ca([
            {"close": b["close"] if isinstance(b, (dict, np.void)) else b.close,
             "high": b["high"] if isinstance(b, (dict, np.void)) else b.high,
             "low": b["low"] if isinstance(b, (dict, np.void)) else b.low}
            for b in bars
        ])
    
    sig = {
        "strategy_id": "test_live_01",
        "symbol": "EURUSD",
        "timeframe": "H1",
        "direction": "long",
        "current_price": tick.ask if tick else 0,
        "rsi": 30.0,
        "atr": atr,
        "session": "test",
        "match_reasons": "live test order",
    }
    
    result = place_order(mt5_conn, sig, 0.01, magic, risk_cfg)
    print(f"\n  下单结果: {json.dumps(result, indent=4)}")
    
    if result.get("success"):
        print(f"\n  ✅ 测试单已成交! Ticket: {result.get('ticket')}")
    else:
        print(f"\n  ❌ 下单失败: {result.get('error')}")

mt5_conn.shutdown()
print("\n" + "=" * 60)
print("测试完成")
