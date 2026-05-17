#!/usr/bin/env python3
"""T2 动量趋势挖掘 - Iter20 (RELAXED COMBOS)
5 novel combos exploring new parameter dimensions with realistic signal counts.
"""
import json, hashlib, math, sys, os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ch_helper import ch_query

MAX_DATE = "20260512"
DATA_START = "20230101"

def combo_hash(params):
    pairs = sorted(params.items(), key=lambda x: str(x[0]))
    return hashlib.md5(",".join(f"{k}={v}" for k, v in pairs).encode()).hexdigest()[:12]

# ─── 5 RELAXED NOVEL COMBOS ───
COMBOS = [
    {
        "name": "C1: 中位放量突破",
        "desc": "底40%+中阳+放量+中小盘 — 中位趋势启动",
        "params": {
            "close_position": "底40%",
            "pct_chg_1d_min": 2,
            "volume_ratio_min": 1.0,
            "amplitude_min": 5,
            "circ_mv_max_wan": 500000,
        },
    },
    {
        "name": "C2: 持续缩量+温和放量",
        "desc": "5日持续缩量→温和放量企稳 — 底部量能枯竭后反转",
        "params": {
            "vol_trend_5d": "持续缩量",
            "pct_chg_1d_min": 0,
            "volume_ratio_min": 0.8,
            "amplitude_min": 4,
            "circ_mv_max_wan": 500000,
        },
    },
    {
        "name": "C3: 高股息防御反转",
        "desc": "高股息安全垫+深底+放量企稳 — 防御性底部反转",
        "params": {
            "dividend_yield_min": 0.02,
            "close_position": "底20%",
            "pct_chg_1d_min": 0,
            "volume_ratio_min": 1.0,
            "amplitude_min": 4,
            "circ_mv_max_wan": 500000,
        },
    },
    {
        "name": "C4: 底部温和放量反弹",
        "desc": "底20%+温和放量+小阳+中小盘 — 底部低吸信号",
        "params": {
            "close_position": "底20%",
            "pct_chg_1d_min": 1,
            "volume_ratio_min": 0.8,
            "amplitude_min": 3,
            "turnover_rate_min": 0.3,
            "turnover_rate_max": 20,
            "circ_mv_max_wan": 500000,
        },
    },
    {
        "name": "C5: 近底大阳放量",
        "desc": "底40%+大阳(≥3%)+放量+小盘 — 低位强势启动",
        "params": {
            "close_position": "底40%",
            "pct_chg_1d_min": 3,
            "volume_ratio_min": 1.5,
            "amplitude_min": 5,
            "circ_mv_max_wan": 500000,
        },
    },
]

