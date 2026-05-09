#!/usr/bin/env python3
"""
Research Orchestrator (Phase A)
- Auto-discovers active strategies under the parent market directory.
- Aggregates scan logs to identify "blind spots" and performance clusters.
- Loads knowledge base to prevent re-researching known facts.
- Generates a `research_brief.md` for the AI Researcher.
"""

import os
import sys
import re
import json
import random
from pathlib import Path
from datetime import datetime, timedelta, timezone
import requests

# Path Config
SCRIPT_DIR = Path(__file__).parent.resolve()
MARKET_DIR = SCRIPT_DIR.parent.parent  # e.g., strategies/futures/
RESEARCH_DIR = SCRIPT_DIR.parent       # e.g., strategies/futures/research/
KB_PATH = RESEARCH_DIR / "knowledge_base.md"
BRIEFS_DIR = RESEARCH_DIR / "briefs"
EXPERIMENTS_DIR = RESEARCH_DIR / "experiments"
TEMPLATES_DIR = RESEARCH_DIR / "templates"
DEEP_DIVE_STATUS = BRIEFS_DIR / "deep_dive_status.json"

UTC8 = timezone(timedelta(hours=8))

# Import news filter
sys.path.insert(0, str(SCRIPT_DIR))
from news_filter import filter_and_summarize, to_markdown

# Tushare ClickHouse config (for trade calendar)
CH_URL = "http://172.24.224.1:8123/"
CH_AUTH = ("ai_reader", "OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ")

def discover_strategies():
    """Scan for all active strategy directories (single-agent or kanban)"""
    strategies = []
    # 1. Look for standard logs/scans
    for item in MARKET_DIR.rglob("logs"):
        if item.is_dir():
            scans_dir = item / "scans"
            if scans_dir.exists() and any(scans_dir.iterdir()):
                strategies.append(item.parent)
            elif any(item.glob("*.md")):
                # If logs dir itself has .md files
                strategies.append(item.parent)
    # Deduplicate
    return list(set(strategies))

def get_market_context(market):
    """Generate real-time market context for the Brief"""
    UTC8 = timezone(timedelta(hours=8))
    now = datetime.now(UTC8)
    today_str = now.strftime("%Y%m%d")
    tomorrow_str = (now + timedelta(days=1)).strftime("%Y%m%d")
    
    # Query trade calendar for next 7 days
    cal_data = []
    next_trade = None
    try:
        query = f"SELECT cal_date, is_open FROM _meta.trade_cal FINAL WHERE exchange='SSE' AND cal_date >= '{today_str}' AND cal_date <= '{(now + timedelta(days=7)).strftime('%Y%m%d')}' ORDER BY cal_date"
        r = requests.get(CH_URL, params={"query": query}, auth=CH_AUTH, timeout=10)
        for line in r.text.strip().split("\n"):
            parts = line.strip().split("\t")
            if len(parts) == 2:
                date_str, is_open = parts[0].replace("-", ""), int(parts[1])
                if is_open == 1 and next_trade is None:
                    next_trade = date_str
                cal_data.append((date_str, is_open))
    except:
        pass
    
    # Determine A-stock trading status
    is_a_stock_trading_day = False
    is_a_stock_market_open = False
    if cal_data:
        for d, o in cal_data:
            if d == today_str and o == 1:
                is_a_stock_trading_day = True
                # Check if currently in trading hours
                hour_min = now.hour * 60 + now.minute
                if (570 <= hour_min <= 690) or (780 <= hour_min <= 900):  # 09:30-11:30 or 13:00-15:00
                    is_a_stock_market_open = True
    
    # Futures/Forex session
    hour = now.hour
    weekday = now.weekday()  # 0=Mon, 6=Sun
    if weekday < 5:
        if 6 <= hour < 14:
            fx_session = "亚盘 (流动性低)"
        elif 14 <= hour < 20:
            fx_session = "欧盘 (流动性中)"
        elif 20 <= hour < 24 or 0 <= hour < 5:
            fx_session = "美盘 (流动性高)"
        elif 5 <= hour < 6:
            fx_session = "清算时段 (避免交易)"
        else:
            fx_session = "周末休市"
    else:
        fx_session = "周末休市"
    
    # Build context section
    lines = []
    lines.append("## 🕐 Market Context (Real-Time)")
    lines.append(f"\n**当前时间**: {now.strftime('%Y-%m-%d %H:%M:%S')} (UTC+8)")
    lines.append(f"**星期**: {now.strftime('%A')}")
    
    if market.upper() == "A-STOCK":
        lines.append(f"**今日是否交易日**: {'是' if is_a_stock_trading_day else '否'}")
        if is_a_stock_trading_day:
            lines.append(f"**当前是否盘中**: {'是' if is_a_stock_market_open else '否 (盘前/盘后)'}")
            lines.append(f"**A 股交易时段**: 09:30-11:30, 13:00-15:00 (UTC+8)")
        else:
            lines.append(f"**下一个交易日**: {next_trade if next_trade else '未知'}")
        lines.append(f"**⚠️ Tushare 数据更新时间**: 每日 22:00 前补齐当日数据。若当前 < 22:00，今日数据可能未就绪，请以昨日数据为主")
    else:
        lines.append(f"**当前交易时段**: {fx_session}")
        lines.append(f"**外汇/黄金/原油**: 06:00-次日04:00 (UTC+8), 周末休市")
        lines.append(f"**美股指数期货**: 21:30-04:00 (UTC+8)")
        lines.append(f"**JP225**: 08:00-14:00 + 15:00-03:30 (UTC+8)")
        lines.append(f"**清算时段**: 04:00-06:00 (UTC+8) 避免交易")
        if not (0 <= weekday < 5):
            lines.append(f"**⚠️ 当前周末**: 外汇/期货/美股指数均休市")
    
    # Next trading days schedule
    if cal_data:
        lines.append(f"\n**未来 7 天交易日历**:")
        for d, o in cal_data:
            icon = "🟢" if o == 1 else "🔴"
            lines.append(f"  {icon} {d} ({'交易日' if o == 1 else '休市'})")
    
    lines.append("")
    return "\n".join(lines)

