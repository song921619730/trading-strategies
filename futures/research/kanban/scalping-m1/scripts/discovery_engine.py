#!/usr/bin/env python3
"""discovery_engine.py — 全指标自动化条件发现引擎

从已计算的指标 DataFrame 自动生成候选交易条件，批量回测，排序输出。

流程:
  1. 加载数据 + 计算全量指标 → 获得 300+ 列的 DataFrame
  2. 按列类型自动生成候选条件（数值列→阈值，bool列→触发）
  3. 分批回测 → 统计 WR/Sharpe/n/avg_return
  4. 排序筛选 → 输出 best_known 格式

用法:
  python3 discovery_engine.py --tf M5 --symbols XAUUSD,XAGUSD  # 指定品种
  python3 discovery_engine.py --tf M5                          # 全品种
  python3 discovery_engine.py --tf M5 --dry-run                # 只看生成的候选条件
"""

import sys, os, json, logging, time, re
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("discovery")

# ─── 路径 ───
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
STATE_DIR = PROJECT_DIR / "state"
DATA_DIR = PROJECT_DIR / "data"
BEST_KNOWN_PATH = STATE_DIR / "research_state.json"

_IND_SCRIPTS = str(Path(__file__).resolve().parent.parent.parent.parent.parent / "scripts")
if _IND_SCRIPTS not in sys.path:
    sys.path.insert(0, _IND_SCRIPTS)

sys.path.insert(0, str(SCRIPT_DIR))
from data_loader import load_data
from data_loader import list_available_symbols

# 直接调 batch_precompute 拿全量 509 列指标
_BS = str(Path(__file__).resolve().parent.parent.parent.parent.parent / "scripts")
if _BS not in sys.path:
    sys.path.insert(0, _BS)
from batch_precompute import compute_all_fast as _calc_all

# 共享品种表
from mt5_symbols import MT5_SYMBOLS_19

# ─── 排除字段（这些作为条件没有意义或重复） ───
EXCLUDE_COLS = {
    "open", "high", "low", "close", "volume", "time",
    "spread", "tick_volume", "real_volume", "body", "range",
    "upper_shadow", "lower_shadow",
    # 价格原始字段
    "ma3", "ma5", "ma8", "ma10", "ma13",
    "ma20", "ma21", "ma30", "ma34", "ma50",
    "ma55", "ma89", "ma100", "ma144", "ma200",
    "bb_20_2_mid", "bb_20_2_upper", "bb_20_2_lower",
    # 保留斜率类，不保留基础MA
}

# ─── 可用的 session 值 ───
SESSIONS = ["asia", "europe", "us"]


# ================================================================
# 1. 列类型自动检测
# ================================================================

def categorize_columns(df: pd.DataFrame) -> Dict[str, List[str]]:
    """将 DataFrame 列分类: bool, int, float_pct, float_raw"""
    cats = {"bool": [], "int": [], "pct": [], "raw": []}
    for col in df.columns:
        col_lower = col.lower()
        if col_lower in EXCLUDE_COLS:
            continue
        if any(excl in col_lower for excl in ["time", "date", "index"]):
            continue

        dtype = df[col].dtype
        series = df[col].dropna()

        if series.empty:
            continue

        # 判断是否是 bool / 0-1 int
        unique_vals = series.unique()
        if dtype == bool or (dtype in (int, float) and set(unique_vals) <= {0, 1}):
            cats["bool"].append(col)
        elif dtype in (int, np.int64):
            cats["int"].append(col)
        elif "pct" in col_lower or "ratio" in col_lower:
            cats["pct"].append(col)
        else:
            cats["raw"].append(col)
    return cats


# ================================================================
# 2. 候选条件生成
# ================================================================

def gen_thresholds(series: pd.Series, n_thresholds: int = 4) -> List[float]:
    """根据数据分布生成有意义的阈值"""
    q = series.quantile([0.1, 0.25, 0.5, 0.75, 0.9]).dropna()
    if len(q) < 3:
        return []
    # 取四分位附近的阈值
    thresholds = set()
    for pct in [0.15, 0.3, 0.5, 0.7, 0.85]:
        thresholds.add(round(series.quantile(pct), 4))
    return sorted(thresholds - {0})