def build_signal_sql(combo):
    """Build SQL for signal detection with window functions."""
    p = combo["params"]
    conditions = []
    joins = []
    data_cols = ["d.ts_code", "d.trade_date", "d.close", "d.high", "d.low", "d.pct_chg", "d.vol", "d.amount"]

    # Base table (FINAL causes issues with JOIN+WINDOW, so use direct table)
    from_clause = "FROM tushare.tushare_stock_daily d"

    # Basic filters
    base_filters = [
        f"d.trade_date >= '{DATA_START}'",
        f"d.trade_date <= '{MAX_DATE}'",
        "d.ts_code NOT LIKE '30%'",
        "d.ts_code NOT LIKE '688%'",
        "d.ts_code NOT LIKE '920%'",
        "d.amount > 0",
        "d.close IS NOT NULL",
        "d.pct_chg IS NOT NULL",
    ]

    # pct_chg condition
    if "pct_chg_1d_min" in p:
        conditions.append(f"d.pct_chg >= {p['pct_chg_1d_min']}")

    # Amplitude condition
    if "amplitude_min" in p:
        amp = p["amplitude_min"]
        conditions.append(f"(d.high - d.low) / NULLIF(d.low, 0) * 100 >= {amp}")

    # Daily basic JOIN
    need_db = any(k in p for k in [
        "volume_ratio_min", "turnover_rate_min", "turnover_rate_max",
        "circ_mv_max_wan", "dividend_yield_min"
    ])
    if need_db:
        joins.append("LEFT JOIN tushare.tushare_daily_basic b "
                      "ON d.ts_code=b.ts_code AND d.trade_date=b.trade_date")
        data_cols.extend(["b.volume_ratio", "b.turnover_rate", "b.circ_mv", "b.dv_ratio"])
        if "volume_ratio_min" in p:
            conditions.append(f"b.volume_ratio >= {p['volume_ratio_min']}")
        if "turnover_rate_min" in p:
            conditions.append(f"b.turnover_rate >= {p['turnover_rate_min']}")
        if "turnover_rate_max" in p:
            conditions.append(f"b.turnover_rate <= {p['turnover_rate_max']}")
        if "circ_mv_max_wan" in p:
            conditions.append(f"b.circ_mv <= {p['circ_mv_max_wan']}")
        if "dividend_yield_min" in p:
            conditions.append(f"b.dv_ratio >= {p['dividend_yield_min']}")

    # Moneyflow JOIN (net_mf_amount)
    need_mf = "net_mf_min" in p
    if need_mf:
        joins.append("LEFT JOIN (SELECT * FROM tushare.tushare_moneyflow FINAL) m "
                      "ON d.ts_code=m.ts_code AND d.trade_date=m.trade_date")
        data_cols.append("m.net_mf_amount")
        conditions.append(f"m.net_mf_amount >= {p['net_mf_min']}")

    # Window functions
    windows_cols = ""
    need_pos = "close_position" in p
    need_vol_trend = "vol_trend_5d" in p

    if need_pos:
        windows_cols += ", min(d.low) OVER w20 AS low_20d, max(d.high) OVER w20 AS high_20d"

    if need_vol_trend:
        windows_cols += ", lagInFrame(d.vol, 1) OVER vw AS vol_1d_ago"
        windows_cols += ", lagInFrame(d.vol, 2) OVER vw AS vol_2d_ago"
        windows_cols += ", lagInFrame(d.vol, 3) OVER vw AS vol_3d_ago"
        windows_cols += ", lagInFrame(d.vol, 4) OVER vw AS vol_4d_ago"

    windows_cols += ", row_number() OVER pw AS rn"

    window_defs = [
        "w20 AS (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)",
        "pw AS (PARTITION BY d.ts_code ORDER BY d.trade_date)",
    ]
    if need_vol_trend:
        window_defs.append(
            "vw AS (PARTITION BY d.ts_code ORDER BY d.trade_date ROWS BETWEEN 4 PRECEDING AND 1 PRECEDING)"
        )

    all_windows = ", ".join(window_defs)

    data_cols_str = ", ".join(data_cols)
    join_str = " ".join(joins)
    cond_str = " AND ".join(base_filters + conditions)

    subquery = f"""
    SELECT {data_cols_str} {windows_cols}
    {from_clause}
    {join_str}
    WHERE {cond_str}
    WINDOW {all_windows}
    """

    # Outer query with post-filter conditions
    outer_conds = ["rn >= 60"]

    if need_pos:
        pos = p["close_position"]
        if pos == "底20%":
            outer_conds.append("(close - low_20d) / NULLIF(high_20d - low_20d, 0) <= 0.20")
        elif pos == "底40%":
            outer_conds.append("(close - low_20d) / NULLIF(high_20d - low_20d, 0) <= 0.40")
        elif pos == "底30%":
            outer_conds.append("(close - low_20d) / NULLIF(high_20d - low_20d, 0) <= 0.30")

    if need_vol_trend:
        trend = p["vol_trend_5d"]
        if trend == "持续缩量":
            outer_conds.append("vol_4d_ago IS NOT NULL AND vol_1d_ago IS NOT NULL")
            outer_conds.append(
                "vol < vol_1d_ago AND vol_1d_ago < vol_2d_ago "
                "AND vol_2d_ago < vol_3d_ago AND vol_3d_ago < vol_4d_ago"
            )

    outer_cond_str = " AND ".join(outer_conds)

    full_sql = f"""
    SELECT ts_code, trade_date, close
    FROM ({subquery})
    WHERE {outer_cond_str}
    ORDER BY ts_code, trade_date
    """

    return full_sql


