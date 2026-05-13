# 期货 K 线形态研究 — 专属研究循环

⚠️ **语言要求：所有输出必须使用中文。**

## 重要：研究范围隔离
**这是期货外汇市场的 K 线形态研究。严禁涉及 A 股。**
- ✅ 品种范围：XAUUSD, EURUSD, GBPUSD, USDJPY, AUDUSD, USDCHF, US30, US500, USTEC, JP225, HK50, XAGUSD, USOIL, UKOIL
- ✅ 数据源：本地 parquet（GitHub Hermes 仓库）+ MT5
- ❌ 禁止使用 ClickHouse
- ❌ 禁止使用 tushare_ 表
- ❌ 禁止引用 A 股假设（gen_xxx 系列）
- ❌ 禁止讨论"做空/避雷"——这是期货市场，方向自由不受限

## 研究目录
{workdir}

## WORKFLOW

### Step 1: 读取状态
```bash
cat state/research_state.json
```
从 `hypothesis_queue` 选一个 pending 假设。

### Step 2: 运行测试
```bash
cd /mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/candlestick-patterns/scripts
python3 << 'PYEOF'
from run_candlestick import run_pattern_test
results = run_pattern_test(
    entry_condition="<YOUR_CANDLESTICK_CONDITION>",
    direction="long",
    timeframe="H1",
    symbols=["XAUUSD", "EURUSD", "USDJPY", "US30", "JP225"],
    hold_periods=[1, 2, 3, 5, 7, 10, 15, 20],
    verbose=False,
)
PYEOF
```

### Step 3: 解读
- win_rate > 60% + n >= 30 → 加入 best_findings（强信号）
- win_rate > 55% + n >= 30 → promising
- n < 30 → 信号不足
- 记录最佳品种、持有期、Sharpe

### Step 4: 生成新假设
基于结果生成 2-4 个新的 K 线形态假设。

### Step 5: 更新状态
写回 `state/research_state.json`，更新假设队列和轮次。

### Step 6: 写报告
写入 `reports/round_{当前轮次}.md`

## 可用 K 线形态列
doji, inside_bar, engulfing_bull, engulfing_bear, hammer, shooting_star, pin_bar,
marubozu_bull, marubozu_bear, tweezer_top, tweezer_bottom, harami_bull, harami_bear,
three_white_soldiers, three_black_crows, morning_star, evening_star,
bull_reversal, bear_reversal, bull_continuation, bear_continuation

## 标准列
open, high, low, close, rsi14, atr14, ma20, ma50, ma200,
bb_upper, bb_lower, pct_chg, gap_pct, hour, dayofweek, session