def analyze_strategy_logs(strategy_path):
    """Extract scan summaries and recent context from logs"""
    scan_dir = strategy_path / "logs" / "scans"
    logs_dir = strategy_path / "logs"
    context_snippets = []
    
    # Determine which dir to search
    target_dir = scan_dir if scan_dir.exists() else logs_dir
    
    if not target_dir.exists():
        return {"name": strategy_path.name, "context": []}

    # Get recent files (handle nested date folders)
    files = sorted(target_dir.rglob("*.md"), key=os.path.getmtime, reverse=True)[:3]
    
    for f in files:
        try:
            content = f.read_text(encoding="utf-8")
            # 1. Try Futures format
            if "扫描总结" in content:
                snippet = content.split("扫描总结")[1].split("\n")[0].strip(": *")
                context_snippets.append(f"- **{f.name}**: {snippet}")
            elif "核心认知" in content:
                snippet = content.split("核心认知")[1].split("\n")[0].strip(": >*")
                context_snippets.append(f"- **{f.name}**: {snippet}")
            # 2. Try A-Stock format (Headers)
            elif "## 一、当前市场判断" in content:
                snippet = content.split("## 一、当前市场判断")[1].split("\n\n")[0].strip()
                context_snippets.append(f"- **{f.name}**: {snippet[:100]}...")
            # 3. Fallback: First 200 chars
            else:
                snippet = content[:200].replace("\n", " | ")
                context_snippets.append(f"- **{f.name}**: {snippet}...")
        except:
            pass

    return {
        "name": strategy_path.name,
        "path": str(strategy_path.relative_to(MARKET_DIR)),
        "context": context_snippets
    }

