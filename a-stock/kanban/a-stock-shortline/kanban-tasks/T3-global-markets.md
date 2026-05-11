# Kanban Task: T3 — MT5 全球行情 + global-futures 国际期货

| Field | Value |
|-------|-------|
| **Task ID** | T3 |
| **Name** | T3 — MT5 全球行情 + global-futures 国际期货 |
| **Status** | ✅ done |
| **Completed** | 2026-05-10 08:39 UTC+8 |
| **Assignee** | researcher |
| **Parents** | [] (无依赖) |
| **Created** | 2026-05-10 08:39 UTC+8 |
| **Priority** | high |

## 📅 时间上下文（强制遵守）
- 系统执行时间：2026-05-10 08:39 UTC+8
- 今日日期：2026-05-10
- 数据基准日期：2026-05-08（最近实际交易日）
- ⚠️ 规则：
  1. 日志文件名中的日期必须使用"今日日期"。
  2. 数据查询必须先运行：`SELECT max(trade_date) FROM tushare.tushare_stock_daily FINAL` 以确认"数据基准日期"。
  3. 报告中的"基准日期"必须写实际查询到的 `max_date`（YYYY-MM-DD）。
  4. 报告中的"下一交易日"必须读取 `./logs/screen-20260510-01-trade_cal.md`，引用其中的准确结论。
  5. 禁止使用"今天/明天/周一/周五"等模糊词汇，统一使用 YYYY-MM-DD。

## Skill/Soul 注入
你的核心工作原则请参考：`./skills/researcher-soul.md`。

## Task Body
你是数据研究员。获取全球市场最新行情并映射到 A 股对应板块。

第一部分：MT5 全球行情
通过 WSL 调用 Windows Python: /mnt/c/Users/gj/AppData/Local/Programs/Python/Python312/python.exe
必须用 inline -c 方式，try/finally 包裹 mt5.shutdown()。
获取以下 symbol 的 tick + 5 根 D1 K线（Python API 中不带 m 后缀）:
XAUUSD, USOIL, UKOIL, US30, US500, USTEC, JP225, HK50, USDCNH, USDJPY, BTCUSD

第二部分：global-futures 国际期货
脚本路径: /mnt/f/AIcoding_space/skills/global-futures/scripts/global_futures.py
sys.path.insert(0, r"/mnt/f/AIcoding_space/skills/global-futures/scripts")
from global_futures import GlobalFutures
gf = GlobalFutures()
获取以下品种的价格和近 3 个月趋势:
谷物: Corn, Soybean, Wheat, SoybeanMeal
软商品: Sugar11, Cotton, Canola
能源: CrudeOil, BrentOil, NaturalGas
金属: Gold, Silver, Copper
利率: Treasury10Y, Treasury30Y

对每个品种输出: 最新价格、涨跌幅、近 3 个月趋势方向、对 A 股的映射判断。
将结果写入日志：./logs/screen-20260510-03-global_markets.md
