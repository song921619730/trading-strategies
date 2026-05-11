#!/usr/bin/env python3
# ============================================================
# A 股 Kanban Loop - 网格回测引擎 (Grid Engine) v2
# ============================================================
# 核心职责：
# 1. 读取 grid_config.json (AI 生成的假设)
# 2. 调用 DataLoader 从 ClickHouse 拉取数据
# 3. 对每个参数组合执行 PIT-safe 选股
# 4. 向量化计算多周期收益 (1D/5D/10D/20D)
# 5. 输出 results.csv 和 summary.json
#
# 用法: python grid_engine.py <config.json>
# ============================================================

import pandas as pd
import numpy as np
import json
import sys
import os
from itertools import product
from datetime import datetime
from data_loader import DataLoader


def load_config(config_path: str) -> dict:
    """加载配置"""
    with open(config_path, 'r') as f:
        return json.load(f)


def load_market_data(config: dict) -> pd.DataFrame:
    """从 ClickHouse 加载市场数据"""
    print(f"\n{'='*60}")
    print("📡 Loading Market Data from ClickHouse...")
    print(f"{'='*60}")

    data_layers = config.get('data_layers', ['daily', 'daily_basic'])
    
    # 动态获取全量数据范围，严禁硬编码年份
    loader = DataLoader()
    min_date, max_date = loader.get_date_range()
    
    start_date = config.get('start_date', min_date)
    end_date = config.get('end_date', max_date)
    
    # 全市场加载（速度优先，不做个股筛选）
    print(f"📅 Date range: {start_date} to {end_date}")
    print(f"📊 Layers: {data_layers}")
    
    df = loader.load_data(
        tables=data_layers,
        start_date=start_date,
        end_date=end_date
    )
    
    return df


def prepare_data(df: pd.DataFrame) -> pd.DataFrame:
    """数据预处理：排序、去重列、类型转换"""
    print(f"\n{'='*60}")
    print("🔧 Preparing Data...")
    print(f"{'='*60}")
    
    # 删除重复列（t3.ts_code, t3.trade_date 等）
    dup_cols = [c for c in df.columns if c.startswith('t') and '.' in c]
    if dup_cols:
        df = df.drop(columns=dup_cols)
        print(f"  Removed {len(dup_cols)} duplicate columns: {dup_cols}")
    
    # 确保日期排序
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df = df.sort_values(['ts_code', 'trade_date']).reset_index(drop=True)
    
    # 数值类型转换
    num_cols = ['open', 'high', 'low', 'close', 'pre_close', 'pct_chg', 'vol', 'amount',
                'turnover_rate', 'volume_ratio', 'pe', 'pb', 'circ_mv']
    for col in num_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # 填充基本字段空值
    df['circ_mv'] = df['circ_mv'].fillna(0)
    df['turnover_rate'] = df['turnover_rate'].fillna(0)
    df['volume_ratio'] = df['volume_ratio'].fillna(0)
    df['pe'] = df['pe'].fillna(0)
    df['pb'] = df['pb'].fillna(0)
    
    print(f"  Shape after prep: {df.shape}")
    print(f"  Date range: {df['trade_date'].min()} to {df['trade_date'].max()}")
    print(f"  Unique stocks: {df['ts_code'].nunique()}")
    
    return df


def calculate_future_returns(df: pd.DataFrame, periods: list) -> pd.DataFrame:
    """向量化计算未来 N 日收益（PIT 安全）"""
    print(f"\n{'='*60}")
    print("📈 Calculating Future Returns...")
    print(f"{'='*60}")
    
    # 按股票分组，计算未来收益
    df = df.sort_values(['ts_code', 'trade_date'])
    
    for period in periods:
        # shift(-period) 获取未来 N 日后的收盘价
        future_close = df.groupby('ts_code')['close'].shift(-period)
        # 未来 N 日收益率
        df[f'fwd_ret_{period}d'] = (future_close - df['close']) / df['close']
        
        # 计算持仓期间最大回撤（未来 N 日内的最低点）
        for i in range(1, period + 1):
            future_h = df.groupby('ts_code')['high'].shift(-i) if i == 1 else None
            future_l = df.groupby('ts_code')['low'].shift(-i) if i == 1 else None
        
        # 简化：仅计算未来各日收益
        for i in range(1, period + 1):
            fc = df.groupby('ts_code')['close'].shift(-i)
            df[f'fwd_close_{i}d'] = fc
    
    print(f"  Added future return columns for periods: {periods}")
    return df