def get_tools_and_data(market):
    """Return market-specific available tools and data sources"""
    
    futures_tools = """
## 🛠️ Available Tools & Data (Futures)

### 1. MT5 (MetaTrader 5) — 实时行情 + 持仓 + 账户
- **路径**: `C:\\Program Files\\MetaTrader 5\\terminal64.exe`
- **品种后缀**: `m` (Exness) — 如 `XAUUSDm`, `USOILm`, `USTECm`
- **Python**: `import MetaTrader5 as mt5`
- **可用数据**: D1/H1/M15 K线、tick 价格、账户净值/保证金、持仓/SL/TP
- **参考脚本**: `../single-agent/pure-ai-cio/scripts/pre_analyze.py` (可直接复制修改)

### 2. Global Futures (Yahoo Finance) — 外盘商品/指数历史
- **脚本**: `/mnt/f/AIcoding_space/skills/global-futures/scripts/global_futures.py`
- **用法**: `from global_futures import GlobalFutures; gf = GlobalFutures()`
- **覆盖品种**: 黄金、白银、原油、布油、铜、玉米、大豆、天然气、10Y/30Y 美债、纳指/道指/标普
- **API**: `gf.get_history(name, period="3mo", interval="1d")` / `gf.get_all_prices()`

### 3. News Pipeline — 实时财经新闻 (9 数据源)
- **URL**: `http://127.0.0.1:8900` (Docker 服务)
- **覆盖**: eastmoney, 新浪财经, BBC, 华尔街见闻, Bloomberg, Reuters, 金十数据, 财联社, 同花顺
- **分类**: `futures`, `forex`, `a_shares`, `global_macro`, `political`, `crypto`
- **API 用法**:
  ```python
  import requests
  # 最近 40 分钟期货新闻
  r = requests.get("http://127.0.0.1:8900/api/v1/news/latest?minutes=40&category=futures&limit=30")
  # 按品种搜索
  r = requests.get("http://127.0.0.1:8900/api/v1/news/query?symbol=原油")
  ```
- **CLI 脚本**: `/mnt/f/AIcoding_space/skills/news-pipeline/scripts/news.py`
- **参考 Skill**: `news-pipeline` (完整 API 文档 + 分类关键词)
- **⚠️ 使用规范 (研究场景)**:
  - **不要全量拉取**: 每次查询必须带 `category` 和 `minutes` 参数，限制范围
  - **当"事件日历"用**: 提取重大事件的时间戳（如央行决议、非农、OPEC 会议），与价格数据做事件研究 (Event Study)
  - **不要逐条分析**: 新闻文本噪音极高，研究时应做关键词聚合/聚类，而不是逐条阅读
  - **用于验证而非发现**: 当你发现价格异动后，用 News Pipeline 查"当时发生了什么"，而不是反过来
  - **研究建议**: 用 `query?symbol=关键词` 搜索特定品种/板块的历史新闻，构建事件时间线

### 4. Tavily MCP — 补充搜索 (非主要)
- **Hermes 内置**: 可用于补充搜索 Tavily 未覆盖的事件
- **说明**: 优先使用 News Pipeline，Tavily 作为补充

### 5. Tushare ClickHouse (只读) — 全球期货数据
- **URL**: `http://172.24.224.1:8123/`
- **User**: `ai_reader`
- **说明**: 主要用于 A 股，但也包含期货合约数据
- **查询方式**: `requests.get(url, params={'query': sql}, auth=(user, pwd))`

### 💡 回测建议
- **数据量要求**: 回测至少需要 **2 年以上** 历史数据以保证统计显著性。短线/波段策略可用 H1/M15，趋势策略优先 D1
- **⚠️ 数据范围**: 写 SQL 查询时，**不要硬编码当前年份**作为起始日期！先查询表的实际日期范围（`SELECT min(trade_date), max(trade_date) FROM ...`），然后使用全部可用历史数据。样本量不足会导致统计检验不可靠。
- **Python 环境**: `C:\\Users\\gj\\AppData\\Local\\Programs\\Python\\Python312\\python.exe`
- **已安装库**: pandas, numpy, scipy, matplotlib, mplfinance, yfinance, MetaTrader5, backtrader, ta, statsmodels
- 使用 MT5 的 `copy_rates_from_pos` 获取历史 OHLCV
- 用 `ta` 库计算技术指标 (RSI, MACD, ATR, Bollinger Bands)
- 用 `backtrader` 做回测 (支持手续费/滑点/多品种)
- 用 `statsmodels` 做统计检验 (ADF 平稳性, Granger 因果, 回归分析)
- 用 `mplfinance` 绘制 K 线图
- 用 `numpy` 做相关性、显著性检验
"""

    a_stock_tools = """
## 🛠️ Available Tools & Data (A-Stock)

### 1. Tushare ClickHouse (主数据源) — 167 张表，覆盖 A 股全量数据
- **URL**: `http://172.24.224.1:8123/`
- **User**: `ai_reader` / **Password**: `OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ`
- **⚠️ 无分钟级数据**: 只有日线及以上粒度
- **覆盖**: 5729 只股票，2019-12-30 至 2026-05-07，753 万+条日线记录
- **📖 表结构文档**: 加载 `tushare-db-fast` Skill 查看所有 167 张表的结构、关键字段和 SQL 示例

#### 🚨 Schema 防呆卡 (Schema Cheat Sheet) — 严禁张冠李戴!
**AI 写代码前必须查阅此表，若需的字段不在对应表中，必须换表查询，严禁幻觉!**

| 字段名 | 正确归属表 | 常见错误 | 说明 |
| :--- | :--- | :--- | :--- |
| `turnover_rate` (换手率) | **`daily_basic`** | ❌ 误用于 `tushare_stock_daily` | 包含 pe, pb, total_mv, circ_mv |
| `open`, `high`, `low`, `close` | **`tushare_stock_daily`** | ❌ 误用于 `daily_basic` | 基础行情 OHLC |
| `vol`, `amount`, `pct_chg` | **`tushare_stock_daily`** | ❌ 误用于 `daily_basic` | 成交量、成交额、涨跌幅 |
| `pe`, `pe_ttm`, `pb`, `ps` | **`daily_basic`** | ❌ 误用于 `tushare_stock_daily` | 估值指标 |
| `buy_sm_vol`, `sell_lg_vol` | **`moneyflow`** | ❌ 误用于 `tushare_stock_daily` | 资金流向 (小/中/大/超大单) |
| `limit_type`, `first_time` | **`limit_list_d`** | ❌ 误用于 `tushare_stock_daily` | 涨跌停统计 |
| `concept_name`, `ts_code` | **`concept_detail`** |  误用于 `tushare_stock_daily` | 概念成分股 |

**🔒 铁律**: 
1. 写 SQL 前，**必须先确认字段在哪个表**。
2. 如果不确定，**先去查 `daily_basic`**，不要默认都在行情表里。
3. 使用 `JOIN` 时需通过 `ts_code` 和 `trade_date` 关联，且两表都要加 `FINAL`。

- **主要数据类别**:
  - 日线行情: `tushare_stock_daily`, `daily_basic` (PE/PB/市值/换手率), `adj_factor` (复权)
  - 资金流向: `moneyflow` (小/中/大/超大单), `moneyflow_hsgt` (北向资金), `moneyflow_ths` (同花顺板块)
  - 涨停/龙虎榜: `limit_list_d` (涨停统计), `top_list`, `top_inst` (龙虎榜)
  - 概念/板块: `concept_detail` (概念成分股), `ths_index` (同花顺指数), `ths_daily`
  - 财报: `income` (利润表), `balancesheet` (资产负债表), `cashflow` (现金流), `fina_indicator` (财务指标)
  - 指数: `index_daily`, `index_weight` (成分权重), `index_member_all`
  - 期货/宏观: `fut_daily`, `cn_pmi`, `cn_cpi`, `cn_m`, `shibor`
  - 其他: 基金(`fund_daily`), 可转债(`cb_daily`), 融资融券(`margin`), 持仓分析(`cyq_perf`, `stk_factor_pro`)
- **查询方式**:
  ```python
  import requests
  url = 'http://172.24.224.1:8123/'
  auth = ('ai_reader', 'OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ')
  # ⚠️ 必须加 FINAL (ReplacingMergeTree 去重)
  query = "SELECT ts_code, trade_date, close, vol, pct_chg FROM tushare.tushare_stock_daily FINAL WHERE ts_code = '000001.SZ' AND trade_date >= '20200101' FORMAT TabSeparatedWithNames"
  r = requests.get(url, params={'query': query}, auth=auth, timeout=30)
  ```
- **参考脚本**: `../kanban/screening/kanban/strategy/a-stock-shortline/scripts/query_tushare.py`

### 2. Global Futures (Yahoo Finance) — 全球市场/外盘/大宗商品
- **脚本**: `/mnt/f/AIcoding_space/skills/global-futures/scripts/global_futures.py`
- **覆盖**: 油价、黄金、美元指数、美债、VIX、纳指/标普 (A 股情绪参考)
- **API**: `gf.get_history(name, period="3mo", interval="1d")`

### 3. News Pipeline — 实时财经新闻 (9 数据源)
- **URL**: `http://127.0.0.1:8900` (Docker 服务)
- **覆盖**: eastmoney, 新浪财经, BBC, 华尔街见闻, Bloomberg, Reuters, 金十数据, 财联社, 同花顺
- **分类**: `a_shares`, `futures`, `global_macro`, `political`, `forex`, `crypto`
- **API 用法**:
  ```python
  import requests
  # 最近 40 分钟 A 股新闻
  r = requests.get("http://127.0.0.1:8900/api/v1/news/latest?minutes=40&category=a_shares&limit=30")
  # 按品种/板块搜索
  r = requests.get("http://127.0.0.1:8900/api/v1/news/query?symbol=芯片")
  ```
- **CLI 脚本**: `/mnt/f/AIcoding_space/skills/news-pipeline/scripts/news.py`
- **参考 Skill**: `news-pipeline` (完整 API 文档 + 分类关键词)
- **⚠️ 使用规范 (研究场景)**:
  - **不要全量拉取**: 每次查询必须带 `category` 和 `minutes` 参数，限制范围
  - **当"事件日历"用**: 提取重大事件的时间戳（如政策发布、财报季、板块利好），与价格数据做事件研究
  - **不要逐条分析**: 新闻文本噪音极高，研究时应做关键词聚合/聚类，而不是逐条阅读
  - **用于验证而非发现**: 当你发现板块异动后，用 News Pipeline 查"当时发生了什么"，而不是反过来
  - **研究建议**: 用 `query?symbol=板块/概念名` 搜索特定板块的历史新闻，构建事件时间线

### 4. Tavily MCP — 补充搜索 (非主要)
- **Hermes 内置**: 可用于补充搜索 Tavily 未覆盖的事件
- **说明**: 优先使用 News Pipeline，Tavily 作为补充

### 5. MT5 (Exness) — 全球期货/外汇 (跨市场关联分析)
- **路径**: `C:\\Program Files\\MetaTrader 5\\terminal64.exe`
- **品种**: `XAUUSDm`, `USOILm`, `DXY`(替代), `USTECm`
- **用途**: 分析 A 股与全球市场的跨资产相关性

### 💡 回测建议
- **数据量建议**: 回测至少需要 **2 年以上** 历史数据以保证统计显著性。短线/波段策略可用 H1/M15，趋势策略优先 D1
- 用 ClickHouse 直接 SQL 查询获取大量历史数据 (极快)
- 用 pandas 做连板分析、溢价率统计、量价关系
- 用 numpy 做显著性检验、相关性分析

### 🚨 SCHEMA CHEAT SHEET (MUST CHECK)
**CRITICAL**: `turnover_rate` (换手率), `pe`, `pb` are **NOT** in `tushare_stock_daily`!
You MUST use `tushare_daily_basic` for these fields.

| Field | Table Name |
|-------|------------|
| `turnover_rate`, `pe`, `pb`, `total_mv` | `tushare.tushare_daily_basic FINAL` |
| `open`, `high`, `low`, `close`, `vol` | `tushare.tushare_stock_daily FINAL` |
| `buy_sm_vol`, `sell_lg_vol` | `tushare.tushare_moneyflow FINAL` |
| `limit_times`, `limit_type` | `tushare.tushare_limit_list_d FINAL` |
| `concept_name`, `ts_code` | `tushare.tushare_concept_detail FINAL` |

**Rule**: Always check this table before writing SQL. If you hallucinate a field in the wrong table, the backtest will fail.
"""

    return futures_tools if market.upper() == "FUTURES" else a_stock_tools

