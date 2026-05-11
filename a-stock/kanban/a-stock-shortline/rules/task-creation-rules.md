# A股 Kanban 任务创建规则

> 本文档记录 A股短线选股 Kanban 流水线的任务创建规范，所有 Cron Prompt 和 Orchestrator 必须遵守。
> 基于 2026-05-10 实际测试经验总结。

---

## 一、三段式流水线架构

```
盘后初筛 22:00（T1-T7）──→ 盘后收敛 22:30（T8-T14）──→ 盘前确认 08:30（T15-T17）
```

### 任务依赖链

```
T1(researcher) ─┐
T2(researcher) ─┤
T3(researcher) ─┼──→ T5(analyst) ──→ T6(analyst) ──→ T7(writer)
T4(researcher) ─┘

T8(researcher) ─┬──→ T9(analyst) ─┐
                ├──→ T10(analyst) ├→ T13(analyst) ──→ T14(writer)
                ├──→ T11(analyst) │
                └──→ T12(analyst) ┘

T15(researcher) ──→ T16(analyst) ──→ T17(writer)
```

---

## 二、数据查询工具规范

### 2.1 Tushare DB — 直连 ClickHouse

**脚本路径**：`/home/gjtmux/.hermes/skills/tushare-clickhouse-direct/scripts/ch_query.py`

```bash
# 任意 SQL
python3 /home/gjtmux/.hermes/skills/tushare-clickhouse-direct/scripts/ch_query.py sql "SELECT count(*) FROM tushare_stock_daily FINAL"

# 专用命令
python3 /home/gjtmux/.hermes/skills/tushare-clickhouse-direct/scripts/ch_query.py max_date        # 最新数据日期
python3 /home/gjtmux/.hermes/skills/tushare-clickhouse-direct/scripts/ch_query.py limits           # 涨停池
python3 /home/gjtmux/.hermes/skills/tushare-clickhouse-direct/scripts/ch_query.py north_flow       # 北向资金
python3 /home/gjtmux/.hermes/skills/tushare-clickhouse-direct/scripts/ch_query.py index_latest     # 五大指数
python3 /home/gjtmux/.hermes/skills/tushare-clickhouse-direct/scripts/ch_query.py calendar SSE 20260501 20260511
python3 /home/gjtmux/.hermes/skills/tushare-clickhouse-direct/scripts/ch_query.py ohlcv 000001.SZ 20260501 20260510
python3 /home/gjtmux/.hermes/skills/tushare-clickhouse-direct/scripts/ch_query.py moneyflow 000001.SZ 20260501 20260510
python3 /home/gjtmux/.hermes/skills/tushare-clickhouse-direct/scripts/ch_query.py financials 000001.SZ income
python3 /home/gjtmux/.hermes/skills/tushare-clickhouse-direct/scripts/ch_query.py describe tushare_stock_daily
python3 /home/gjtmux/.hermes/skills/tushare-clickhouse-direct/scripts/ch_query.py search 涨停
```

**硬规则**：
- 所有 SQL 必须加 `FINAL`（ReplacingMergeTree 去重）
- 日期格式统一 `YYYYMMDD`
- 直连比 MCP 快 5-10ms，本地环境无需安全顾虑

**⚠️ 字段名验证 — 使用真实存在的字段**：

| 表 | 正确字段 | ❌ 不存在的字段 |
|---|---------|---------------|
| `tushare_limit_list_d` | `limit`, `limit_times`, `first_time`, `last_time` | ~~`fc_ratio`~~ |
| `tushare_moneyflow_hsgt` | `north_money`, `south_money`, `hgt`, `sgt` | ~~`gg_buy`~~, ~~`gg_sell`~~ |
| `tushare_kpl_concept_cons` | `concept_name`, `ts_code` | ~~`tushare_concept_detail`~~（表不存在） |

不确定时先用 `ch_query.py describe <表名>` 确认字段。

### 2.2 外盘行情 — MT5 + global-futures

```python
# MT5（Windows Python312）
/mnt/c/Users/gj/AppData/Local/Programs/Python/Python312/python.exe -c "
import MetaTrader5 as mt5
mt5.initialize()
tick = mt5.symbol_info_tick('US30')
mt5.shutdown()
"

# global-futures
python3 -c "
import sys; sys.path.insert(0, '/mnt/f/AIcoding_space/skills/global-futures/scripts')
from global_futures import GlobalFutures
gf = GlobalFutures()
print(gf.get_price('Gold'))
"
```

### 2.3 新闻搜索 — tavily-skills

```bash
export PYTHONPATH=/mnt/f/AIcoding_space/skills/tavily-skills:$PYTHONPATH
python3 -m tavily_manager search "A股 政策 2026" --max-results 10 --topic news --time-range week
```

