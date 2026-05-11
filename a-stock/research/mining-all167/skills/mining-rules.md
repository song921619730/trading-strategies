# 策略挖掘循环规则

## 核心架构

```
每轮 Cron 触发 → reze 读取 state.json → 创建 11 个 Kanban 任务
    ↓
T1  researcher    数据检查
T2～T8  analyst   7 个流派并行挖掘（统一参数空间，随机采样）
    ↓
T9  analyst       组合派交叉验证
T10 analyst       主控收敛（更新 state + knowledge_base）
    ↓
T11 writer        生成报告
```

## 全局时间指令

在创建所有 kanban_create 任务时，必须在 body 开头注入：
```
## 📅 时间上下文（强制遵守）
- 系统执行时间：{YYYY-MM-DD HH:MM} UTC+8
- 数据查询前必须先运行：SELECT max(trade_date) FROM tushare.tushare_stock_daily FINAL
- 禁止使用"周一/周五"等推测词，统一使用 YYYY-MM-DD
```

## 工作目录

所有任务运行在：`/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/`

## 分析师参数采样规则

1. 读取 `./skills/param-space.md` 获取完整参数空间
2. 从 50 个维度中**随机选择 3-8 个维度**
3. 每个维度**随机选择一个值**
4. 组合的 hash = sorted(key=value pairs) → md5
5. 对比 `./state/state.json` 中的 `recent_combos`，跳过最近 50 个已测试组合
6. 每个 analyst 每轮测试 **5 组不同的参数组合**
7. 7 个 analyst × 5 组 = 每轮 35 个策略测试

## 分析师输出要求

每个 analyst 任务完成后，必须在 scratch 中写入：
- `analysis_iter_{N}_{流派}.md`：包含：
  - 本轮测试的 5 组参数
  - 每组的 SQL 查询
  - 每组的结果：信号数、胜率、5D收益、10D收益、20D收益
  - 最佳发现的详细描述
  - 关键 SQL 查询语句（必须可复现）

然后 `kanban_complete` 的 summary 中必须包含：
- 最佳策略的参数组合
- 最佳指标（胜率、收益、信号数）

## 数据查询规则

- **必须使用 FINAL**（ClickHouse ReplacingMergeTree 去重）
- **日期格式 YYYYMMDD**
- **先查 `max(trade_date)` 确认数据基准**
- **充分利用全量历史数据**，不要只查最近几天
- **主板过滤**：`ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%' AND ts_code NOT LIKE '920%' AND ts_code NOT LIKE '%ST%'`
- 使用 `query_sql` MCP 工具，不要直连 ClickHouse HTTP

### ⚠️ 已知数据质量问题（2026-05-11 确认）

| 问题 | 状态 | 修复方案 |
|------|------|---------|
| `cyq_chips` HTTP 404 | ⚠️ 偶发，表存在(206万条) | 重试即可，或检查 ClickHouse 连接 |
| `basic_eps_yoy` 整列为空 | ❌ 118565条全NULL | 改用 `tr_yoy`（营收增长）或 `netprofit_yoy`（净利润增长） |
| `net_mf` 字段不存在 | ❌ | 正确字段是 `net_mf_amount`（Decimal）和 `net_mf_vol`（Int64） |
| 财报季频数据匹配困难 | ⚠️ fina_indicator仅118565条 | 用 `end_date` 对齐财报季度，或用 `tr_yoy` 代替基本 EPS 增长 |
| T4 资金主力参数过严 | ⚠️ 首轮5组全部0信号 | 下轮放宽：`net_mf_min` 从 2000万 降至 500万，`buy_lg_ratio_min` 从 15% 降至 8% |

## 回测计算规则

- 买入日：信号触发日
- T+N 收益：(close_{T+N} / close_{T} - 1) × 100%
- 胜率：(T+N 收益 > 0 的股票数) / 总信号数
- 平均收益：所有信号 T+N 收益的算术平均
- 夏普比率：平均收益 / 收益标准差 × sqrt(252/N)
- **所有 None 值用 0 或 "N/A" 处理，不要直接格式化**

## 成功标准（Alpha 定义）

| 指标 | 合格线 | 优秀线 |
|------|--------|--------|
| 胜率(WR) | ≥ 52% | ≥ 58% |
| 5D 平均收益 | ≥ 3% | ≥ 7% |
| 信号数量 | ≥ 200 | ≥ 1000 |
| 夏普比率 | ≥ 0.5 | ≥ 1.0 |

## state.json 更新规则（T10 主控负责）

每轮结束后，T10 必须更新 `./state/state.json`：

```json
{
  "current_iteration": N,
  "best_metrics": {
    "ret_5d": 0.XX,
    "win_rate_5d": 0.XX,
    "ret_10d": 0.XX,
    "ret_20d": 0.XX,
    "signal_count": XXX,
    "sharpe_5d": X.XX,
    "strategy_desc": "流派名-参数描述",
    "params": {"key": "value", ...},
    "discovered_at": "YYYY-MM-DD"
  },
  "fatigue_count": N,  // 连续未破新纪录的轮数
  "history": [
    {"iteration": N, "ret_5d": X.XX, "win_5d": X.XX, "signal_count": XXX,
     "params": {...}, "analyst": "T2", "time": "YYYY-MM-DD HH:MM"},
    // 保留最近 50 条
  ],
  "recent_combos": [
    "hash_abc123",  // 保留最近 50 个参数 hash
    "hash_def456"
  ]
}
```

### 更新逻辑
- 如果本轮有**超过历史最佳**的策略 → 更新 `best_metrics`，`fatigue_count = 0`
- 否则 → `fatigue_count += 1`
- 将本轮所有参数组合的 hash 加入 `recent_combos`
- 将本轮摘要加入 `history`（保持最多 50 条）
- 如果 `fatigue_count ≥ 10` → 在本轮报告中建议用户检查方向

## knowledge_base 更新规则

每轮收敛后，T10 必须将**有效发现**追加到 `./state/knowledge_base.md`：

```markdown
## YYYY-MM-DD (iter N) - 流派名
- **参数**: key1=value1, key2=value2, ...
- **指标**: 5D收益=X%, WR=X%, 信号数=XXX, 夏普=X.XX
- **SQL**: （关键查询片段）
- **结论**: 一句话总结
- **状态**: ✅ 有效 / ❌ 无效 / ⚠️ 样本不足
```

## 疲劳机制

- `fatigue_count` 从 0 开始
- 每轮如果**没有找到超过历史最佳**的策略 → +1
- 找到新的历史最佳 → 重置为 0
- **fatigue_count ≥ 10** → T10 在报告中提醒用户："连续 10 轮未破纪录，建议调整方向"
- **fatigue_count ≥ 20** → T10 在报告中建议暂停并审查

## 报告路径

Writer 生成的报告保存到：`./reports/mining-all167-iter{N}-YYYYMMDD-HHMM.md`