def _init_experiment_workspace(exp_path, brief_path):
    """Initialize experiment workspace with templates and brief link"""
    # Copy backtest template
    bt_template = TEMPLATES_DIR / "backtest_template.py"
    if bt_template.exists():
        import shutil
        shutil.copy2(bt_template, exp_path / "backtest.py")
    
    # Create report.md skeleton
    report_content = f"""# 📊 Research Report

**Date**: {datetime.now(UTC8).strftime("%Y-%m-%d %H:%M")} (UTC+8)
**Brief**: `{brief_path.name}`
**Market**: {MARKET_DIR.name.upper()}

---

## 🎯 Research Question

<!-- What hypothesis are you testing? -->

## 📐 Methodology

<!-- How did you test it? Data sources, scripts, statistical methods. -->

## 📈 Results

<!-- Key findings, backtest performance, statistical significance. -->

## 💡 Conclusion

<!-- What does this mean for the trading strategy? -->

## 📝 Proposal

<!-- If validated, draft a proposal for the user to review. -->
"""
    (exp_path / "report.md").write_text(report_content, encoding="utf-8")
    
    # Create proposal.md skeleton
    proposal_content = """# 📜 Proposal: [Strategy Name]

**Status**: 🟡 Draft  
**Linked Experiment**: `[experiment_id]`  
**Target Strategy**: `[strategy_path]`

## 🚨 Problem Statement

<!-- What issue does this rule address? -->

## 💡 Proposed Rule

<!-- Describe the rule in clear logic. -->

## 📊 Expected Impact

| Metric | Before | After | Source |
|--------|--------|-------|--------|
| Win Rate | - | - | Backtest |
| Max Drawdown | - | - | Backtest |
| Trade Frequency | - | - | Backtest |

## 📋 Implementation Checklist

- [ ] Update `skills/risk-rules.md` (or relevant file)
- [ ] Update data fetch scripts if needed
- [ ] Backtest on out-of-sample data
- [ ] User review and approval

## 📝 Reviewer Notes

*Pending user approval.*
"""
    (exp_path / "proposal.md").write_text(proposal_content, encoding="utf-8")
    
    # Create README for experiment
    readme_content = f"""# Experiment: {exp_path.name}

**Brief**: `{brief_path.name}`
**Status**: 🔄 In Progress

## Files
- `report.md` - Research findings
- `proposal.md` - Strategy proposal (if validated)
- `backtest.py` - Backtest script (fill in logic)

## How to Run
```bash
# Windows Python environment
C:/Users/gj/AppData/Local/Programs/Python/Python312/python.exe backtest.py
```
"""
    (exp_path / "README.md").write_text(readme_content, encoding="utf-8")
    
    # Create status.json for tracking
    import json
    status = {
        "exp_id": exp_path.name,
        "created_at": datetime.now(UTC8).isoformat(),
        "status": "in_progress",
        "brief": brief_path.name,
        "market": MARKET_DIR.name.upper(),
        "report_done": False,
        "proposal_done": False,
    }
    (exp_path / "status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")


