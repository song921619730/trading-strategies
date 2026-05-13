#!/usr/bin/env python3
"""
Pipeline Orchestrator — Background poller for 盘后短线收敛 (T8-T14)

Waits for 盘后初筛 (T1-T7) to complete, then creates T8-T14 convergence tasks
with proper dependency chains.

Usage:
    python3 scripts/pipeline_orchestrator.py 2>&1 >> logs/pipeline_orchestrator.log &
"""

import sqlite3
import subprocess
import json
import time
import sys
import os
from datetime import datetime, timezone, timedelta

# Configuration
STRATEGY_DIR = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/kanban/a-stock-shortline"
KANBAN_DB = "/home/gjtmux/.hermes/profiles/reze/kanban.db"
TZ_CST = timezone(timedelta(hours=8))
TODAY = datetime.now(TZ_CST).strftime("%Y%m%d")
TODAY_HHMM = datetime.now(TZ_CST).strftime("%Y%m%d%H%M")
LOG_DIR = f"{STRATEGY_DIR}/logs"
REPORT_DIR = f"{STRATEGY_DIR}/reports"

# Task IDs from 盘后初筛 (T1-T7) — these must be existing tasks
# T7 is the final report generation task that we need to wait for
T7_ID = "t_7194b85d"  # T7: 报告生成 (20260512-盘后)

# Previously completed tasks from 初筛 phase
T1_ID = "t_a1cfd47a"  # 交易日历确认
T2_ID = "t_6efdeda3"  # A股日线扫描
T3_ID = "t_edc64dbe"  # 全球行情
T4_ID = "t_13a30295"  # 新闻搜索
T5_ID = "t_60229760"  # 财经专家全市场扫描
T6_ID = "t_c1371456"  # 主控初筛压缩


def log(msg):
    ts = datetime.now(TZ_CST).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def kanban_create(title, assignee, body, parents=None, max_runtime=600):
    """Create a Kanban task via CLI."""
    cmd = [
        "hermes", "kanban", "create", title,
        "--assignee", assignee,
        "--body", body,
        "--json"
    ]
    if parents:
        for p in parents:
            cmd.extend(["--parent", p])
    cmd.extend(["--max-runtime", str(max_runtime)])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            log(f"ERROR creating task '{title}': {result.stderr[:200]}")
            return None
        data = json.loads(result.stdout)
        task_id = data.get("id")
        log(f"Created task: {task_id} - {title} (assignee={assignee})")
        return task_id
    except subprocess.TimeoutExpired:
        log(f"TIMEOUT creating task '{title}'")
        return None
    except json.JSONDecodeError as e:
        log(f"JSON parse error: {e}, output: {result.stdout[:200]}")
        return None


def wait_for_task(task_id, timeout=7200, poll_interval=60):
    """Wait for a task to reach status 'done'."""
    log(f"Waiting for task {task_id} to complete (timeout={timeout}s)...")
    deadline = time.time() + timeout
    while time.time() < deadline:
        conn = sqlite3.connect(KANBAN_DB)
        row = conn.execute(
            "SELECT status, spawn_failures, last_spawn_error FROM tasks WHERE id=?",
            (task_id,)
        ).fetchone()
        conn.close()

        if row is None:
            log(f"WARNING: Task {task_id} not found in DB, retrying...")
            time.sleep(poll_interval)
            continue

        status = row[0]
        failures = row[1]
        error = row[2]

        if status == "done":
            log(f"Task {task_id} completed successfully.")
            return True
        elif failures and failures > 3:
            log(f"WARNING: Task {task_id} has {failures} spawn failures. Error: {error[:100] if error else 'None'}")
            # Continue waiting — it might still complete
        elif status in ("running", "ready", "todo"):
            pass  # Still in progress

        time.sleep(poll_interval)

    log(f"TIMEOUT: Task {task_id} did not complete within {timeout}s")
    return False


