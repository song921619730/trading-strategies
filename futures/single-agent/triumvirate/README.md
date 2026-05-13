# Triumvirate — 三 AI 共识交易策略 (Magic 234004)

**定位**: 低频·高胜率·三重验证 · 三人表决制 · 全链路日志留痕

---

## 为什么从 CIO 升级？

Pure AI CIO 运行 3 天，21 笔交易的亏损根本原因：

| 问题 | CIO 模式 | 三 AI 解决方案 |
|------|---------|--------------|
| **逆势猜顶** | AI 自己看 D1 涨但坚持做空，无人质疑 | President 专职趋势裁判，方向冲突直接 VETO |
| **RR < 1:1 仍开仓** | AI 找理由"结构强"绕过规则 | RiskManager 硬性拦截，量化规则一票否决 |
| **第二段执行不严格** | 回调 53% 还开仓 | Analyst 独立评分，<6 分倾向反对 |
| **持仓集中** | 同方向贵金属/股指同时开 | RiskManager 计算相关性组合风险 |
| **认知偏差** | 单人无法自我纠错 | 三人交叉评审，互相质疑 |

---

## 架构: Global Profiles + Local Skills

符合整体系统的 "Global Profiles + Local Skills" 设计模式：

| Profile (全局复用) | Skill 注入 (本策略) | 职责 |
|-----------------|-------------------|------|
| `analyst` | `skills/analyst-triumvirate.md` | H1 结构评分 1-10 |
| `risk_manager` | `skills/risk-manager-triumvirate.md` | 5 条硬过滤 + 仓位计算 |
| `president` | `skills/president-triumvirate.md` | D1 趋势方向判断 |

> Profile 是通用角色定义，跨策略复用
> Skills 是策略专属的行为指南，存储在 `skills/` 下

---

## 交易逻辑（三 AI 各自决策什么）

### 技术分析官 — Analyst

**核心问题**: 这个品种的 H1 结构质量如何？

**判断依据**:
```
1. 找出 H1 上的推进段 (Impulse) + 回调段 (Pullback)
2. 评价第二段质量:
   - 回调在 30-50% 之间 → 最佳
   - 回调 50-65% → 勉强接受
   - 回调 >65% → 可能是反转边缘
   - 回调 <20% → 蜻蜓点水，不安全
3. 检查上方最近的阻力/下方最近的支撑
4. 输出结构评分 1-10 + PASS/FAIL
```

**输出**: 评分、入场区间、止损位、目标位、风险标记

---

### 风控官 — Risk Manager

**核心问题**: 这笔单的风险敞口可接受吗？

**5 条硬过滤（每一条都是独立一票否决权）**:

| # | 规则 | 拒绝条件 |
|---|------|---------|
| 1 | 盈亏比 ≥ 1:1 | RR < 1.0 → ❌ |
| 2 | 单笔风险 ≤ 5% 净值 | Risk% > 5% → ❌ |
| 3 | 相关性风险 | 同组合计风险 > 10% → ❌ |
| 4 | SL 合理性 | SL < 1x ATR 或 SL 方向错误 → ❌ |
| 5 | 连亏警觉 | 最近 3 笔中 ≥2 笔亏损 → 降手数 |

**规则不可绕过**: 任何一条不满足，直接投反对票，不给讨论空间。

---

### 趋势裁判官 — President

**核心问题**: 当前 D1 趋势方向是否支持这笔交易？

**判断规则**:
```
D1 多头 + H1 想做空 → ❌ VETO（这是 CIO 最大的亏损来源）
D1 空头 + H1 想做多 → ❌ VETO
D1 多头 + H1 做多 → ✅ SUPPORT
D1 空头 + H1 做空 → ✅ SUPPORT
D1 震荡 + 任何方向 → 允许但降手数
```

**趋势判断依据**:
- D1 higher high + higher low → 多头
- D1 lower high + lower low → 空头
- 以上不成立 → 震荡
- 价格与 20 日均线的关系辅助确认

---

## 决策流程

```
步骤1: pre_analyze.py → 14品种 OHLCV + ATR + 持仓     写入 logs/scans/
步骤2: fetch_news.py  → 宏观/地缘/经济事件              写入 logs/news/
步骤3: Trade Gate     → 选出 1-3 个候选                写入 logs/scans/
         │
         ▼
步骤4: delegate_task 并行派出3人并行分析                写入 logs/consensus/
  ┌─ Analyst: 结构评分
  ├─ RiskManager: 硬过滤
  └─ President: 方向判断
         │
         ▼
步骤5: 交叉评审（3人互相看对方意见后决定是否改）         写入 logs/consensus/
         │
         ▼
步骤6: 投票 → 3:0 执行 / 否则不执行                    写入 logs/consensus/
         │
         ▼
步骤7: execute_trade.py 下单                          写入 logs/trades/
         │
         ▼
步骤8: 持仓管理 (SL/TP调整)                            写入 logs/trades/
```

---

## 日志体系（所有内容都有记录）

| 日志目录 | 谁写 | 记录什么 |
|---------|------|---------|
| `logs/scans/` | pre_analyze.py / Oracle | 市场数据快照 + Trade Gate 过滤结果 |
| `logs/news/` | fetch_news.py | 原始新闻搜索结果 |
| `logs/consensus/` | Oracle | 三轮讨论 + 最终投票 + 分歧理由 |
| `logs/trades/` | execute_trade.py | 每个开/平/改 MT5 返回 |

每条日志都带 **时间戳 + 品种 + 操作类型**，不可覆盖，支持完整归因复盘。

---

## 目录结构

```
config/
├── active_cron_prompt.md     # 主 Cron Prompt（Oracle 调度指令）
├── consensus_rules.md        # 投票规则参考
sklils/ (3 个)
scripts/ (3 个)
templates/
docs/
data/     # pre_analyze 缓存（最新快照）
logs/
├── scans/{timestamp}_pre_analyze.json
├── scans/{timestamp}_tradegate.json
├── news/{timestamp}_{query}.json
├── consensus/{timestamp}_round1/round2/FINAL.json
└── trades/{timestamp}_OPEN/CLOSE/MODIFY.json
```

## 与 CIO 对比

| 维度 | CIO (234003) | Triumvirate (234004) |
|------|-------------|---------------------|
| 决策 | 单人 | 三人共识 |
| 记录 | 有限 | 全链路日志 |
| 风控 | 自控制 | 独立 RiskManager |
| 逆势 | 无法自我阻止 | President VETO |
| SL | 有时异常 | 硬性 1x ATR 下限 |

两个 Magic Number 在同一个 MT5 账户里和平共存，互不影响。