def apply_filters(df: pd.DataFrame, variables: dict, base_mask: pd.Series) -> pd.DataFrame:
    """应用过滤条件，返回信号标记"""
    mask = base_mask.copy()
    
    for var, val in variables.items():
        if val is None:  # 空值 = 不限制
            continue
        
        if var == 'circ_mv_max':
            # circ_mv 单位是元，config 中是亿
            mask &= df['circ_mv'] <= (val * 1e8)
        elif var == 'circ_mv_min':
            mask &= df['circ_mv'] >= (val * 1e8)
        elif var == 'turnover_min':
            # turnover_rate 已经是百分比（如 0.5 = 0.5%）
            mask &= df['turnover_rate'] >= val
        elif var == 'turnover_max':
            mask &= df['turnover_rate'] <= val
        elif var == 'volume_ratio_min':
            mask &= df['volume_ratio'] >= val
        elif var == 'pe_max':
            mask &= (df['pe'] <= val) | (df['pe'] == 0)  # PE=0 表示亏损，保留
        elif var == 'pe_min':
            mask &= (df['pe'] >= val) | (df['pe'] == 0)
        elif var == 'pct_chg_min':
            mask &= df['pct_chg'] >= val
        elif var == 'pct_chg_max':
            mask &= df['pct_chg'] <= val
        elif var == 'vol_min':
            mask &= df['vol'] >= val
        elif var == 'close_min':
            mask &= df['close'] >= val
        elif var == 'net_mf_min':
            # 净资金流（正 = 净买入）
            if 'net_mf_vol' in df.columns:
                mask &= df['net_mf_vol'] >= val
        elif var == 'buy_lg_ratio_min':
            # 大单买入比例（大买单 / 总成交量）
            if 'buy_lg_vol' in df.columns and 'vol' in df.columns:
                ratio = df['buy_lg_vol'] / (df['vol'] + 1)
                mask &= ratio >= val
        elif var == 'buy_elg_ratio_min':
            # 超大单买入比例
            if 'buy_elg_vol' in df.columns and 'vol' in df.columns:
                ratio = df['buy_elg_vol'] / (df['vol'] + 1)
                mask &= ratio >= val
        elif var == 'sell_lg_ratio_max':
            # 大单卖出比例上限
            if 'sell_lg_vol' in df.columns and 'vol' in df.columns:
                ratio = df['sell_lg_vol'] / (df['vol'] + 1)
                mask &= ratio <= val
        else:
            print(f"  ⚠️ Unknown variable: {var}")
    
    return mask