def generate_conditions(df: pd.DataFrame, symbol: str) -> List[Dict]:
    """从 DataFrame 列自动生成候选条件配置（双向：做多+做空，全列覆盖）"""
    cats = categorize_columns(df)
    candidates = []

    # 2a. Bool 列: col == 1 — 双向生成
    for col in cats["bool"]:
        if df[col].sum() < 10:
            continue
        for session in SESSIONS:
            for direction in ["long", "short"]:
                candidates.append({
                    "condition": f"{col} == 1 and session == '{session}'",
                    "symbol": symbol,
                    "direction": direction,
                    "type": f"bool_{col}_{direction}",
                    "source_col": col,
                })

    # 2b. RSI 类 — 做多(超卖) + 做空(超买)，测试全部门槛
    for col in cats["raw"] + cats["pct"]:
        if "rsi" not in col.lower():
            continue
        series = df[col].dropna()
        # 做多: RSI < 阈值(超卖)
        for threshold in [5, 10, 15, 18, 20, 25, 30]:
            if series.min() > threshold:
                continue
            for session in SESSIONS:
                candidates.append({
                    "condition": f"{col} < {threshold} and session == '{session}'",
                    "symbol": symbol,
                    "direction": "long",
                    "type": f"rsi_oversold_{col}",
                    "source_col": col,
                })
        # 做空: RSI > 阈值(超买)
        for threshold in [70, 75, 80, 85]:
            if series.max() < threshold:
                continue
            for session in SESSIONS:
                candidates.append({
                    "condition": f"{col} > {threshold} and session == '{session}'",
                    "symbol": symbol,
                    "direction": "short",
                    "type": f"rsi_overbought_{col}",
                    "source_col": col,
                })

    # 2c. 数值列 — 双向（低位做多, 高位做空），全列覆盖（无break）
    for col in cats["raw"] + cats["pct"]:
        if "rsi" in col.lower() or "slope" in col.lower() or "trend" in col.lower():
            continue
        series = df[col].dropna()
        if series.nunique() < 5:
            continue
        q1 = series.quantile(0.25)
        q3 = series.quantile(0.75)
        for session in SESSIONS:
            # 做多：低位反转（col < Q1）
            candidates.append({
                "condition": f"{col} < {round(q1, 4)} and session == '{session}'",
                "symbol": symbol,
                "direction": "long",
                "type": f"low_{col}",
                "source_col": col,
            })
            # 做空：高位反转（col > Q3）
            candidates.append({
                "condition": f"{col} > {round(q3, 4)} and session == '{session}'",
                "symbol": symbol,
                "direction": "short",
                "type": f"high_{col}",
                "source_col": col,
            })

    # 2d. 斜率类 — 双向，全列覆盖（无break）
    for col in cats["pct"] + cats["raw"]:
        if "slope" not in col.lower() and "trend" not in col.lower():
            continue
        for session in SESSIONS:
            candidates.append({
                "condition": f"{col} > 0 and session == '{session}'",
                "symbol": symbol,
                "direction": "long",
                "type": f"slope_{col}",
                "source_col": col,
            })
            candidates.append({
                "condition": f"{col} < 0 and session == '{session}'",
                "symbol": symbol,
                "direction": "short",
                "type": f"slope_{col}_neg",
                "source_col": col,
            })

    # 2e. Weekday / 周期性字段 — 双向
    for col in cats["bool"]:
        if not any(day in col.lower() for day in ["monday", "tuesday", "wednesday",
                                                    "thursday", "friday", "weekend"]):
            continue
        if df[col].sum() < 10:
            continue
        for session in SESSIONS:
            for direction in ["long", "short"]:
                candidates.append({
                    "condition": f"{col} == 1 and session == '{session}'",
                    "symbol": symbol,
                    "direction": direction,
                    "type": f"weekday_{col}_{direction}",
                    "source_col": col,
                })

    # 2f. consecutive 类 — 全门槛 + 双向（反转+趋势延续）
    for col in cats["int"]:
        if "consecutive" not in col.lower():
            continue
        if "bear" not in col.lower() and "bull" not in col.lower():
            continue
        series = df[col].dropna()
        for thresh in [2, 3, 4, 5]:
            if series.max() < thresh:
                continue
            for session in SESSIONS:
                for direction in ["long", "short"]:
                    candidates.append({
                        "condition": f"{col} >= {thresh} and session == '{session}'",
                        "symbol": symbol,
                        "direction": direction,
                        "type": f"cb_{col}_{direction}",
                        "source_col": col,
                    })

    return candidates