def create_time_context():
    """Generate the time context block for task bodies."""
    return f"""## 📅 时间上下文（强制遵守）
- 系统执行时间：{datetime.now(TZ_CST).strftime('%Y-%m-%d %H:%M')} UTC+8
- ⚠️ 规则：
  1. 日志文件名中的日期必须使用系统执行日期的日期部分（{TODAY}）。
  2. 数据基准日期：读取最新初筛报告（shortline-screen-*）中的日期。
  3. 报告中的"基准日期"和"下一交易日"必须基于初筛报告中的 T1 交易日确认结果。
  4. 禁止使用"周一/周五"等推测词，统一使用 YYYY-MM-DD。"""


def inject_soul(assignee):
    """Get the Soul injection line for a given assignee role."""
    souls = {
        "researcher": "你的核心工作原则请参考：`./skills/researcher-soul.md`。",
        "analyst": "你的核心工作原则请参考：`./skills/analyst-soul.md`。",
        "writer": "你的核心工作原则请参考：`./skills/writer-soul.md`。",
    }
    return souls.get(assignee, "")


def build_t8_body():
    time_ctx = create_time_context()
    soul = inject_soul("researcher")
    return f"""{time_ctx}

你是数据研究员。任务：对最新初筛候选池中每只票进行最新价和基本面校验。
{soul}

读取最新初筛报告：{REPORT_DIR}/
找到文件名以 shortline-screen- 开头的最新报告，从中提取候选股票代码列表（12-20 只）。

对每只票执行（使用 Tushare DB，SQL 必须加 FINAL，日期 YYYYMMDD）:

1. 最新 5 根日 K 线:
   SELECT ts_code, trade_date, open, high, low, close, vol, pct_chg
   FROM tushare.tushare_stock_daily FINAL
   WHERE ts_code = '{{code}}' AND trade_date >= '{{最近交易日-10}}'
   ORDER BY trade_date DESC LIMIT 5

2. 最新基本面指标:
   SELECT pe, pb, total_mv, circ_mv, turnover_rate, volume_ratio
   FROM tushare.tushare_daily_basic FINAL
   WHERE ts_code = '{{code}}' AND trade_date >= '{{最近交易日-10}}'
   ORDER BY trade_date DESC LIMIT 5

3. 最新资金流向（近 5 日）:
   SELECT trade_date, buy_sm_vol, sell_sm_vol, buy_md_vol, sell_md_vol,
          buy_lg_vol, sell_lg_vol, buy_elg_vol, sell_elg_vol
   FROM tushare.tushare_moneyflow FINAL
   WHERE ts_code = '{{code}}' AND trade_date >= '{{最近交易日-10}}'
   ORDER BY trade_date DESC LIMIT 5

4. 近 20 根日 K 线（技术分析用）:
   SELECT trade_date, open, high, low, close, vol, pct_chg
   FROM tushare.tushare_stock_daily FINAL
   WHERE ts_code = '{{code}}' AND trade_date >= '{{最近交易日-40}}'
   ORDER BY trade_date ASC LIMIT 40

输出：每只票的最新价、交易日期、PE/PB/市值/换手率、近 5 日资金流向摘要、近 20 根 K 线。
将校验结果写入日志：{LOG_DIR}/converge-{TODAY}-08-price_check.md"""


