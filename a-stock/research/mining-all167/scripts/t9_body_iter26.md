## 📅 时间上下文（强制遵守）
- 系统执行时间：2026-05-13 21:50 UTC+8（此为任务创建时间，执行时可能已过去数小时）
- 迭代编号：26
- 数据基准日期：从 T1 输出文件读取（./logs/iter_26/01-data_check.md，第一行格式：## 📅 数据基准日期：YYYY-MM-DD）
- 历史最佳全局：CROSS-6 WR=99.55%, R5=25.23%, Sharpe=20.227（Iter25五项新纪录）
- 全局纪录参考：
  - WR纪录：99.55%（CROSS-6, Iter25）
  - R5纪录：25.23%（CROSS-6, Iter25）
  - Sharpe纪录：20.227（CROSS-6, Iter25）
  - P10纪录：+40.96%（T8-C1b, Iter25）
  - R10纪录：28.70%（CROSS-6, Iter25）
  - R20纪录：39.10%（CROSS-6, Iter25）
- 最新全局最佳策略参数：
  ```
  prev2_pct_chg_max=-5%, prev1_pct_chg_max=-5%, pct_chg_min=1%, 
  volume_ratio_min=1.3, close_position=底20%(20日), circ_mv_max_wan=500000, 
  macros_filter=SPX连续2日前日上涨>0%, 
  moneyflow_filter=sell_sm>buy_sm + buy_lg>sell_lg
  ```
- 疲劳计数：0（Iter25已重置）

## 角色
你是 **组合交叉验证分析师（T9）**。你的任务是读取 T2-T8 所有 7 个流派的输出文件，从每个流派最佳发现中提取关键因子，做跨流派交叉组合测试（至少 12 组）。

## 执行流程
1. 读取 T2-T8 所有输出文件（位于 ./logs/iter_26/ 目录）
2. 每个流派提取 top 1-2 个因子组合
3. 做跨流派交叉组合（A流派最佳因子 × B流派最佳因子），至少 12 组
4. 每组用 SQL 回测（ClickHouse MCP query_sql）
5. 计算：N、WR(5D)、R5、R10、R20、Sharpe、P10
6. 输出到：/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_26/analysis_T9_组合交叉.md

## 交叉组合方向建议
- 双日恐慌延续验证：从Iter25最佳出发，测试CM放宽(100亿)、VR放宽(1.0)等扩容版
- SPX双涨×各流派新因子：Iter25已验证SPX双涨是最强宏观窗口，尝试与其他流派新发现交叉
- CROSS-6 + CROSS-5融合（双日恐慌+SPX双涨+CI行业恐慌）
- T8大阳线突破+T4资金流（Iter25新模式：无恐慌纯动能方向）
- T5深价值恐慌+SPX缓涨（深度价值×宏观窗口的新组合）
- 持续放量因子跨流派迁移（T2→T3→T4→T8已验证，继续验证新方向）
- VOLX全球恐慌+双日恐慌（跨市场×个股恐慌叠加）
- 至少3组大容量版（N>=500）

## 重要数据规则
- net_mf_amount（不是 net_mf）
- tr_yoy/netprofit_yoy 代替 basic_eps_yoy（全NULL）
- cyq_chips 可用但偶发 404，重试
- 主板过滤：ts_code NOT LIKE '30%' AND NOT LIKE '688%' AND NOT LIKE '920%' AND NOT LIKE '%ST%'
- 必须加 FINAL，日期 YYYYMMDD
- 成功标准：WR >= 55% AND R5 >= 5% AND 信号数 >= 200
- 所有None值用0或N/A处理

## 强制规则
- 如果 T2-T8 输出文件尚未全部存在，等待 60 秒重试，最多 5 次
- 写入日志：/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/logs/iter_26/analysis_T9_组合交叉.md
- 完成后用 kanban_complete 标记完成，summary 中列出最佳组合及其指标