# ================================================================
# 3. 批量回测
# ================================================================

def batch_test(df: pd.DataFrame, candidates: List[Dict],
               hold_periods: List[int] = None) -> List[Dict]:
    """对候选条件列表做批量回测（向量化版）"""
    if hold_periods is None:
        hold_periods = [3, 5, 10, 20, 30]

    results = []
    for cand in candidates:
        condition = cand["condition"]
        direction = cand["direction"]
        symbol = cand["symbol"]

        try:
            mask = df.eval(condition)
            entry_count = mask.sum()
            if entry_count < 20:
                continue

            entry_indices = np.where(mask.values)[0]
            entry_prices = df["close"].values[entry_indices]
            closes = df["close"].values
            n = len(closes)

            for hold in hold_periods:
                exit_positions = entry_indices + hold
                valid = exit_positions < n
                if valid.sum() < 20:
                    continue
                entry = entry_prices[valid]
                exit_ = closes[exit_positions[valid]]

                if direction == "long":
                    returns = (exit_ - entry) / entry
                else:
                    returns = (entry - exit_) / entry

                n_trades = len(returns)
                if n_trades < 20:
                    continue
                win_rate = float((returns > 0).mean())
                avg_return = float(returns.mean())
                std = float(returns.std()) if returns.std() > 0 else 1e-10
                sharpe = float(avg_return / std)

                results.append({
                    "condition": condition,
                    "symbol": symbol,
                    "direction": direction,
                    "hold": hold,
                    "type": cand.get("type", "?"),
                    "n": int(n_trades),
                    "win_rate": round(win_rate * 100, 1),
                    "avg_return": round(avg_return * 100, 3),
                    "sharpe": round(sharpe, 2),
                })
        except Exception as e:
            log.debug("跳过 %s: %s", condition, e)
            continue

    return results


# ================================================================
# 4. 输出 best_known
# ================================================================

def findings_to_best_known(results: List[Dict], top_n: int = 20) -> Dict[str, str]:
    """将回测结果转换为 best_known 格式"""
    # 排序：n >= 30 且 WR 最高
    valid = [r for r in results if r["n"] >= 30]
    if not valid:
        return {}

    # 按 Sharpe 排序（兼顾胜率和样本量）
    valid.sort(key=lambda r: (r["sharpe"] * np.log10(r["n"] + 1)), reverse=True)

    best_known = {}
    for i, r in enumerate(valid[:top_n]):
        cond = r["condition"]
        sym = r["symbol"]
        tf = "M5"  # 默认
        dir_cn = "做多" if r["direction"] == "long" else "做空"
        sid = f"auto_{sym}_{tf}_{r['direction']}_{i}"
        desc = f"{sym} {tf} {dir_cn}: {cond} WR={r['win_rate']}% n={r['n']} hold={r['hold']} avg_ret={r['avg_return']}% Sharpe={r['sharpe']}"
        best_known[sid] = desc

    return best_known


# ================================================================
# 5. 全流程
# ================================================================

LIMITED_SYMBOLS = MT5_SYMBOLS_19  # 全部 19 个 MT5 品种