def build_t9_body():
    time_ctx = create_time_context()
    soul = inject_soul("analyst")
    return f"""{time_ctx}

你是财经专家。任务：对初筛候选池进行财经维度专项加减分。
{soul}

角色边界:
- 你负责提供板块强度和资金认可度的专业判断
- 你不代替主控宣布"已收敛"
- 你不给出最终可执行名单

财经专家核心能力（必须覆盖）:
1. 全市场强弱与板块梯队判断
2. 龙头/次龙/补涨/套利票/伪强势票区分
3. 板块内部位置比较（龙头/次龙/补涨/低位预备突破）
4. 资金是否已充分定价与预期差识别
5. 双周期模型：中国经济周期 vs 美国经济周期（房地产+出口 vs 消费+科技）
6. 资金联动模型：北向资金（配置盘vs交易盘）+ 南向资金 + 全球主权基金再平衡
7. 全市场强度与位置模型：涨停家数、首板数量、炸板率、量价结构、封单质量、梯队完整度
8. 短线新开仓模型：竞价预期、盘中承接、股性、辨识度、题材强度、次日空间与可执行性

你必须明确区分每只候选属于:
- 产业主线龙头 / 题材龙头 / 跟风补涨 / 套利票 / 伪强势票

搜索协议:
- 总搜索轮次不得超过 4 轮，总搜索词不得超过 16 个
- 绝对禁止用 tavily_search 查询价格/指数/汇率等数值行情
- 权威新闻源优先：Reuters, Bloomberg, CNBC, 金十数据, 华尔街见闻, 东方财富, AP News, BBC, WSJ, FT

输入数据: 读取 T8 日志 + 最新初筛报告。

对每只候选给出:
- 板块强度分/资金认可分/位置分/预期差分/次日空间分/个股交易性分/资金结构风险等级（0-5）
- 最大失败路径
- 是否建议降级 + 降级触发条件（最多 2 条）
- 触发条件与失效条件

输出"对主控输入"结构化块:
对 Reze 主框架输入：框架关系/情绪温度影响/风格影响/执行窗口/分项评分/最大失败路径/是否建议降级/降级触发条件/触发条件/失效条件

将分析结果写入日志：{LOG_DIR}/converge-{TODAY}-09-finance.md"""


def build_t10_body():
    time_ctx = create_time_context()
    soul = inject_soul("analyst")
    return f"""{time_ctx}

你是科技专家。任务：对初筛候选池进行科技/产业维度专项加减分。
{soul}

角色边界:
- 你负责提供科技产业链与成长主线的专业判断
- 你不代替主控宣布"已收敛"

科技专家六大分析模型（必须覆盖）:
1. 产业渗透率模型：判断行业是 0 到 1、1 到 10 还是 10 到 100 阶段
2. 技术路线胜率模型：判断技术路线是趋势性胜出还是阶段性炒作
3. 景气度传导模型：从订单、资本开支、价格、出货、库存五维度验证行业景气
4. 产业预期差模型：区分"已被市场充分定价"与"仍有预期差兑现空间"
5. 科技主题交易模型：区分"产业主升浪""事件脉冲""情绪补涨""纯概念套利"
6. 拥挤度与接盘风险模型：识别高位一致、拥挤交易与次日接盘风险

科技专家六大赛道拆解:
- 人工智能（大模型/算力/GPU/光模块/液冷/IDC）
- 机器人与智能制造
- 智能汽车
- 半导体
- 互联网与软件
- 商业航天与前沿科技

搜索协议:
- 总搜索轮次 <= 4，搜索词 <= 16
- 搜索按顺序分组：AI/算力 → 机器人 → 智能车 → 半导体 → 互联网/软件/商业航天
- 绝对禁止用 tavily_search 查询价格/涨跌幅/指数点位

对每只候选给出:
- 科技主线有效分/产业兑现度分/科技股股性分/产业预期差分/位置分/次日空间分/拥挤度接盘风险等级/伪概念风险等级
- 最大失败路径、是否建议降级、降级触发条件
- "对主控输入"结构化块

将分析结果写入日志：{LOG_DIR}/converge-{TODAY}-10-tech.md"""


def build_t11_body():
    time_ctx = create_time_context()
    soul = inject_soul("analyst")
    return f"""{time_ctx}

你是期货专家。任务：对初筛候选池进行大宗商品周期映射加减分。
{soul}

角色边界:
- 你负责评估大宗商品价格变化对 A 股对应板块的影响
- 你不代替主控宣布"已收敛"

核心原则:
- 商品涨跌不等于股票一定同步，必须说明映射路径和时滞
- 必须先判断"商品逻辑延续"vs"股票端是否已被充分定价"
- 空间优先于强度：必须评估映射剩余空间、拥挤风险、次日空间
- 不得只因商品强就升格股票候选

期货专家覆盖品种:
- 上期所：铜、铝、锌、镍、黄金、白银、原油、橡胶、螺纹
- 大商所：铁矿石、焦炭、焦煤、豆粕、豆油、棕榈油、玉米
- 郑商所：棉花、白糖、PTA、甲醇、玻璃、纯碱
- 广期所：工业硅、碳酸锂
- 股指期货：IF/IC/IM/IH
- 全球商品：WTI/Brent 原油、LME 铜铝锌、美豆/美玉米/美棉/美糖

搜索协议:
- 总搜索轮次 <= 4，搜索词 <= 16
- 搜索分组：综合主线与能源/宏观 → 贵金属与股指 → 黑色与有色 → 农产品/化工
- 绝对禁止用 tavily_search 查询价格/涨跌幅/点位/持仓量/基差/库存

对每只候选给出:
- 产业映射有效分/供需持续性分/时滞匹配分/映射剩余空间分/映射拥挤风险等级
- 对主控四项建议分（位置分/预期差分/次日空间分/接盘风险等级）
- 最大失败路径、是否建议降级、降级触发条件
- "对主控输入"结构化块

将分析结果写入日志：{LOG_DIR}/converge-{TODAY}-11-futures.md"""