def load_knowledge_base():
    known_facts = []
    if KB_PATH.exists():
        content = KB_PATH.read_text(encoding="utf-8")
        # Extract headers or list items as facts
        lines = content.split("\n")
        for line in lines:
            if line.startswith("##") or line.startswith("- "):
                clean = line.lstrip("#- ")
                if len(clean) > 10:
                    known_facts.append(clean)
    return known_facts

def parse_user_topics():
    """Parse USER_TOPIC.md and return a list of topics (dicts)"""
    user_topic = BRIEFS_DIR / "USER_TOPIC.md"
    if not user_topic.exists():
        return []
    
    text = user_topic.read_text(encoding="utf-8")
    # Split by "### 主题 X：", but capture the name
    # Example line: "### 主题 A：低开高走模式识别 (Low Open High Go)"
    pattern = r'### 主题\s+\S+：(.*?)\n'
    parts = re.split(pattern, text)
    
    # parts will be: [header, "Topic Name 1", "Content 1", "Topic Name 2", "Content 2"...]
    topics = []
    # Iterate by 2s starting from index 1
    for i in range(1, len(parts), 2):
        if i + 1 < len(parts):
            name = parts[i].strip()
            content = parts[i+1].strip()
            if len(content) > 20:
                # Guess suffix
                suffix = "_user"
                if "低" in name or "low" in name.lower(): suffix = "_lowopen"
                elif "衰" in name or "竭" in name or "bottom" in name.lower(): suffix = "_exhaustion"
                elif "升" in name or "主升" in name or "breakout" in name.lower(): suffix = "_breakout"
                
                topics.append({
                    "name": name,
                    "content": content,
                    "suffix": suffix
                })
    return topics