def calc_fwd_returns(signals, stock_data, hold_days):
    """Calculate forward returns for signal list."""
    results = {}
    for hd in hold_days:
        fwd = []
        for code, td, close_signal in signals:
            bars = stock_data.get(code, [])
            sig_idx = None
            for bi, b in enumerate(bars):
                if int(str(b["trade_date"]).replace("-", "")) == td:
                    sig_idx = bi
                    break
            if sig_idx is None or sig_idx + hd >= len(bars):
                continue
            fwd_close = bars[sig_idx + hd]["close"]

            if fwd_close is not None and close_signal is not None and close_signal > 0:
                ret = (fwd_close / close_signal) - 1
                fwd.append(ret)

        n = len(fwd)
        if n < 5:
            results[hd] = {"wr": 0, "ret": 0, "sharpe": 0, "n": n}
            continue

        wr = sum(1 for r_ in fwd if r_ > 0) / n * 100
        avg_ret = sum(fwd) / n * 100
        mean_ret = sum(fwd) / n
        var = sum((r_ - mean_ret)**2 for r_ in fwd) / n
        std = math.sqrt(var) if var > 0 else 0.0001
        sharpe = (mean_ret / std) * math.sqrt(252 / hd) if std > 0 else 0

        sorted_fwd = sorted(fwd)
        p90 = sorted_fwd[min(int(n * 0.9), n-1)] * 100
        p10 = sorted_fwd[min(int(n * 0.1), n-1)] * 100

        results[hd] = {
            "wr": round(wr, 2),
            "ret": round(avg_ret, 4),
            "sharpe": round(sharpe, 3),
            "n": n,
            "p90": round(p90, 2),
            "p10": round(p10, 2),
        }

    return results


def load_stock_data():
    """Load stock_daily for forward return calculation."""
    print("[Load] Loading stock_daily (for fwd returns)...")
    rows = ch_query(f"""SELECT ts_code, trade_date, close 
        FROM tushare.tushare_stock_daily FINAL 
        WHERE trade_date >= '{DATA_START}' AND trade_date <= '{MAX_DATE}' 
        AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%' AND ts_code NOT LIKE '920%' 
        AND close IS NOT NULL
        ORDER BY ts_code, trade_date""", timeout=600)
    by_code = {}
    for r in rows:
        code = r["ts_code"]
        if code not in by_code:
            by_code[code] = []
        by_code[code].append(r)
    print(f"  {len(rows)} rows, {len(by_code)} stocks")
    return by_code