def run_grid_search(df: pd.DataFrame, config: dict) -> list:
    """
    遍历所有参数组合，执行回测。
    返回每个组合的结果字典列表。
    """
    print(f"\n{'='*60}")
    print("🔬 Running Grid Search...")
    print(f"{'='*60}")
    
    variables_config = config.get('variables', {})
    holding_periods = config.get('holding_periods', [1, 5, 10, 20])
    
    # 生成所有参数组合的笛卡尔积
    var_names = list(variables_config.keys())
    var_values = [variables_config[name] for name in var_names]
    
    all_combinations = list(product(*var_values)) if var_values else [()]
    
    print(f"  Variable space: {len(var_names)} vars")
    for name, vals in variables_config.items():
        print(f"    {name}: {vals}")
    print(f"  Total combinations: {len(all_combinations)}")
    
    # 基础筛选：日内涨幅 >= 5% 且 次日收盘不跌
    # PIT-safe: 使用 T 日开盘价已知信息
    df['next_close'] = df.groupby('ts_code')['close'].shift(-1)
    base_rule = (df['close'] / df['open'] >= 1.05) & (df['next_close'] >= df['close'])
    
    results = []
    
    for idx, combo in enumerate(all_combinations):
        # 构建当前组合的参数字典
        params = dict(zip(var_names, combo))
        
        # 应用过滤
        mask = apply_filters(df, params, base_rule)
        signals = df[mask].copy()
        
        if len(signals) == 0:
            results.append({
                **params,
                'signal_count': 0,
                'avg_ret_1d': None,
                'avg_ret_5d': None,
                'avg_ret_10d': None,
                'avg_ret_20d': None,
                'win_rate_5d': None,
                'max_dd_5d': None,
                'avg_max_dd_5d': None,
                'sharpe_5d': None,
            })
            continue
        
        # 计算多周期收益
        signal_results = {'signal_count': len(signals)}
        signal_results.update(params)
        
        for period in [1, 5, 10, 20]:
            ret_col = f'fwd_ret_{period}d'
            if ret_col in signals.columns:
                rets = signals[ret_col].dropna()
                if len(rets) > 0:
                    avg_ret = rets.mean()
                    win_rate = (rets > 0).mean()
                    # 年化 Sharpe（假设 252 个交易日）
                    sharpe = (rets.mean() / rets.std() * np.sqrt(252 / period)) if rets.std() > 0 else 0
                    
                    signal_results[f'avg_ret_{period}d'] = float(avg_ret)
                    signal_results[f'win_rate_{period}d'] = float(win_rate)
                    signal_results[f'sharpe_{period}d'] = float(sharpe)
                    signal_results[f'signal_count_{period}d'] = len(rets)
                else:
                    signal_results[f'avg_ret_{period}d'] = None
                    signal_results[f'win_rate_{period}d'] = None
                    signal_results[f'sharpe_{period}d'] = None
                    signal_results[f'signal_count_{period}d'] = 0
        
        results.append(signal_results)
        
        if (idx + 1) % 10 == 0:
            print(f"  Processed {idx+1}/{len(all_combinations)} combos...")
    
    # 排序：按 5D 收益降序
    results_df = pd.DataFrame(results)
    sort_col = 'avg_ret_5d'
    if sort_col in results_df.columns:
        results_df = results_df.sort_values(sort_col, ascending=False).reset_index(drop=True)
    
    print(f"\n✅ Grid search complete: {len(results_df)} combos evaluated.")
    print(f"   Top 3 by {sort_col}:")
    if sort_col in results_df.columns and len(results_df) > 0:
        top3 = results_df.head(3)
        for i, row in top3.iterrows():
            ret = row.get('avg_ret_5d', None)
            wr = row.get('win_rate_5d', None)
            sh = row.get('sharpe_5d', None)
            cnt = row.get('signal_count', 0)
            ret_str = f"{ret:.4f}" if pd.notna(ret) and ret is not None else "N/A"
            wr_str = f"{wr:.2%}" if pd.notna(wr) and wr is not None else "N/A"
            sh_str = f"{sh:.2f}" if pd.notna(sh) and sh is not None else "N/A"
            print(f"   #{i+1}: {ret_str} | "
                  f"WR={wr_str} | "
                  f"Sharpe={sh_str} | "
                  f"Signals={cnt} | "
                  f"Params: {dict((k, row[k]) for k in var_names if k in row)}")
    
    return results_df


def save_results(results_df: pd.DataFrame, output_dir: str):
    """保存结果"""
    os.makedirs(output_dir, exist_ok=True)
    
    # CSV 结果
    csv_path = os.path.join(output_dir, 'results.csv')
    results_df.to_csv(csv_path, index=False)
    print(f"\n💾 Results saved to {csv_path}")
    
    # Sumary JSON (Top 10)
    summary_path = os.path.join(output_dir, 'summary.json')
    top10 = results_df.head(10).to_dict('records') if len(results_df) > 0 else []
    summary = {
        'timestamp': datetime.now().isoformat(),
        'total_combinations': len(results_df),
        'top_10': top10
    }
    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"💾 Summary saved to {summary_path}")
    
    return csv_path, summary_path