def check_topic_saturation(topic_name, topic_suffix):
    """Check if a topic is saturated (too many recent failures)"""
    # Find recent experiments matching this suffix
    recent_exps = sorted(EXPERIMENTS_DIR.glob(f"*{topic_suffix}"))
    # Check last 3 experiments
    failures = 0
    if recent_exps:
        for exp_path in recent_exps[-3:]:
            status_file = exp_path / "status.json"
            if status_file.exists():
                with open(status_file, 'r') as f:
                    status = json.load(f)
                # If no proposal was generated, count as failure/stagnation
                if not status.get("proposal_done", False):
                    failures += 1
    return failures >= 3

def manage_deep_dive():
    """Manage Deep Dive Mode logic"""
    topics = parse_user_topics()
    if not topics:
        return None

    # Load status
    status = {}
    if DEEP_DIVE_STATUS.exists():
        with open(DEEP_DIVE_STATUS, 'r') as f:
            status = json.load(f)
    
    current_idx = status.get("current_idx", 0)
    current_name = status.get("current_name", "")
    reset = False
    
    # Check if we need to switch
    if current_idx >= len(topics):
        current_idx = 0 # Loop back to start? Or stop? Let's loop for now.
        
    # Check saturation for current
    current_topic = topics[current_idx]
    if check_topic_saturation(current_topic["name"], current_topic["suffix"]):
        print(f"💤 Topic '{current_topic['name']}' seems saturated. Switching...")
        current_idx += 1
        reset = True
    elif current_name and current_name != current_topic["name"]:
        # If manual change in config? No, let's just trust the index.
        pass
        
    # Update status
    new_status = {
        "current_idx": current_idx,
        "current_name": topics[current_idx]["name"],
        "last_run": datetime.now(UTC8).isoformat()
    }
    with open(DEEP_DIVE_STATUS, 'w') as f:
        json.dump(new_status, f, indent=2)
        
    return topics[current_idx]

