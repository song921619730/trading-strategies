#!/usr/bin/env python3
"""Update research_state.json after round28 testing."""
import json

PATH = "/mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/futures-intraday/state/research_state.json"

with open(PATH, "r") as f:
    state = json.load(f)

# 1. Mark round27_a01 as completed
for h in state.get("hypothesis_queue", []):
    if h.get("id") == "round27_a01":
        h["status"] = "completed"
        h["completed_at"] = "2026-05-11"
        h["result"] = "精密扫描10个持有期(3/5/6/7/8/9/10/12/15/20)，hold=7以62.98%保持最优。未发现超过62.98%的持有期参数。"

# 2. Add round28_summary
state["round28_summary"] = {
    "timeframe": "H1",
    "hypothesis": "round27_a01: XAUUSD H1 美盘+RSI<40+ATR>0.35%做多 精密持有期扫描",
    "verdict": "confirmed",
    "core_findings": [
        {
            "test": "A_hold_scan",
            "description": "XAUUSD H1 session==us + rsi14<40 + atr14/close>0.0035 long hold扫描(3/5/6/7/8/9/10/12/15/20)",
            "best_hold": 7,
            "best_win_rate": 0.6298,
            "signal_count": 705,
            "sharpe": 3.25,
            "label": "STRONG (62.98% — 基线验证确认)",
            "hold_scan": {
                "3": {"win_rate": 0.5943, "n": 705, "sharpe": 3.60, "label": "PROMISING"},
                "5": {"win_rate": 0.6184, "n": 705, "sharpe": 4.39, "label": "STRONG"},
                "6": {"win_rate": 0.6184, "n": 705, "sharpe": 3.86, "label": "STRONG"},
                "7": {"win_rate": 0.6298, "n": 705, "sharpe": 3.25, "label": "STRONG ★"},
                "8": {"win_rate": 0.6113, "n": 705, "sharpe": 2.64, "label": "STRONG"},
                "9": {"win_rate": 0.6043, "n": 705, "sharpe": 1.84, "label": "STRONG"},
                "10": {"win_rate": 0.5957, "n": 705, "sharpe": 1.26, "label": "PROMISING"},
                "12": {"win_rate": 0.6028, "n": 705, "sharpe": 0.84, "label": "STRONG"},
                "15": {"win_rate": 0.6085, "n": 705, "sharpe": 0.63, "label": "STRONG"},
                "20": {"win_rate": 0.5546, "n": 705, "sharpe": -0.84, "label": "WEAK"}
            }
        },
        {
            "test": "B_cross_symbol",
            "description": "跨品种验证(session==us + rsi14<40 + atr14/close>0.0035, hold=7, 9 symbols)",
            "results": {
                "XAUUSD": {"win_rate": 0.6298, "n": 705, "sharpe": 3.25, "label": "STRONG ★"},
                "US30": {"win_rate": 0.6112, "n": 517, "sharpe": 1.93, "label": "STRONG"},
                "AUDUSD": {"win_rate": 0.5851, "n": 94, "sharpe": 7.74, "label": "PROMISING"},
                "GBPUSD": {"win_rate": 0.5849, "n": 53, "sharpe": -6.64, "label": "TRAP"},
                "JP225": {"win_rate": 0.5753, "n": 671, "sharpe": 0.79, "label": "PROMISING"},
                "XAGUSD": {"win_rate": 0.5642, "n": 1847, "sharpe": 1.67, "label": "PROMISING"},
                "US500": {"win_rate": 0.5601, "n": 691, "sharpe": 0.66, "label": "PROMISING"},
                "HK50": {"win_rate": 0.5565, "n": 735, "sharpe": 2.76, "label": "PROMISING"},
                "USTEC": {"win_rate": 0.5550, "n": 1301, "sharpe": -0.08, "label": "PROMISING"},
                "EURUSD": {"win_rate": 0.7857, "n": 14, "sharpe": 29.81, "label": "INSUFFICIENT"}
            }
        }
    ],
    "comparison_to_baseline": {
        "Round23_baseline": "XAUUSD H1 session=='us' + ATR>0.35% + RSI<40 long hold=7 wr=62.98% n=705 Sharpe=3.25",
        "Round28_current_best": "XAUUSD H1 session=='us' + ATR>0.35% + RSI<40 long hold=7 wr=62.98% n=705 Sharpe=3.25",
        "delta_wr": "0.00pp (62.98% vs 62.98%) — 精密扫描未发现更高胜率持有期",
        "assessment": "hold=7确认维持最优。hold=5(61.84%, Sharpe=4.39)为最佳风险调整方案。策略对持有期选择不敏感(3-15全部>59%)。"
    },
    "key_insights": [
        "XAUUSD H1精密持有期扫描确认hold=7(62.98%)为最优——10个持有期中无任何突破62.98%",
        "hold=5(61.84%, Sharpe=4.39)为最佳风险调整——Sharpe全场最高但胜率低1.14pp",
        "全部3-15持有期胜率>59%——信号极其稳健，策略对持有期选择不敏感",
        "hold=20(55.46%, avg_ret=-0.07%)——长持有期完全失效，收益转负",
        "跨品种验证完全复现round27结果——XAUUSD(62.98%)和US30(61.12%)为仅有两个STRONG信号品种",
        "GBPUSD(58.49%, n=53, avg_ret=-0.25%)再次确认高胜率低收益陷阱"
    ],
    "negative_findings": [
        "精密扫描未发现超过62.98%的持有期——该策略路线在XAUUSD H1上已充分探索",
        "hold=20 avg_return为负(-0.07%)——过长持有期完全丧失方向性优势",
        "EURUSD仅n=14信号样本不足——ATR>0.35%阈值对主要外汇对过高"
    ],
    "new_hypotheses_generated": [
        "round28_a01: US30 H1 美盘+RSI<40+ATR精细扫描(0.32%~0.38%步长0.01%)寻找61.12%以上更优参数(原round27_a02)",
        "round28_a02: US30 H1 美盘+RSI<40+ATR>0.35%做多 分小时级US session分析(16-23时逐小时)(原round27_a03)",
        "round28_a03: US30 M30 美盘+RSI<40+ATR>0.35%做多 hold扫描(3-20)跨时间框架验证(原round27_a04)"
    ],
    "summary": "Round 28 H1完成round27_a01假设测试：XAUUSD H1美盘+RSI<40+ATR>0.35%做多精密持有期扫描(10个持有期)。核心结论：(1)hold=7以62.98%保持最优——精密扫描未发现更高胜率持有期。(2)hold=5(61.84%, Sharpe=4.39)为最佳风险调整方案，Sharpe全场最高。(3)全部3-15持有期胜率>59%，信号极其稳健。(4)hold=20(55.46%, avg_ret=-0.07%)长持有期完全失效。(5)跨品种验证完全复现round27结果。(6)该策略路线在XAUUSD H1上已充分探索（从Round16 60.35%至Round28 62.98%确认最优）。疲劳度增至2/5(确认性验证未产生新突破但仍积累了收敛证据)。剩余待测假设：round27_a02(US30精细ATR阈值扫描)、round27_a03(US30分小时分析)、round27_a04(US30 M30跨框架验证)。"
}

# 3. Remove the duplicate round27_a01 from hypothesis_queue since it's now tested
state["hypothesis_queue"] = [h for h in state["hypothesis_queue"] if h.get("id") != "round27_a01"]

with open(PATH, "w") as f:
    json.dump(state, f, indent=2, ensure_ascii=False)

print("research_state.json updated successfully.")
print(f"  round27_a01 status → completed (removed from queue)")
print(f"  round28_summary added")
print(f"  Remaining hypotheses in queue: {len(state.get('hypothesis_queue', []))}")
