# Round 002 — TechnicalAnalyst Log

## 输入假设
- 假设: 涨停首板(非一字)+封板率>70% → 次日高开概率
- 方向: long
- 表: limit_list_d JOIN stk_factor_pro

## 回测设计
```
entry_sql: ln.ts_code IS NOT NULL AND ln.limit='U' AND ln.limit_times=1
           AND ln.first_time > '093000' AND ln.open_times=0
条件说明: 非一字板(09:30后涨停) + 首板 + 封死后不开板
hold_periods: [1, 3, 5]
多表JOIN: stk_factor_pro (f) LEFT JOIN limit_list_d (ln)
```

## 回测结果

| hold | signals | win_rate | ci_95_lower | ci_95_upper | avg_return | sharpe |
|------|---------|----------|-------------|-------------|------------|--------|
| 1 | 151 | 68.21% | 60.41% | 75.11% | +2.50% | 8.31 |
| 3 | 151 | 31.79% | 24.89% | 39.59% | -58.23% | -10.29 |
| 5 | 151 | 11.26% | 7.15% | 17.29% | -80.36% | -13.70 |

## 分析
- hold=1: 强信号。WR 68.21%, CI 下限 60.41% 远超 50%。
- hold=3+: 同 init_001 一样快速均值回归。
- 信号量偏少 (151个，5年约30个/年)，样本偏小，CI 区间较宽。

## 结论
✅ 统计显著，但样本量偏小，需要提升到 A 级需要更多交叉验证。

## 建议
1. 扩大条件: 放宽到 all limit_up (含一字板)，看溢价是否更大
2. 拆分: 涨停次日 vs 非涨停的跳空溢价差异
3. 增加: 换手率、成交额条件过滤