def find_best_config(results_df: pd.DataFrame, var_names: list) -> dict:
    """找到最佳参数组合"""
    if len(results_df) == 0:
        return {}
    
    # 按 5D 收益排序
    if 'avg_ret_5d' in results_df.columns:
        best = results_df.iloc[0]
        best_params = {k: best[k] for k in var_names if k in best}
        best_params['avg_ret_5d'] = float(best['avg_ret_5d']) if pd.notna(best.get('avg_ret_5d')) else None
        best_params['win_rate_5d'] = float(best['win_rate_5d']) if pd.notna(best.get('win_rate_5d')) else None
        best_params['sharpe_5d'] = float(best['sharpe_5d']) if pd.notna(best.get('sharpe_5d')) else None
        best_params['signal_count'] = int(best['signal_count']) if pd.notna(best.get('signal_count')) else 0
        return best_params
    
    return {}


def main():
    if len(sys.argv) < 2:
        print("Usage: python grid_engine.py <config.json>")
        sys.exit(1)
    
    config_path = sys.argv[1]
    print(f"🚀 Grid Engine v2 Starting...")
    print(f"   Config: {config_path}")
    
    # 1. 加载配置
    config = load_config(config_path)
    print(f"   Variables: {list(config.get('variables', {}).keys())}")
    print(f"   Layers: {config.get('data_layers', ['daily'])}")
    
    # 2. 设置输出目录
    output_dir = config.get('output_dir', 'logs')
    iter_dir = config.get('iteration_dir', 'iter_001')
    output_path = os.path.join(output_dir, iter_dir)
    os.makedirs(output_path, exist_ok=True)
    
    # 3. 加载数据
    df = load_market_data(config)
    df = prepare_data(df)
    
    # 4. 计算未来收益
    df = calculate_future_returns(df, config.get('holding_periods', [1, 5, 10, 20]))
    
    # 5. 执行网格搜索
    results_df = run_grid_search(df, config)
    
    # 6. 保存结果
    csv_path, summary_path = save_results(results_df, output_path)
    
    # 7. 找到最佳参数
    var_names = list(config.get('variables', {}).keys())
    best = find_best_config(results_df, var_names)
    
    print(f"\n{'='*60}")
    print("🏆 Best Config Found:")
    print(f"{'='*60}")
    for k, v in best.items():
        if isinstance(v, float):
            print(f"  {k}: {v:.4f}")
        else:
            print(f"  {k}: {v}")
    
    # 8. 写日志
    log_path = os.path.join(output_path, 'engine_log.md')
    with open(log_path, 'w') as f:
        f.write(f"# Grid Engine Run Log\n")
        f.write(f"**Time**: {datetime.now().isoformat()}\n")
        f.write(f"**Config**: {config_path}\n\n")
        f.write(f"## Data\n")
        f.write(f"- Date Range: {config.get('start_date')} to {config.get('end_date')}\n")
        f.write(f"- Layers: {config.get('data_layers')}\n")
        f.write(f"- Total Stocks: {df['ts_code'].nunique() if 'ts_code' in df.columns else 'N/A'}\n")
        f.write(f"- Total Rows: {len(df)}\n\n")
        f.write(f"## Results\n")
        f.write(f"- Combinations tested: {len(results_df)}\n")
        f.write(f"- Best 5D Return: {best.get('avg_ret_5d', 'N/A')}\n")
        f.write(f"- Best Win Rate (5D): {best.get('win_rate_5d', 'N/A')}\n")
        f.write(f"- Best Sharpe (5D): {best.get('sharpe_5d', 'N/A')}\n")
        f.write(f"- Signal Count: {best.get('signal_count', 0)}\n\n")
        f.write(f"## Best Params\n")
        for k, v in best.items():
            f.write(f"- {k}: {v}\n")
    
    print(f"\n📝 Log saved to {log_path}")
    print(f"\n✅ Grid Engine v2 Complete!\n")
    
    return best


if __name__ == '__main__':
    main()