def build_t12_body():
    time_ctx = create_time_context()
    soul = inject_soul("analyst")
    return f"""{time_ctx}

你是政治专家。任务：对初筛候选池进行政策/地缘催化加减分。
{soul}

角色边界:
- 你负责评估催化真实性和政策强度
- 你不代替主控宣布"已收敛"

政治专家核心能力（必须覆盖）:
1. 中国监管政策"三层解读法"：字面层 / 语境层 / 意图层
2. 事件催化持续性判断：1 天 / 3 天 / 1 周
3. 真消息与伪消息甄别
4. 政策边际变化对板块情绪的映射
5. 催化是否已 price-in 的识别：未定价 / 部分定价 / 已充分定价
6. 催化预期差与事件驱动剩余交易窗口识别

你必须明确判断每条催化属于: 真催化 / 弱催化 / 过时催化 / 伪催化
并判断定价状态：未定价 / 部分定价 / 已充分定价

搜索协议:
- 总搜索轮次 <= 4，搜索词 <= 16
- 搜索分组：中东/俄乌 → 中美欧/亚太 → 新兴市场 → 制裁与出口管制 → 能源与航运
- 优先权威来源：AP News, Reuters World, BBC, WSJ, FT, 纽约时报, 外交学者, 联合早报
- 绝对禁止用 tavily_search 查询价格/点位/涨跌幅/汇率/利率/油价/金价

对每只候选给出:
- 催化真实性分/催化预期差分/事件驱动剩余窗口分/外溢影响分/打脸风险等级/兑现衰减拥挤风险等级/定价状态
- 对主控分项修正建议
- 最大失败路径、是否建议降级、降级触发条件
- "对主控输入"结构化块

将分析结果写入日志：{LOG_DIR}/converge-{TODAY}-12-politics.md"""


def build_t13_body():
    time_ctx = create_time_context()
    soul = inject_soul("analyst")
    return f"""{time_ctx}

你是主控分析师。任务：汇总四专家加减分，完成最终裁决，收敛到 6-10 只候选并强制分层。
{soul}

这是四步裁决流的最后一步。

角色定义:
- 你是主控，负责流程协调、评分裁决与最终对外收敛
- 你是 A 股短线情绪周期研判、待涨型候选裁决与技术执行窗口专家
- 你是唯一可以宣布收敛的角色

Reze 核心能力（短线六锚点，必须覆盖）:
1. 情绪周期：启动、加速、高潮、分歧、退潮、冰点修复
2. 龙头梯队：龙一/龙二/补涨队列完整度
3. 量价结构：放量突破、缩量回踩、分歧转一致、量价背离
4. 执行窗口：竞价、开盘前30分钟、午后回流、尾盘确认
5. 关键价位：前高前低、开盘价、均线锚点、缺口、成交密集区
6. 待涨/接盘识别：位置拥挤度、预期差存量、次日空间与接盘风险

逐票待涨/接盘判定（必须执行）:
- 对每只候选显式判断"待涨票"或"接盘票"
- 判断位置拥挤度、预期差是否仍在、次日风险收益比是否仍有优势

输入数据: 读取 T8-T12 日志 + 最新初筛报告。

操作步骤:
第一步：确认情绪周期和权重重心
第二步：统一评分协议（汇总四专家评分，计算总分）
第三步：高位一致惩罚（硬性规则）:
  - 高位一致+接盘>=3+空间<=2 → 至少降级为观察
  - 高位一致+接盘>=4 → 默认降级为观察
  - 接盘>=4 且无新增强证据 → 移出主看层
第四步：收敛到 6-10 只:
  - 待涨观察池 >= 50%
  - 低位待涨+预备突破 >= 60%
  - 最终可执行层：优先跟踪 + 条件成立可执行 合计 2-4 只
  - 不得由当天已涨停票占据绝对多数
第五步：技术面双模块（每只保留候选必须有月度技术扫描 + 次日执行卡）
第六步：风险口径统一（综合风险等级 = max(专家均值, 接盘风险），风险扣分 = -综合等级）
第七步：复盘留痕（候选池保留/降级/淘汰 + 分项分 + 技术扫描 + 执行卡 + 错因初判）

每只候选必须包含:
标的/结论标签/所处分层/最新价+来源+retrievedAt/K线来源+retrievedAt/全部分项分/总分/接盘风险等级/月度技术扫描/次日执行卡/触发条件/失效条件/降级理由/待涨接盘判定

将分析结果写入日志：{LOG_DIR}/converge-{TODAY}-13-final.md"""


