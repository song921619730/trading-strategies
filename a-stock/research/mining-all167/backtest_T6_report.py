#!/usr/bin/env python3
"""Fix report from previous run results"""
import json
from datetime import datetime

output_path = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_3/analysis_T6_板块轮动.md"
END_DATE = "20260511"
START_DATE = "20250101"

all_results = [
    {"name": "C1_Sector+T2超跌放量", "signals": 0, "win_rate_5d": 0, "ret_5d": 0, "ret_10d": 0, "ret_20d": 0, "sharpe_5d": 0, "pass_5d": False, "desc": "PAST5D行业TOP5+底20%+VR>=1.5+振幅>=3%+pct>=0"},
    {"name": "C2_Sector+超跌恐慌", "signals": 0, "win_rate_5d": 0, "ret_5d": 0, "ret_10d": 0, "ret_20d": 0, "sharpe_5d": 0, "pass_5d": False, "desc": "PAST5D行业TOP5+pct<=-5%+VR>=0.8+振幅>=5%"},
    {"name": "C3_Sector+均线粘合", "signals": 1344, "win_rate_5d": 45.8, "ret_5d": 0.15, "ret_10d": -0.12, "ret_20d": -0.24, "sharpe_5d": 0.226, "pass_5d": False, "desc": "PAST5D行业TOP5+均线粘合+VR>=1.0+pct>=0"},
    {"name": "C4_Sector+多头排列+放量", "signals": 1895, "win_rate_5d": 37.9, "ret_5d": -1.34, "ret_10d": 0, "ret_20d": 0, "sharpe_5d": 0, "pass_5d": False, "desc": "PAST5D行业TOP3+多头排列+VR>=1.3+pct>=0"},
    {"name": "C5_Sector领涨(过去)+底部(不限行业)", "signals": 0, "win_rate_5d": 0, "ret_5d": 0, "ret_10d": 0, "ret_20d": 0, "sharpe_5d": 0, "pass_5d": False, "desc": "底40%+VR>=1.2+振幅>=3%+pct>=0 (baseline)"},
]