def generate_brief(strategies_data, known_facts):
    """Generate the Markdown Brief + initialize experiment workspace"""
    now = datetime.now(UTC8)
    now_str = now.strftime("%Y-%m-%d %H:%M")
    
    # --- Step 0: Ensure directories exist ---
    BRIEFS_DIR.mkdir(parents=True, exist_ok=True)
    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
    
    # --- Step 0b: Check for user-specified research topic ---
    user_topic = BRIEFS_DIR / "USER_TOPIC.md"
    use_user_topic = user_topic.exists()
    
    # Logic for Deep Dive (Weekend)
    now = datetime.now(UTC8)
    is_weekend = now.weekday() >= 5 # Sat=5, Sun=6
    deep_dive_active = is_weekend and use_user_topic
    
    selected_topic = None
    selected_topic_content = ""
    topic_suffix = "_auto"
    
    if deep_dive_active:
        print("🔥 Weekend Deep Dive Mode: Locking onto topics...")
        selected_topic = manage_deep_dive()
        if selected_topic:
            print(f" Locked Topic: {selected_topic['name']}")
            use_user_topic = True
            selected_topic_content = selected_topic["content"]
            topic_suffix = selected_topic["suffix"]
        else:
            print("⚠️ Deep Dive paused or no topics available. Fallback to random.")
            deep_dive_active = False
            
    # Fallback for random user topic selection (non-weekend)
    if use_user_topic and not deep_dive_active:
        # 50/50 轮转
        use_user_topic = random.choice([True, False])
        if use_user_topic:
            print(f"🎯 Using user-specified topic: USER_TOPIC.md")
            # Randomly pick one topic for the brief
            all_topics = parse_user_topics()
            if all_topics:
                selected_topic = random.choice(all_topics)
                selected_topic_content = selected_topic["content"]
                topic_suffix = selected_topic["suffix"]
            else:
                use_user_topic = False
        else:
            print(f"🤖 AI self-discovery mode — skipping user topic this round")
    
    # --- Step 1: Generate filtered news summary ---
    print("📰 Filtering news feed...")
    if MARKET_DIR.name.lower() in ("futures",):
        news_categories = ["futures", "forex", "global_macro"]
        news_minutes = 360  # 6h window for futures
    else:
        news_categories = ["a_shares", "global_macro", "political"]
        news_minutes = 1440  # 24h window for A-stock (post-close)
    
    try:
        news_events = filter_and_summarize(
            categories=news_categories,
            minutes=news_minutes,
            min_score=5.0,
            max_events=10,
        )
        news_md = to_markdown(news_events, title_prefix=f"Filtered News ({news_minutes//60}h Window)")
        print(f"✅ News filtered: {len(news_events)} high-signal events")
    except Exception as e:
        print(f"⚠️ News filter failed: {e}")
        news_md = "## 📰 News Feed\n\n> ⚠️ News Pipeline service unavailable. Skipping news summary.\n\n"
    
    # --- Step 2: Create Brief ---
    brief_id = now.strftime("%Y%m%d_%H%M")
    brief_path = BRIEFS_DIR / f"{brief_id}.md"
    
    # Find latest experiment for naming
    existing = sorted(EXPERIMENTS_DIR.glob("2026*"))
    exp_version = len([e for e in existing if e.is_dir() and not e.name.startswith("0000")]) + 1
    
    # Topic selection logic (Deep Dive or Random) is handled in Step 0b above.
    # Ensure variables are set if not already (default safety)
    if 'topic_suffix' not in locals(): topic_suffix = "_auto"
    if 'selected_topic_content' not in locals(): selected_topic_content = ""
    if 'selected_topic' not in locals(): selected_topic = None

    exp_id = f"{now.strftime('%Y%m%d')}_v{exp_version}{topic_suffix}"
    exp_path = EXPERIMENTS_DIR / exp_id
    exp_path.mkdir(parents=True, exist_ok=True)
    
    # Initialize experiment files
    _init_experiment_workspace(exp_path, brief_path)
    
    md = f"""# 📡 Research Brief ({"User-Specified" if use_user_topic else "Auto-Generated"})
**Time**: {now_str}
**Market**: {MARKET_DIR.name.upper()}
**Experiment Workspace**: `experiments/{exp_id}/`

---

{get_market_context(MARKET_DIR.name)}

## 🎯 Research Topic
"""

    # Insert user-specified topic if exists
    if use_user_topic:
        topic_name = selected_topic["name"] if selected_topic else "User Topic"
        md += f"## 🎯 Selected User Topic: {topic_name}\n\n"
        md += selected_topic_content
        md += "\n\n"
        
        # Add Deep Dive Instruction
        if deep_dive_active:
            md += "### 🔥 Deep Dive Instruction\n"
            md += "You are in **Deep Dive Mode**. The system has locked onto this specific topic.\n"
            md += "1. **Check Known Facts**: Do NOT repeat experiments that have already failed (check `knowledge_base.md` and `Known Facts`).\n"
            md += "2. **Iterate Aggressively**: Try new parameters, new filters, or new data dimensions.\n"
            md += "3. **Goal**: Find a statistically significant alpha. If you fail, the system will switch topics in the next run.\n\n"
    else:
        md += "## 🧭 AI Research Instructions\n\nYou are the Lead Researcher. Based on the diagnostic data below, **propose and execute a research experiment**.\n\n"
        md += "### 🎯 Your Goal\n1. **Analyze** the strategy blind spots and market context below.\n2. **Formulate** 1-2 hypotheses that could improve risk-adjusted returns or reduce drawdowns.\n3. **Check** against the [Known Facts](#-known-facts) to avoid re-discovering the wheel.\n4. **Execute** the experiment in this directory (`{exp_path.name}/`).\n5. **Output** a `report.md` with your findings and a `proposal.md` if you found something actionable.\n6. **🔬 自动孵化**: 如果实验验证通过 (statistically significant positive result)，**立即调用孵化脚本**将策略转为影子模式。\n\n### 🔬 孵化流程 (自动)\n如果研究结果有效:\n```\npython scripts/incubate.py {exp_path.absolute()} <简短策略英文名> {MARKET_DIR.name}\n```\n这会自动创建 `experimental/<策略名>/` 影子模式策略，包含完整规则、状态追踪和扫描 prompt。\n孵化后在 report.md 末尾注明：`🔬 已孵化为 experimental 策略: <策略名>`\n\n"
        md += "### ⚠️ Important\n- Do NOT modify files outside this experiment directory.\n- Do NOT blindly verify known facts. Look for *new* patterns or edge cases.\n\n"

    md += "---\n\n## 🩺 Strategy Diagnostics\n\n"

    # --- Insert filtered news before Strategy Diagnostics ---
    md += news_md
    md += "\n"

    # Per-Strategy Stats
    for s in strategies_data:
        md += f"### Strategy: `{s['name']}`\n"
        md += f"- **Path**: `{s['path']}`\n"
        if s['context']:
            md += "- **Recent Context**:\n"
            for ctx in s['context']:
                md += f"  {ctx}\n"
        else:
            md += "- **Status**: No recent logs found.\n"
        md += "\n"

    # Known Facts
    md += "## 📚 Known Facts (Avoid Redundancy)\n\n"
    if known_facts:
        for fact in known_facts[-10:]: # Show last 10
            md += f"- {fact}\n"
    else:
        md += "- (No known facts recorded yet. You are the pioneer.)\n"

    md += "\n---\n*Generated by Orchestrator v2.0*\n"

    # Append Tools & Data
    md += get_tools_and_data(MARKET_DIR.name)

    brief_path.write_text(md, encoding="utf-8")
    print(f"✅ Brief saved: {brief_path}")
    print(f"🧪 Experiment workspace: {exp_path}")
    print(f"💡 Next Step: AI Agent reads brief, works in experiment folder.")

if __name__ == "__main__":
    print("🔍 Orchestrator Starting...")
    strategies = discover_strategies()
    print(f"📦 Discovered {len(strategies)} active strategies.")
    
    data = [analyze_strategy_logs(s) for s in strategies]
    known = load_knowledge_base()
    
    generate_brief(data, known)