def run_discovery(timeframe: str = "M5",
                  symbols: Optional[List[str]] = None,
                  dry_run: bool = False,
                  top_n: int = 20) -> Dict:
    """运行全指标发现流程"""
    if symbols is None:
        symbols = LIMITED_SYMBOLS

    log.info("🚀 开始全指标发现: %s %s", timeframe, symbols)

    start = time.time()
    all_results = []

    for sym in symbols:
        log.info("📊 处理 %s %s...", sym, timeframe)
        t0 = time.time()
        try:
            data = load_data(timeframe=timeframe, symbols=[sym])
            if sym not in data:
                log.warning("  ❌ %s 无数据", sym)
                continue
            raw = data[sym]
            # 先采样再算指标（加速 5x）
            if len(raw) > 20000:
                raw = raw.iloc[-20000:].copy()
            df = _calc_all(raw, timeframe)
            if df is None or df.empty:
                continue
            log.info("  ✅ %d 行 × %d 列 (%ds)", len(df), len(df.columns), time.time() - t0)

            # 生成候选条件（双向）
            candidates = generate_conditions(df, sym)
            log.info("  🎯 %d 个候选条件(双向)", len(candidates))

            if dry_run:
                log.info("  📋 候选条件(前10):")
                for c in candidates[:10]:
                    log.info("    %s | %s | %s", c["type"], c["direction"], c["condition"])
                continue

            # 批量回测
            t1 = time.time()
            sym_results = batch_test(df, candidates)
            all_results.extend(sym_results)
            log.info("  🏆 %d 个合格发现 (%ds)", len(sym_results), time.time() - t1)

        except Exception as e:
            log.error("  ❌ %s 失败: %s", sym, e)
            import traceback
            traceback.print_exc()
            continue

    if dry_run:
        return {"status": "dry_run", "candidates_generated": "in_symbol_loop"}

    # 结果汇总
    log.info("=" * 60)
    log.info("📈 总结果: %d 个", len(all_results))

    if all_results:
        # 按 Sharpe 排序
        all_results.sort(key=lambda r: (r["sharpe"] * np.log10(max(r["n"], 1) + 1)), reverse=True)

        log.info("\n🏆 TOP 15 发现:")
        log.info(f"| {'类型':<20} | {'条件':<40} | {'WR':<6} | {'n':<5} | {'Sharpe':<7} | {'Avg%':<7} |")
        log.info(f"|{'':->20}|{'':->40}|{'':->6}|{'':->5}|{'':->7}|{'':->7}|")
        for r in all_results[:15]:
            log.info(f"| {r.get('type','?'):<20} | {r['condition']:<40} | {r['win_rate']:<6} | {r['n']:<5} | {r['sharpe']:<7} | {r['avg_return']:<7} |")

    return {
        "status": "completed",
        "timeframe": timeframe,
        "symbols": symbols,
        "total_findings": len(all_results),
        "duration_s": round(time.time() - start, 1),
        "top_findings": all_results[:top_n],
        "best_known": findings_to_best_known(all_results, top_n),
    }


# ================================================================
# 6. CLI
# ================================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="全指标自动化条件发现引擎")
    parser.add_argument("--tf", default="M5", help="时间框架 (M1/M5/M30/H1/H4/D1/W1/MN1)")
    parser.add_argument("--symbols", default=None, help="品种列表(逗号分隔，默认全部)")
    parser.add_argument("--dry-run", action="store_true", help="只看候选条件不跑回测")
    parser.add_argument("--top", type=int, default=20, help="输出前N个")
    args = parser.parse_args()

    symbols = args.symbols.split(",") if args.symbols else None

    result = run_discovery(
        timeframe=args.tf,
        symbols=symbols,
        dry_run=args.dry_run,
        top_n=args.top,
    )

    if not args.dry_run:
        print(json.dumps(result, indent=2, ensure_ascii=False))

        # 写入 research_state
        if result.get("top_findings"):
            os.makedirs(STATE_DIR, exist_ok=True)
            state = {
                "status": result["status"],
                "current_round": "auto_discovery",
                "last_run": datetime.utcnow().isoformat(),
                "best_known": result.get("best_known", {}),
                "hypotheses": [],
                "warnings": [],
                "next_actions": [f"检查 auto_discovery 的 {result['total_findings']} 个发现"],
                "findings_summary": {
                    "total": result["total_findings"],
                    "duration_s": result["duration_s"],
                    "top": [{
                        "condition": r["condition"],
                        "win_rate": r["win_rate"],
                        "n": r["n"],
                        "sharpe": r["sharpe"],
                        "avg_return": r["avg_return"],
                    } for r in result["top_findings"][:10]],
                },
            }
            with open(STATE_DIR / "discovery_result.json", "w") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
            log.info("✅ 结果已保存到 discovery_result.json")