with open(output_path, "w") as f:
    f.write(f"# T6 板块轮动 — Iter 3 分析报告\n\n")
    f.write(f"- 基准交易日: {END_DATE[:4]}-{END_DATE[4:6]}-{END_DATE[6:8]}\n")
    f.write(f"- 回测区间: {START_DATE[:4]}-{START_DATE[4:6]}-{START_DATE[6:8]} ~ {END_DATE[:4]}-{END_DATE[4:6]}-{END_DATE[6:8]}\n")
    f.write(f"- 数据源: stock_basic.industry(5516只股票) + stock_daily(156万行)\n")
    f.write(f"- 行业排名: PAST 5D 收益聚合 (无前向偏见, 319个交易日有数据)\n")
    f.write(f"- 参数: 3-6个维度随机采样 (板块因子+量价/资金因子)\n")
    f.write(f"- 分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
    
    f.write(f"| # | 组合 | N | WR_5d | ret_5d | ret_10d | ret_20d | Sharpe | 达标 |\n")
    f.write(f"|---|------|---|-------|--------|---------|---------|--------|------|\n")
    for i, r in enumerate(all_results, 1):
        ps = "✅" if r.get("pass_5d") else "❌"
        f.write(f"| {i} | {r.get('name','')} | {r.get('signals',0)} | {r.get('win_rate_5d',0):.1f}% | {r.get('ret_5d',0):.2f}% | {r.get('ret_10d',0):.2f}% | {r.get('ret_20d',0):.2f}% | {r.get('sharpe_5d',0):.3f} | {ps} |\n")
    
    f.write("\n## 详细分析\n\n")
    
    f.write("### 1. C1_Sector + T2超跌放量\n")
    f.write("- **描述**: PAST5D行业TOP5 + 底20% + VR>=1.5 + 振幅>=3% + pct>=0\n")
    f.write("- **结果**: 0信号 — 条件组合过严\n")
    f.write("- **原因**: 底20%+VR>=1.5+振幅>=3%+中小盘+pct>=0 5个条件叠加，再叠加行业TOP5过滤，样本量降为0\n\n")
    
    f.write("### 2. C2_Sector + 超跌恐慌\n")
    f.write("- **描述**: PAST5D行业TOP5 + pct<=-5% + VR>=0.8 + 振幅>=5%\n")
    f.write("- **结果**: 0信号\n")
    f.write("- **原因**: VR>=0.8+pct<=-5%矛盾 — 暴跌时VR通常>1(放量恐慌)，VR>=0.8条件过低\n\n")
    
    f.write("### 3. C3_Sector + 均线粘合 ✅ BEST\n")
    f.write("- **描述**: PAST5D行业TOP5 + 均线粘合(差<3%) + VR>=1.0 + pct>=0\n")
    f.write("- **参数**: ma_arrangement:粘合(差<3%), volume_ratio_min:1.0, pct_chg_1d_min:0\n")
    f.write("- **结果**: N=1,344 | WR_5d=45.8% | ret_5d=0.15% | Sharpe=0.226\n")
    f.write("- **Hash**: e6487d6e564\n")
    f.write("- **分析**: 信号量充足(1344)，但5D收益趋近于0。均线粘合意味着横盘整理，叠加行业热点后仍然是横盘\n\n")
    
    f.write("### 4. C4_Sector + 多头排列 + 放量\n")
    f.write("- **描述**: PAST5D行业TOP3 + 多头排列 + VR>=1.3 + 振幅>=5% + pct>=0\n")
    f.write("- **结果**: N=1,895 | WR_5d=37.9% | ret_5d=-1.34%\n")
    f.write("- **分析**: 多头排列+行业热点叠加实际产生负收益！说明\"强者恒强\"在5D窗口不成立，热点追涨反而是陷阱\n\n")
    
    f.write("### 5. C5_Sector 底部放量(不限行业)\n")
    f.write("- **描述**: 底40% + VR>=1.2 + 振幅>=3% + pct>=0 (无行业过滤，作baseline)\n")
    f.write("- **结果**: 0信号 — SQL兼容性问题\n\n")
    
    f.write("## 结论\n\n")
    f.write("### ❌ 全部组合未达标\n\n")
    f.write("**最佳组合**: C3_Sector+均线粘合 — WR=45.8%, ret_5d=0.15%, N=1,344, Sharpe=0.226\n\n")
    
    f.write("### Iter 3 vs Iter 2 对比\n\n")
    f.write("| 指标 | Iter 2 (轮动潜伏) | Iter 3 最佳(均线粘合) | 变化 |\n")
    f.write("|------|-------------------|----------------------|------|\n")
    f.write("| 胜率 | 52.44% | 45.80% | -6.64pp |\n")
    f.write("| 5D收益 | 0.87% | 0.15% | -0.72pp |\n")
    f.write("| 信号数 | 37,939 | 1,344 | -36,595 |\n\n")
    
    f.write("### 核心发现\n\n")
    f.write("1. **板块轮动独立视角在5D窗口无效** — 确认Iter 2结论，Iter 3用无偏见方法再次验证\n")
    f.write("2. **行业因子不适合单独使用** — 无论怎么组合(底部/恐慌/趋势/粘合)，加行业过滤都降低信号量\n")
    f.write("3. **多头排列+行业热点=负收益** — C4显示追热点趋势票5D亏损-1.34%\n")
    f.write("4. **均线粘合+行业是最不差选择** — 信号量充足(1344)，但收益趋近于0\n")
    f.write("5. **推荐**: T6板块轮动因子可作T2/T9 CE8(7.97%收益)的辅助过滤器\n\n")
    
    f.write("### SQL示例 (C3最佳组合)\n\n")
    f.write("```sql\n")
    f.write("SELECT ts_code, trade_date, close FROM (\n")
    f.write("  SELECT d.ts_code, d.trade_date, d.close,\n")
    f.write("    avg(d.close) OVER w5 AS ma5,\n")
    f.write("    avg(d.close) OVER w10 AS ma10,\n")
    f.write("    avg(d.close) OVER w20 AS ma20,\n")
    f.write("    avg(d.close) OVER w60 AS ma60,\n")
    f.write("    row_number() OVER pw AS rn\n")
    f.write("  FROM tushare.tushare_stock_daily d\n")
    f.write("  LEFT JOIN tushare.tushare_daily_basic db ON d.ts_code=db.ts_code AND d.trade_date=db.trade_date\n")
    f.write("  WHERE d.pct_chg>=0 AND db.volume_ratio>=1.0 [主板过滤/日期过滤]\n")
    f.write("  WINDOW ...\n")
    f.write(") WHERE rn>=60\n")
    f.write("  AND greatest(ma5,ma10,ma20,ma60)/NULLIF(least(...),0)-1<0.03\n")
    f.write("```\n\n")
    
    # Table of all 5 combos with params
    f.write("## 完整参数空间\n\n")
    f.write("| Combo | 维度1 | 维度2 | 维度3 | 维度4 | 维度5 | 维度6 |\n")
    f.write("|-------|-------|-------|-------|-------|-------|-------|\n")
    f.write("| C1 | industry_hot_rank(前3) | close_position(底20%) | volume_ratio_min(1.5) | amplitude_min(3) | market_cap_bucket(中小盘) | pct_chg_1d_min(0) |\n")
    f.write("| C2 | sector_top5(Past5D) | close_position(底40%) | volume_ratio_min(1.2) | amplitude_min(3) | pct_chg_1d_min(0) | — |\n")
    f.write("| C3 | sector_top5(Past5D) | volume_ratio_min(1.0) | pct_chg_1d_min(0) | ma_arrangement(粘合) | — | — |\n")
    f.write("| C4 | sector_top3(Past5D) | ma_arrangement(多头) | volume_ratio_min(1.3) | amplitude_min(5) | pct_chg_1d_min(0) | — |\n")
    f.write("| C5 | sector_top5(Past5D) | pct_chg_1d_min(-5) | amplitude_min(5) | — | — | — |\n")
    
    f.write("\n---\n")
    f.write(f"*Report generated at {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n")

print(f"✅ Report written to: {output_path}")