def build_t14_body():
    time_ctx = create_time_context()
    soul = inject_soul("writer")
    # Try to find the latest screen report for the trade_cal reference
    screen_report = find_latest_screen_report()
    cal_ref = screen_report if screen_report else "./logs/screen-{TODAY}-01-trade_cal.md"
    return f"""{time_ctx}

你是报告撰写人。任务：将主控最终裁决结果生成标准 markdown 报告。
{soul}

文件命名：shortline-candidates-{TODAY_HHMM}.md
保存到：{REPORT_DIR}/

⚠️ 强制要求：
在报告开头，读取 `{cal_ref}`（从初筛阶段）或最新的初筛报告，
准确引用"基准日期"和"下一交易日"。
禁止自行推测日期。

报告结构:
1. 当前市场判断（情绪周期/主线/全球环境）
2. 候选压缩结果（保留/排除清单）
3. 专项加减分框架（科技/期货/政治）
4. 三层候选池 + 结构检查
5. 最终候选排序
6. 最终候选卡（逐票完整字段，含月度技术扫描 + 次日执行卡）
7. 被降级/淘汰标的及原因
8. 下一次复核点

将生成的报告同时写入日志：{LOG_DIR}/converge-{TODAY}-14-report.md"""


def find_latest_screen_report():
    """Find the latest screening report file."""
    import glob
    reports = glob.glob(f"{REPORT_DIR}/shortline-screen-*.md")
    if reports:
        return max(reports, key=os.path.getmtime)
    return None


