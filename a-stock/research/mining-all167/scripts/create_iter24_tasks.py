#!/usr/bin/env python3
"""Create Iter24 Kanban task graph T1-T8"""
import json, subprocess, os, sys

ITER = 24
SYSTEM_TIME = "2026-05-13 17:40"
STRATEGY_DIR = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167"
LOGS_DIR = "%s/logs/iter_%d" % (STRATEGY_DIR, ITER)

os.makedirs(LOGS_DIR, exist_ok=True)

with open("%s/state/state.json" % STRATEGY_DIR) as f:
    state = json.load(f)

best = state["best_metrics"]
recent = state["recent_combos"][:10]
fatigue = state["fatigue_count"]

def kanban_create(title, assignee, body, parents=None, max_runtime=3600):
    cmd = ["hermes", "kanban", "create", title, "--assignee", assignee, "--body", body, "--json"]
    if parents:
        for p in parents:
            cmd.extend(["--parent", p])
    cmd.extend(["--max-runtime", str(max_runtime)])
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("ERROR creating %s: %s" % (title, result.stderr))
        return None
    return json.loads(result.stdout)["id"]

# Build T1 body
t1_lines = []
t1_lines.append("## 时间上下文（强制遵守）")
t1_lines.append("- 系统执行时间：2026-05-13 17:40 UTC+8")
t1_lines.append("- 本轮迭代编号：24")
t1_lines.append("- 数据基准日期：先确认最新trade_date")
t1_lines.append("- 历史最佳：WR=%.2f%%, R5=%.2f%%, Sharpe=%.2f" % (best['win_rate_5d'], best['ret_5d'], best['sharpe_5d']))
t1_lines.append("- fatigue_count: %d（上轮破WR+P10纪录后重置为0）" % fatigue)
t1_lines.append("")
t1_lines.append("### 职责")
t1_lines.append("1. 查询最新 trade_date：SELECT max(trade_date) FROM tushare.tushare_stock_daily FINAL")
t1_lines.append("2. 检查各核心表最新数据日期：stock_daily, moneyflow, fina_indicator, daily_basic等")
t1_lines.append("3. 确认前后交易日（从 trade_cal 查询 cal_date WHERE is_open=1）")
t1_lines.append("4. 输出到绝对路径：%s/analysis_T1_数据检查.md" % LOGS_DIR)
t1_lines.append("5. 所有日期使用 YYYY-MM-DD 格式，禁止推测词")
t1_lines.append("")
t1_lines.append("### 数据查询工具")
t1_lines.append("- 使用 query_sql MCP 工具连接 ClickHouse")
t1_lines.append("- 所有表必须加 FINAL")
t1_lines.append("- 日期格式 YYYYMMDD")
t1_lines.append("- 主板过滤条件必须包含")
t1_lines.append("")
t1_lines.append("### 输出格式")
t1_lines.append("文件 %s/analysis_T1_数据检查.md 必须包含：" % LOGS_DIR)
t1_lines.append("- 数据基准日期（来自 stock_daily 最新 trade_date）")
t1_lines.append("- 前一交易日、后一交易日（来自 trade_cal）")
t1_lines.append("- 各表数据日期检查表")
t1_lines.append("- 任何数据延迟或异常")

t1_body = "\n".join(t1_lines)

# Build time context prefix for T2-T8
time_prefix_lines = []
time_prefix_lines.append("## 时间上下文（强制遵守）")
time_prefix_lines.append("- 系统执行时间：2026-05-13 17:40 UTC+8")
time_prefix_lines.append("- 本轮迭代编号：24")
time_prefix_lines.append("- 历史最佳：WR=%.2f%%, R5=%.2f%%, Sharpe=%.2f" % (best['win_rate_5d'], best['ret_5d'], best['sharpe_5d']))
time_prefix_lines.append("- fatigue_count: %d（上轮破WR+P10纪录后重置）" % fatigue)
time_prefix_lines.append("- 最新发现参考 ./state/knowledge_base.md")
time_prefix = "\n".join(time_prefix_lines)

recent_str = "\n".join(["  - %s" % c[:100] for c in recent])