def main():
    print("=" * 70)
    print("T2 动量趋势挖掘 - Iter 20")
    print(f"执行: {datetime.now().strftime('%Y-%m-%d %H:%M')} | 数据基准: {MAX_DATE}")
    print("历史最佳: WR=94.93%, R5=21.32%, Sharpe=14.873, N=276")
    print("=" * 70)

    stock_data = load_stock_data()
    hold_days = [5, 10, 20]
    all_results = []

    for ci, combo in enumerate(COMBOS):
        p = combo["params"]
        h = combo_hash(p)
        print(f"\n{'='*60}")
        print(f"[{ci+1}/5] {combo['name']} [{h}]")
        print(f"  {combo['desc']}")
        print(f"  参数: {p}")

        sql = build_signal_sql(combo)
        print(f"  [SQL] Querying...")
        signals_raw = ch_query(sql, timeout=600)

        signals = []
        for r in signals_raw:
            try:
                td = int(str(r["trade_date"]).replace("-", ""))
                close_val = float(r["close"])
                signals.append((r["ts_code"], td, close_val))
            except (ValueError, KeyError):
                continue

        print(f"  SQL signals: {len(signals_raw)} raw, {len(signals)} valid")

        if len(signals) < 5:
            print(f"  ⚠️ Too few signals ({len(signals)}), skipping")
            all_results.append({
                "name": combo["name"], "hash": h, "params": p,
                "signal_count": len(signals),
                "hold_results": {d: {"wr": 0, "ret": 0, "sharpe": 0, "n": 0} for d in hold_days}
            })
            continue

        hr = calc_fwd_returns(signals, stock_data, hold_days)

        all_results.append({
            "name": combo["name"], "hash": h, "params": p,
            "signal_count": len(signals),
            "hold_results": hr
        })

        print(f"  Results:")
        for hd in hold_days:
            if hd in hr:
                r = hr[hd]
                print(f"    T+{hd:2d}: N={r['n']:6d} | WR={r['wr']:5.2f}% | Ret={r['ret']:6.4f}% | Sharpe={r['sharpe']:6.3f} | P10={r.get('p10', 0):6.2f}%")

    # ─── Summary ───
    print("\n" + "=" * 70)
    print("T2 Iter 20 — 最终汇总")
    print("=" * 70)
    print(f"{'组合':25s} {'信号数':>8s} {'WR_5d':>8s} {'Ret_5d':>10s} {'Ret_10d':>10s} {'Ret_20d':>10s} {'Sharpe':>8s} {'Status':>10s}")
    print("-" * 84)

    best_ret = best_wr = best_comp = None
    PASS_N = 200
    PASS_WR = 55
    PASS_R5 = 5.0

    for res in all_results:
        hr = res["hold_results"]
        n = res["signal_count"]
        if 5 in hr and hr[5]["n"] >= 5:
            d5 = hr[5]
            d10 = hr.get(10, {})
            d20 = hr.get(20, {})
            w, r5, sh, n5 = d5["wr"], d5["ret"], d5["sharpe"], d5["n"]
            r10 = d10.get("ret", 0) if d10 else 0
            r20 = d20.get("ret", 0) if d20 else 0
            ok = w >= PASS_WR and r5 >= PASS_R5 and n >= PASS_N
            status = "✅" if ok else "❌"
            print(f"{res['name'][:25]:25s} {n:>8d} {w:>7.2f}% {r5:>9.4f}% {r10:>9.4f}% {r20:>9.4f}% {sh:>7.3f} {status:>10s}")
            if best_ret is None or r5 > best_ret[0]:
                best_ret = (r5, w, n, res["name"])
            if best_wr is None or w > best_wr[0]:
                best_wr = (w, r5, n, res["name"])
            score = w * 0.3 + r5 * 4 * 0.4 + min(n / 200, 10) * 10 * 0.3
            if best_comp is None or score > best_comp[0]:
                best_comp = (score, w, r5, n, res["name"])
        else:
            print(f"{res['name'][:25]:25s} {n:>8d} {'N/A':>8s} {'N/A':>10s} {'N/A':>10s} {'N/A':>10s} {'N/A':>8s} {'❌':>10s}")

    print()
    if best_ret:
        print(f"🏆 Best Ret_5d: {best_ret[3]} | Ret={best_ret[0]:.2f}% | WR={best_ret[1]:.2f}% | N={best_ret[2]}")
    if best_wr:
        print(f"🏆 Best WR_5d:  {best_wr[3]} | WR={best_wr[0]:.2f}% | Ret={best_wr[1]:.2f}% | N={best_wr[2]}")
    if best_comp:
        print(f"🏆 Best Comp:   {best_comp[4]} | WR={best_comp[1]:.2f}% | Ret={best_comp[2]:.2f}% | N={best_comp[3]}")

    print(f"\n{'='*70}")
    print(f"✅ 达标判定: WR>={PASS_WR}% AND Ret_5d>={PASS_R5}% AND N>={PASS_N}")
    any_pass = any(
        5 in res["hold_results"] and res["hold_results"][5]["n"] >= 5
        and res["hold_results"][5]["wr"] >= PASS_WR
        and res["hold_results"][5]["ret"] >= PASS_R5
        and res["signal_count"] >= PASS_N
        for res in all_results
    )
    if any_pass:
        print("🎉 有组合完全达标!")
    else:
        print("⚠️ 本轮无组合完全达标")

    print(f"\n{'='*70}")
    print("历史最佳对比:")
    print(f"  当前最佳: WR=94.93%, R5=21.32%, Sharpe=14.873, N=276")
    if best_comp:
        print(f"  本轮最佳: WR={best_comp[1]:.2f}%, R5={best_comp[2]:.2f}%, N={best_comp[3]}")
        if best_comp[2] >= 21.32 and best_comp[1] >= 94.93:
            print("  🏆 超越历史最佳!")
        else:
            print("  ❌ 未超越历史最佳")

    return all_results


if __name__ == "__main__":
    results = main()
    output_dir = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_20"
    os.makedirs(output_dir, exist_ok=True)
    with open(f"{output_dir}/T2_results_raw.json", "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n[Save] Raw results saved to {output_dir}/T2_results_raw.json")