**⚠️ 禁止用新闻工具查询价格/指数/汇率等数值行情。**

---

## 三、时间上下文注入规则

每个 `kanban_create` 任务的 `body` 开头必须注入：

```
## 📅 时间上下文（强制遵守）
- 系统执行时间：YYYY-MM-DD HH:mm UTC+8
- 今日日期：YYYY-MM-DD
- ⚠️ 规则：
  1. 日志文件名中的日期必须使用系统执行日期。
  2. 数据查询必须先运行 `ch_query.py max_date` 确认数据基准日期。
  3. 报告中的"基准日期"和"下一交易日"必须读取 T1 交易日历结果。
  4. 禁止使用"周一/周五"等推测词，统一使用 YYYY-MM-DD。
```

---

## 四、日志与报告路径

### 4.1 绝对路径（禁止相对路径）

```
策略目录：/mnt/f/AIcoding_space/Hermes/strategies/a-stock/kanban/a-stock-shortline/

日志：/mnt/f/AIcoding_space/Hermes/strategies/a-stock/kanban/a-stock-shortline/logs/
报告：/mnt/f/AIcoding_space/Hermes/strategies/a-stock/kanban/a-stock-shortline/reports/
```

**⚠️ Worker 的 scratch workspace 是独立的（各自 profile 下），不能假设 `./logs/` 指向策略目录。**

### 4.2 文件命名规范

```
初筛：screen-{YYYYMMDD}-{01..07}-{步骤名}.md
收敛：converge-{YYYYMMDD}-{08..14}-{步骤名}.md
盘前：preopen-{YYYYMMDD}-{15..17}-{步骤名}.md

最终报告：
  shortline-screen-{YYYYMMDDHHMM}.md    # 初筛报告
  shortline-candidates-{YYYYMMDDHHMM}.md  # 收敛报告
  preopen-check-{YYYYMMDDHHMM}.md        # 盘前报告
```

---

## 五、Profile 角色分配

| 任务 | Profile | 角色 | 说明 |
|------|---------|------|------|
| T1-T4 | researcher | 数据查询 | 交易日历/涨停/板块/新闻 |
| T5 | analyst | 财经专家 | 全市场扫描 |
| T6 | analyst | 主控初筛 | 压缩到 12-20 只 |
| T7 | writer | 报告 | 初筛报告 |
| T8 | researcher | 数据查询 | 逐票价格校验 |
| T9-T12 | analyst | 四专家 | 财经/科技/期货/政治 |
| T13 | analyst | 主控裁决 | 收敛到 6-10 只 |
| T14 | writer | 报告 | 收敛报告 |
| T15 | researcher | 数据查询 | 盘前外盘行情 |
| T16 | analyst | 主控 | 分层迁移 |
| T17 | writer | 报告 | 盘前报告 |

### 5.1 Soul 注入

每个任务 `body` 中必须追加对应 Soul：
- researcher: `你的核心工作原则请参考：./skills/researcher-soul.md。`
- analyst: `你的核心工作原则请参考：./skills/analyst-soul.md。`
- writer: `你的核心工作原则请参考：./skills/writer-soul.md。`

---

## 六、Cron Job 配置

| Job | 调度 | 模型 | 工作目录 |
|-----|------|------|---------|
| 初筛 | `0 22 * * 1-5` | deepseek-v4-flash | a-stock-shortline/ |
| 收敛 | `30 22 * * 1-5` | deepseek-v4-flash | a-stock-shortline/ |
| 盘前 | `30 8 * * 1-5` | deepseek-v4-flash | a-stock-shortline/ |

**注意**：收敛和盘前都用 flash，pro 模型曾导致 `[SILENT]` 静默失败。

---

## 七、已知陷阱清单

| # | 陷阱 | 表现 | 修复 |
|---|------|------|------|
| 1 | 周末手动触发 Cron | 模型识别非交易日返回 `[SILENT]` | Prompt 添加测试标记，或等待周一自动触发 |
| 2 | 日志写到 scratch workspace | 策略目录找不到日志 | 使用绝对路径 |
| 3 | 字段名不存在 | SQL 报 404 错误 | 先用 `describe` 确认字段 |
| 4 | 概念板块表不存在 | `tushare_concept_detail` 报错 | 改用 `tushare_kpl_concept_cons` |
| 5 | 涨停池 `fc_ratio` 不存在 | 字段不存在 | 改用 `limit` 字段 |
| 6 | 北向资金 `gg_buy` 不存在 | 字段不存在 | 改用 `hgt`/`sgt` |
| 7 | Worker profile kanban.db 隔离 | 任务找不到 | 软链接到 reze 的 kanban.db |
| 8 | pro 模型 Orchestrator | 返回 `[SILENT]` | 统一用 flash 模型 |