def main():
    log(f"{'='*60}")
    log(f"Pipeline Orchestrator started at {datetime.now(TZ_CST).isoformat()}")
    log(f"Strategy: {STRATEGY_DIR}")
    log(f"Today: {TODAY}")
    log(f"{'='*60}")

    # Phase 0: Wait for 盘后初筛 to complete (T1-T7)
    log(f"Phase 0: Waiting for 盘后初筛 (T1-T7) to complete...")

    # Wait for T7 (报告生成) which depends on T5+T6
    # But first check if T7 already exists and is done
    conn = sqlite3.connect(KANBAN_DB)
    t7_status = conn.execute("SELECT status FROM tasks WHERE id=?", (T7_ID,)).fetchone()
    conn.close()

    if t7_status is None:
        log(f"ERROR: T7 ({T7_ID}) not found in kanban.db! Something is wrong.")
        sys.exit(1)

    if t7_status[0] == "done":
        log("T7 already done! Proceeding to create convergence tasks.")
    elif t7_status[0] == "running":
        log("T7 is running, waiting for completion...")
        if not wait_for_task(T7_ID, timeout=7200, poll_interval=30):
            log("ERROR: Timeout waiting for T7. Exiting.")
            sys.exit(1)
    elif t7_status[0] in ("todo", "ready"):
        log(f"T7 is {t7_status[0]}, waiting for upstream tasks to complete...")
        if not wait_for_task(T7_ID, timeout=7200, poll_interval=30):
            log("ERROR: Timeout waiting for T7. Exiting.")
            sys.exit(1)
    else:
        log(f"WARNING: T7 status is '{t7_status[0]}'. Checking if convergence tasks already exist...")

    # Check if convergence tasks already exist for today
    conn = sqlite3.connect(KANBAN_DB)
    existing = conn.execute(
        "SELECT id, title, status FROM tasks WHERE title LIKE ? AND created_at > ?",
        (f"%converge-{TODAY}%", int(time.time()) - 86400)
    ).fetchall()
    conn.close()

    if existing:
        log(f"Convergence tasks already exist for today ({len(existing)} found). Skipping creation.")
        for tid, title, status in existing:
            log(f"  {status:8s} | {tid[:20]:20s} | {title[:60]}")
        log("Pipeline orchestrator completed (tasks already exist).")
        return

    # Phase 1: Create T8 — Price Check (no parent)
    log(f"\nPhase 1: Creating T8 — 逐票价格校验")
    t8 = kanban_create(
        "T8: 逐票价格校验",
        "researcher",
        build_t8_body(),
        max_runtime=600
    )
    if not t8:
        log("FATAL: Failed to create T8. Exiting.")
        sys.exit(1)

    # Wait a moment for the DB to update
    time.sleep(5)

    # Phase 2: Create T9-T12 — 四专家并行 (parent=T8)
    log(f"\nPhase 2: Creating T9-T12 — 四专家并行 (depend on T8)")

    t9 = kanban_create(
        "T9: 财经专家专项加减分",
        "analyst",
        build_t9_body(),
        parents=[t8],
        max_runtime=3600
    )
    t10 = kanban_create(
        "T10: 科技专家专项加减分",
        "analyst",
        build_t10_body(),
        parents=[t8],
        max_runtime=3600
    )
    t11 = kanban_create(
        "T11: 期货专家专项加减分",
        "analyst",
        build_t11_body(),
        parents=[t8],
        max_runtime=3600
    )
    t12 = kanban_create(
        "T12: 政治专家专项加减分",
        "analyst",
        build_t12_body(),
        parents=[t8],
        max_runtime=3600
    )

    # Collect expert task IDs (only non-None ones)
    expert_ids = [t for t in [t9, t10, t11, t12] if t is not None]
    if len(expert_ids) < 3:
        log(f"WARNING: Only {len(expert_ids)} expert tasks created successfully. T13 needs at least 3.")

    # Wait a moment for DB consistency
    time.sleep(3)

    # Phase 3: Create T13 — 主控最终裁决 (parents=T9-T12)
    log(f"\nPhase 3: Creating T13 — 主控最终裁决")
    t13 = kanban_create(
        "T13: 主控最终裁决",
        "analyst",
        build_t13_body(),
        parents=expert_ids,
        max_runtime=3600
    )
    if not t13:
        log("FATAL: Failed to create T13. Exiting.")
        sys.exit(1)

    time.sleep(3)

    # Phase 4: Create T14 — 收敛报告生成 (parent=T13)
    log(f"\nPhase 4: Creating T14 — 收敛报告生成")
    t14 = kanban_create(
        "T14: 收敛报告生成",
        "writer",
        build_t14_body(),
        parents=[t13],
        max_runtime=300
    )

    # Summary
    log(f"\n{'='*60}")
    log(f"Pipeline creation complete!")
    log(f"Task Graph:")
    log(f"  T8 ({t8}) → researcher (price check)")
    log(f"  ├─ T9 ({t9}) → analyst (finance)")
    log(f"  ├─ T10 ({t10}) → analyst (tech)")
    log(f"  ├─ T11 ({t11}) → analyst (futures)")
    log(f"  ├─ T12 ({t12}) → analyst (politics)")
    log(f"  └─ T13 ({t13}) → analyst (final convergence, depends on T9-T12)")
    log(f"      └─ T14 ({t14}) → writer (report, depends on T13)")
    log(f"{'='*60}")
    log(f"Pipeline orchestrator completed successfully at {datetime.now(TZ_CST).isoformat()}.")


if __name__ == "__main__":
    main()
