#!/usr/bin/env python3
"""
主升浪潜伏与起爆点 V22 — 板块热度 + 市值分层 + 突破强度优化
基于 V21 已知事实进行增量测试:
  - 不使用洗盘过滤 (V21已证无效)
  - 不使用硬止损 (V21已证有害)
  - 使用牛市过滤 (沪深300>MA60, V21已证有效)
"""
import requests
import json
import pandas as pd
import numpy as np
from datetime import datetime
from scipy import stats

CH_URL = 'http://172.24.224.1:8123/'
CH_AUTH = ('ai_reader', 'OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ')

def ch_query(sql):
    r = requests.get(CH_URL, params={'query': sql}, auth=CH_AUTH, timeout=60)
    r.raise_for_status()
    lines = r.text.strip().split('\n')
    if len(lines) < 2:
        return pd.DataFrame()
    cols = lines[0].split('\t')
    data = [line.split('\t') for line in lines[1:]]
    df = pd.DataFrame(data, columns=cols)
    return df

def main():
    print("=" * 60)
    print("V22: 板块热度 + 市值分层 + 突破强度优化")
    print("=" * 60)

    # ============================================================
    # 1. 获取全市场日线数据 (2019-10 至 2026-05)
    # ============================================================
    print("\n[1/6] 获取全市场日线数据...")
    sql_daily = """
    SELECT ts_code, trade_date, open, high, low, close, vol, pct_chg, amount
    FROM tushare.tushare_stock_daily FINAL
    WHERE trade_date >= '20191001'
    ORDER BY ts_code, trade_date
    FORMAT TabSeparatedWithNames
    """
    df_daily = ch_query(sql_daily)
    print(f"  日线记录: {len(df_daily)} 条")

    for c in ['open','high','low','close','vol','pct_chg','amount']:
        df_daily[c] = pd.to_numeric(df_daily[c], errors='coerce')
    df_daily['trade_date'] = pd.to_datetime(df_daily['trade_date'])

    # ============================================================
    # 2. 获取 daily_basic (市值/PE/换手率)
    # ============================================================
    print("\n[2/6] 获取基本面数据 (市值/PE/换手率)...")
    sql_basic = """
    SELECT ts_code, trade_date, total_mv, circ_mv, pe_ttm, pb, turnover_rate
    FROM tushare.tushare_daily_basic FINAL
    WHERE trade_date >= '20191001'
    ORDER BY ts_code, trade_date
    FORMAT TabSeparatedWithNames
    """
    df_basic = ch_query(sql_basic)
    print(f"  基本面记录: {len(df_basic)} 条")

    for c in ['total_mv','circ_mv','pe_ttm','pb','turnover_rate']:
        df_basic[c] = pd.to_numeric(df_basic[c], errors='coerce')
    df_basic['trade_date'] = pd.to_datetime(df_basic['trade_date'])

    # ============================================================
    # 3. 获取沪深300指数日线 (市场环境过滤)
    # ============================================================
    print("\n[3/6] 获取沪深300指数数据...")
    sql_idx = """
    SELECT trade_date, close
    FROM tushare.tushare_index_daily FINAL
    WHERE ts_code = '000300.SH' AND trade_date >= '20191001'
    ORDER BY trade_date
    FORMAT TabSeparatedWithNames
    """
    df_idx = ch_query(sql_idx)
    df_idx['trade_date'] = pd.to_datetime(df_idx['trade_date'])
    df_idx['close'] = pd.to_numeric(df_idx['close'], errors='coerce')
    df_idx['ma60'] = df_idx['close'].rolling(60).mean()
    df_idx['is_bull'] = (df_idx['close'] > df_idx['ma60']).astype(int)

    # ============================================================
    # 4. 计算技术指标 + 生成信号
    # ============================================================
    print("\n[4/6] 计算技术指标并生成信号...")

    # 先合并 daily + basic
    df = df_daily.merge(df_basic, on=['ts_code','trade_date'], how='inner')

    # 排序
    df = df.sort_values(['ts_code','trade_date']).reset_index(drop=True)

    # 按股票分组计算指标
    results = []
    all_signals = []

    for ts_code, grp in df.groupby('ts_code'):
        grp = grp.sort_values('trade_date').copy()
        if len(grp) < 80:
            continue

        # 均线
        grp['ma5'] = grp['close'].rolling(5).mean()
        grp['ma10'] = grp['close'].rolling(10).mean()
        grp['ma20'] = grp['close'].rolling(20).mean()
        grp['ma60'] = grp['close'].rolling(60).mean()

        # 均线粘合度: 4条均线在t-10到t的均值的标准差/均值
        ma_cols = ['ma5','ma10','ma20','ma60']

        # MA_CV: 变异系数 = std/mean of 4 MAs
        grp['ma_mean'] = grp[ma_cols].mean(axis=1)
        grp['ma_std'] = grp[ma_cols].std(axis=1)
        grp['ma_cv'] = grp['ma_std'] / grp['ma_mean']

        # MA_CV 10日平滑
        grp['ma_cv_10'] = grp['ma_cv'].rolling(10).mean()

        # ATR(14)
        high_low = grp['high'] - grp['low']
        high_close = (grp['high'] - grp['close'].shift(1)).abs()
        low_close = (grp['low'] - grp['close'].shift(1)).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        grp['atr'] = tr.rolling(14).mean()
        grp['atr_pct'] = grp['atr'] / grp['close']

        # 量比: vol / vol_ma_20
        grp['vol_ma20'] = grp['vol'].rolling(20).mean()
        grp['vol_ratio'] = grp['vol'] / grp['vol_ma20']

        # 换手率
        grp['turnover_rate'] = pd.to_numeric(grp['turnover_rate'], errors='coerce')

        # 未来收益 (T+5, T+10, T+20)
        grp['ret_5'] = grp['close'].shift(-5) / grp['close'] - 1
        grp['ret_10'] = grp['close'].shift(-10) / grp['close'] - 1
        grp['ret_20'] = grp['close'].shift(-20) / grp['close'] - 1

        # ============================================================
        # 基础信号: MA_CV_10 < 0.02, ATR% < 0.025, 放量突破
        # ============================================================
        base_cond = (
            (grp['ma_cv_10'] < 0.02) &
            (grp['atr_pct'] < 0.025) &
            (grp['vol_ratio'] > 1.5) &
            (grp['pct_chg'] > 2.0) &
            (grp['close'] > grp['ma60']) &
            (grp['pe_ttm'] > 0) &
            (grp['total_mv'] >= 300000)  # 300000万元 = 30亿元
        )

        # 合并市场环境
        for i, row in grp[base_cond].iterrows():
            td = row['trade_date']
            bull_flag = df_idx.loc[df_idx['trade_date'] == td, 'is_bull']
            if len(bull_flag) == 0:
                continue
            is_bull = bull_flag.values[0]

            sig = {
                'ts_code': ts_code,
                'trade_date': td,
                'is_bull': int(is_bull),
                'ma_cv_10': row['ma_cv_10'],
                'atr_pct': row['atr_pct'],
                'vol_ratio': row['vol_ratio'],
                'pct_chg': row['pct_chg'],
                'turnover_rate': row.get('turnover_rate', np.nan),
                'total_mv': row['total_mv'],
                'pe_ttm': row['pe_ttm'],
                'pb': row.get('pb', np.nan),
                'ret_5': row['ret_5'],
                'ret_10': row['ret_10'],
                'ret_20': row['ret_20'],
            }
            all_signals.append(sig)

    signals_df = pd.DataFrame(all_signals)
    if len(signals_df) == 0:
        print("  ERROR: 无信号生成!")
        return
    print(f"  基础信号总数: {len(signals_df)}")

    # ============================================================
    # 5. 分析维度测试
    # ============================================================
    print("\n[5/6] 多维度分析...")

    # --- 测试A: 市值分层 ---
    print("\n--- 测试A: 市值分层 ---")
    signals_df['mv_bin'] = pd.qcut(signals_df['total_mv'], q=4, labels=['小盘','中小','中大','大盘'], duplicates='drop')
    for mv in signals_df['mv_bin'].unique():
        sub = signals_df[signals_df['mv_bin'] == mv]
        valid = sub['ret_20'].dropna()
        if len(valid) < 50:
            continue
        print(f"  {mv}: n={len(valid)}, 均收益={valid.mean():.2%}, 胜率={(valid>0).mean():.1%}, "
              f"中位={valid.median():.2%}")

    # --- 测试B: 突破日涨幅分层 ---
    print("\n--- 测试B: 突破日涨幅分层 ---")
    signals_df['pct_bin'] = pd.cut(signals_df['pct_chg'], bins=[0, 3, 5, 7, 100], labels=['2-3%','3-5%','5-7%','>7%'])
    for pct in signals_df['pct_bin'].unique():
        sub = signals_df[signals_df['pct_bin'] == pct]
        valid = sub['ret_20'].dropna()
        if len(valid) < 50:
            continue
        print(f"  {pct}: n={len(valid)}, 均收益={valid.mean():.2%}, 胜率={(valid>0).mean():.1%}, "
              f"中位={valid.median():.2%}")

    # --- 测试C: 量比分层 ---
    print("\n--- 测试C: 量比分层 ---")
    signals_df['vr_bin'] = pd.cut(signals_df['vol_ratio'], bins=[1.5, 2, 3, 5, 100], labels=['1.5-2','2-3','3-5','>5'])
    for vr in signals_df['vr_bin'].unique():
        sub = signals_df[signals_df['vr_bin'] == vr]
        valid = sub['ret_20'].dropna()
        if len(valid) < 50:
            continue
        print(f"  {vr}: n={len(valid)}, 均收益={valid.mean():.2%}, 胜率={(valid>0).mean():.1%}, "
              f"中位={valid.median():.2%}")

    # --- 测试D: 换手率分层 ---
    print("\n--- 测试D: 突破日换手率分层 ---")
    signals_df_valid = signals_df.dropna(subset=['turnover_rate'])
    signals_df_valid['tr_bin'] = pd.qcut(signals_df_valid['turnover_rate'], q=4, labels=['Q1(低)','Q2','Q3','Q4(高)'], duplicates='drop')
    for tr in signals_df_valid['tr_bin'].unique():
        sub = signals_df_valid[signals_df_valid['tr_bin'] == tr]
        valid = sub['ret_20'].dropna()
        if len(valid) < 50:
            continue
        print(f"  {tr}: n={len(valid)}, 均收益={valid.mean():.2%}, 胜率={(valid>0).mean():.1%}, "
              f"中位={valid.median():.2%}")

    # --- 测试E: MA_CV 严格阈值 ---
    print("\n--- 测试E: MA_CV 严格阈值 ---")
    for thr in [0.005, 0.01, 0.015, 0.02, 0.025, 0.03]:
        sub = signals_df[signals_df['ma_cv_10'] < thr]
        valid = sub['ret_20'].dropna()
        if len(valid) < 50:
            continue
        print(f"  MA_CV<{thr}: n={len(valid)}, 均收益={valid.mean():.2%}, 胜率={(valid>0).mean():.1%}, "
              f"中位={valid.median():.2%}")

    # --- 测试F: ATR 严格阈值 ---
    print("\n--- 测试F: ATR% 严格阈值 ---")
    for thr in [0.01, 0.015, 0.02, 0.025, 0.03, 0.04]:
        sub = signals_df[signals_df['atr_pct'] < thr]
        valid = sub['ret_20'].dropna()
        if len(valid) < 50:
            continue
        print(f"  ATR%<{thr}: n={len(valid)}, 均收益={valid.mean():.2%}, 胜率={(valid>0).mean():.1%}, "
              f"中位={valid.median():.2%}")

    # --- 测试G: 牛市环境下多维度组合 ---
    print("\n--- 测试G: 牛市环境下的增强组合 ---")
    bull = signals_df[signals_df['is_bull'] == 1]

    # G1: 牛市 + 严格MA_CV(<0.01)
    sub = bull[bull['ma_cv_10'] < 0.01]
    valid = sub['ret_20'].dropna()
    print(f"  牛市+MA_CV<0.01: n={len(valid)}, 均收益={valid.mean():.2%}, 胜率={(valid>0).mean():.1%}")

    # G2: 牛市 + 高换手(Q3+Q4)
    bull_valid = bull.dropna(subset=['turnover_rate'])
    med_tr = bull_valid['turnover_rate'].median()
    sub = bull_valid[bull_valid['turnover_rate'] > med_tr]
    valid = sub['ret_20'].dropna()
    print(f"  牛市+高换手(>{med_tr:.1f}%): n={len(valid)}, 均收益={valid.mean():.2%}, 胜率={(valid>0).mean():.1%}")

    # G3: 牛市 + 大涨突破(>5%)
    sub = bull[bull['pct_chg'] > 5]
    valid = sub['ret_20'].dropna()
    print(f"  牛市+大涨突破(>5%): n={len(valid)}, 均收益={valid.mean():.2%}, 胜率={(valid>0).mean():.1%}")

    # G4: 牛市 + 大量比(>3)
    sub = bull[bull['vol_ratio'] > 3]
    valid = sub['ret_20'].dropna()
    print(f"  牛市+大量比(>3): n={len(valid)}, 均收益={valid.mean():.2%}, 胜率={(valid>0).mean():.1%}")

    # G5: 牛市 + 中小盘 (Q1+Q2)
    bull_with_mv = bull.dropna(subset=['total_mv'])
    med_mv = bull_with_mv['total_mv'].median()
    sub = bull_with_mv[bull_with_mv['total_mv'] < med_mv]
    valid = sub['ret_20'].dropna()
    med_mv_yi = med_mv / 10000  # 万元转亿
    print(f"  牛市+中小盘(<{med_mv_yi:.0f}亿): n={len(valid)}, 均收益={valid.mean():.2%}, 胜率={(valid>0).mean():.1%}")

    # G6: 牛市 + 低PB(<2)
    bull_valid_pb = bull.dropna(subset=['pb'])
    sub = bull_valid_pb[bull_valid_pb['pb'] < 2]
    valid = sub['ret_20'].dropna()
    print(f"  牛市+低PB(<2): n={len(valid)}, 均收益={valid.mean():.2%}, 胜率={(valid>0).mean():.1%}")

    # G7: 牛市 + 高PB(>3)
    sub = bull_valid_pb[bull_valid_pb['pb'] > 3]
    valid = sub['ret_20'].dropna()
    print(f"  牛市+高PB(>3): n={len(valid)}, 均收益={valid.mean():.2%}, 胜率={(valid>0).mean():.1%}")

    # G8: 牛市 + 多重增强 (MA_CV<0.01 + 高换手 + 大涨>5%)
    bull_multi = bull.dropna(subset=['turnover_rate'])
    med_tr = bull_multi['turnover_rate'].median()
    sub = bull_multi[
        (bull_multi['ma_cv_10'] < 0.01) &
        (bull_multi['turnover_rate'] > med_tr) &
        (bull_multi['pct_chg'] > 5)
    ]
    valid = sub['ret_20'].dropna()
    print(f"  牛市+MA_CV<0.01+高换手+大涨>5%: n={len(valid)}, 均收益={valid.mean():.2%}, 胜率={(valid>0).mean():.1%}")

    # G9: 牛市 + 多重增强 (大量比>3 + 大涨>5% + 中小盘)
    sub = bull_with_mv[
        (bull_with_mv['vol_ratio'] > 3) &
        (bull_with_mv['pct_chg'] > 5) &
        (bull_with_mv['total_mv'] < med_mv)
    ]
    valid = sub['ret_20'].dropna()
    print(f"  牛市+大量比>3+大涨>5%+中小盘: n={len(valid)}, 均收益={valid.mean():.2%}, 胜率={(valid>0).mean():.1%}")

    # --- 测试H: 基准对比 (V21结果) ---
    print("\n--- 测试H: 基准对比 ---")
    all_valid = signals_df['ret_20'].dropna()
    bull_all = bull['ret_20'].dropna()
    bear = signals_df[signals_df['is_bull'] == 0]
    bear_all = bear['ret_20'].dropna()
    print(f"  全市场: n={len(all_valid)}, 均收益={all_valid.mean():.2%}, 胜率={(all_valid>0).mean():.1%}")
    print(f"  牛市:   n={len(bull_all)}, 均收益={bull_all.mean():.2%}, 胜率={(bull_all>0).mean():.1%}")
    print(f"  熊市:   n={len(bear_all)}, 均收益={bear_all.mean():.2%}, 胜率={(bear_all>0).mean():.1%}")

    # ============================================================
    # 6. 保存结果
    # ============================================================
    import os
    EXP_DIR = os.path.dirname(os.path.abspath(__file__))
    print("\n[6/6] 保存结果...")
    signals_df.to_csv(os.path.join(EXP_DIR, 'signals_v22.csv'), index=False)

    # 保存汇总
    summary = {
        'total_signals': len(signals_df),
        'bull_signals': int((signals_df['is_bull']==1).sum()),
        'bear_signals': int((signals_df['is_bull']==0).sum()),
        'all_ret_20_mean': float(all_valid.mean()),
        'all_ret_20_median': float(all_valid.median()),
        'all_ret_20_std': float(all_valid.std()),
        'all_ret_20_winrate': float((all_valid > 0).mean()),
        'bull_ret_20_mean': float(bull_all.mean()),
        'bull_ret_20_median': float(bull_all.median()),
        'bull_ret_20_winrate': float((bull_all > 0).mean()),
        'bear_ret_20_mean': float(bear_all.mean()),
        'bear_ret_20_median': float(bear_all.median()),
        'bear_ret_20_winrate': float((bear_all > 0).mean()),
    }

    with open(os.path.join(EXP_DIR, 'summary_v22.json'), 'w') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"\n  ✅ 完成! 信号已保存, 汇总: {json.dumps(summary, indent=2, ensure_ascii=False)}")

if __name__ == '__main__':
    main()