schools = [
    (2, "动量趋势", "从动量角度切入，关注持续强势/放量突破/趋势加速"),
    (3, "反转低吸", "从超跌反转角度切入，关注恐慌暴跌/散户割肉/探底回升"),
    (4, "资金主力", "从资金流角度切入，关注超大单/主力净流向/资金行为模式"),
    (5, "基本面估值", "从基本面/估值角度切入，关注PE/PB/ROE/高股息/业绩增长"),
    (6, "板块轮动", "从板块联动角度切入，关注概念热点/行业轮动/切换信号"),
    (7, "跨市场联动", "从跨市场联动角度切入，关注VIX/SPX/HSI/北向/利率联动"),
    (8, "量价形态", "从K线形态/量价关系角度切入，关注特定形态模式"),
]

task_ids = {}

# Step 1: Create T1
print("Creating T1: 数据新鲜度检查...")
t1_id = kanban_create("Iter24 T1: 数据新鲜度检查", "researcher", t1_body, max_runtime=600)
if not t1_id:
    print("FATAL: Could not create T1")
    sys.exit(1)
task_ids["T1"] = t1_id
print("T1 id=%s" % t1_id)

# Step 2: Create T2-T8
for num, name, desc in schools:
    lines = []
    lines.append(time_prefix)
    lines.append("")
    lines.append("### 角色：%s流派分析师" % name)
    lines.append(desc)
    lines.append("")
    lines.append("### 你的核心工作原则")
    lines.append("先读取 T1 数据检查结果（位于 %s/analysis_T1_数据检查.md）确认数据基准日期。" % LOGS_DIR)
    lines.append("参考 ./skills/param-space.md 和 ./skills/mining-rules.md 获取完整规则。")
    lines.append("参考 ./state/knowledge_base.md 了解已发现的有效策略，避免重复。")
    lines.append("")
    lines.append("### 参数采样规则")
    lines.append("1. 从 ./skills/param-space.md 的统一参数空间中随机选择 3-8 个维度")
    lines.append("2. 每个维度随机选一个值，生成 5 组不同的参数组合")
    lines.append("3. 与 recent_combos 对比去重，跳过最近 50 轮已测试组合")
    lines.append("")
    lines.append("最近的 recent_combos 前10个（避免重复）：")
    lines.append(recent_str)
    lines.append("")
    lines.append("### 查询执行")
    lines.append("- 使用 query_sql MCP 工具执行 ClickHouse SQL")
    lines.append("- 所有查询加 FINAL")
    lines.append("- 日期格式 YYYYMMDD")
    lines.append("- 主板过滤：ts_code NOT LIKE '30%%' AND NOT LIKE '688%%' AND NOT LIKE '920%%' AND NOT LIKE '%%ST%%'")
    lines.append("")
    lines.append("### 已知数据质量修复（2026-05-11 确认）")
    lines.append("- net_mf 不存在 -> 改用 net_mf_amount")
    lines.append("- basic_eps_yoy 全空 -> 改用 tr_yoy 或 netprofit_yoy")
    lines.append("- cyq_chips 存在(206万条)，偶发404需重试")
    lines.append("- fina_indicator 仅118565条，用 end_date 对齐季度")
    lines.append("")
    lines.append("### 输出要求")
    lines.append("写入绝对路径：%s/analysis_T%d_%s.md" % (LOGS_DIR, num, name))
    lines.append("必须包含：")
    lines.append("- 5组参数组合的完整描述")
    lines.append("- 每组的关键SQL查询（可复现）")
    lines.append("- 每组回测结果：信号数、胜率(WR)、5D平均收益、10D收益、20D收益、夏普比率")
    lines.append("- 最佳发现的详细描述")
    lines.append("")
    lines.append("### 成功标准")
    lines.append("- WR >= 52%% AND 5D收益 >= 3%% AND 信号数 >= 200")
    lines.append("")
    lines.append("### 完成时")
    lines.append("用 kanban_complete 标记完成，summary 中包含最佳策略的参数组合、WR、R5、信号数")

    body = "\n".join(lines)
    
    print("Creating T%d: %s..." % (num, name))
    tid = kanban_create("Iter24 T%d: %s分析" % (num, name), "analyst", body, parents=[t1_id], max_runtime=10800)
    if tid:
        task_ids["T%d" % num] = tid
        print("T%d id=%s" % (num, tid))
    else:
        print("FATAL: Could not create T%d" % num)
        sys.exit(1)

print("\n=== Task Creation Summary ===")
for k, v in sorted(task_ids.items()):
    print("  %s: %s" % (k, v))

with open("%s/state/task_ids_iter%d.json" % (STRATEGY_DIR, ITER), "w") as f:
    json.dump(task_ids, f, ensure_ascii=False, indent=2)

print("\nTask IDs saved. Proceeding to poller creation...")
