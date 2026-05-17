## 📅 时间上下文（强制遵守）
- 系统执行时间：2026-05-13 23:57 UTC+8
- 本轮迭代编号：27
- 历史最佳WR：99.55% (Iter25 CROSS-6)
- 历史最佳R5：25.23% (Iter25 CROSS-6)
- 疲劳计数：1
- 本轮 T2-T8 已完成，读取各流派输出进行交叉验证

## 任务：T9 组合交叉验证 (Iter27)

读取 T2-T8 所有输出（位于 ./logs/iter_27/）→ 从每个流派最佳发现中提取因子做交叉组合（至少 10 组）→ 输出到 ./logs/iter_27/analysis_T9_组合交叉.md

### 交叉验证要求
1. 读取每个流派的分析文件（analysis_T{2-8}_{流派}.md）
2. 从每个流派提取 1-2 个最佳参数/因子
3. 生成至少 10 组交叉组合（跨流派因子配对）
4. 每组回测记录：参数组合、信号数(N)、胜率(WR)、5D收益、10D收益、20D收益、夏普比率(Sharpe)、P10(最差10%平均收益)

### 重点测试方向
- 双日恐慌（连续2日跌≥5%）× SPX/宏观/资金流的变体优化
- 振幅≥7% 与资金流因子的跨流派叠加效应
- 双日温和恐慌(-3%) 替代 -5% 的阈值优化
- 散户割肉(sell_sm>buy_sm)与其他因子的组合
- 非恐慌模式（涨时买入+资金确认）的扩容

### 数据规则
- ClickHouse 查询必须加 FINAL
- 日期格式 YYYYMMDD
- 主板过滤：ts_code NOT LIKE '30%' AND NOT LIKE '688%' AND NOT LIKE '920%' AND NOT LIKE '%ST%'
- net_mf_amount 是正确字段（不是 net_mf）
- tr_yoy / netprofit_yoy 代替 basic_eps_yoy（整列为空）
- cyq_chips 可用但偶发404，需重试

### 成功标准
WR ≥ 52% AND 5D 收益 ≥ 3% AND 信号数 ≥ 200
优秀线：WR ≥ 85% AND R5 ≥ 15% AND N ≥ 300

### 输出文件
绝对路径：/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_27/analysis_T9_组合交叉.md
