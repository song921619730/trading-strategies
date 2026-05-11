#!/usr/bin/env python3
# ============================================================
# A 股 LowOpen Loop - 全自动调度器 (Orchestrator) v4
# ============================================================
# 设计原则：
# - 所有数据一次拉满（daily + daily_basic + moneyflow）
# - 所有已知参数全部纳入随机采样
# - 没有"层级锁定"，没有"疲劳层解锁"
# - 唯一限制：不重复测试相同参数组合
# ============================================================

import json, os, sys, random, subprocess
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(SCRIPT_DIR, "state", "lowopen_state.json")

# ============================================================
# 全量参数空间 (所有可用数据字段的过滤条件)
# 采样策略: 先随机选子集大小 (2~5 个过滤条件)，再随机取值
# ============================================================

PARAM_SPACE = {
    # ---- 市值 & 流动性 (daily_basic) ----
    "circ_mv_max": [30, 50, 80, 100, 150, 200, 300, 500],      # 流通市值上限(亿)
    "circ_mv_min": [None, 10, 20, 30, 50],                       # 流通市值下限(亿)
    "turnover_min": [0.01, 0.02, 0.03, 0.05, 0.08, 0.10],       # 换手率下限
    "turnover_max": [None, 0.15, 0.20, 0.30, 0.50],              # 换手率上限
    "volume_ratio_min": [None, 0.8, 1.0, 1.2, 1.5, 2.0],        # 量比下限

    # ---- 估值 (daily_basic) ----
    "pe_max": [None, 10, 20, 30, 50, 80, 100],
    "pe_min": [None, 0, 5, 10],
    "pb_max": [None, 1, 2, 3, 5, 10],

    # ---- 价格行为 (daily) ----
    "pct_chg_min": [3.0, 4.0, 5.0, 6.0, 8.0, 10.0],            # 当日涨幅下限(%)
    "pct_chg_max": [None, 8.0, 10.0, 12.0, 15.0, 20.0],
    "close_min": [None, 3, 5, 10, 20, 50],                       # 股价下限(元)
    "vol_min": [None, 5000000, 10000000, 50000000],              # 成交量下限

    # ---- 资金流 (moneyflow) ----
    "net_mf_min": [None, -100_000_000, -50_000_000, -10_000_000, 0, 10_000_000],
    "buy_lg_ratio_min": [None, 0.03, 0.05, 0.08, 0.10, 0.12],  # 大单买入比例下限
    "sell_lg_ratio_max": [None, 0.05, 0.08, 0.10, 0.12, 0.15, 0.20],
    "buy_elg_ratio_min": [None, 0.01, 0.02, 0.03, 0.05],
    "sell_elg_ratio_max": [None, 0.05, 0.08, 0.10, 0.15],
}

FIXED_LAYERS = ["daily", "daily_basic", "moneyflow"]

# ============================================================
# 状态管理器
# ============================================================

class StateManager:
    def __init__(self, path=STATE_PATH):
        self.path = path
        self.state = self.load()

    def load(self):
        if os.path.exists(self.path):
            with open(self.path, 'r') as f:
                s = json.load(f)
            s.setdefault('current_iteration', 0)
            s.setdefault('best_metrics', {"best_5d_return": 0.0})
            s.setdefault('history', [])
            s.setdefault('fatigue_count', 0)
            return s
        return {
            "topic": "Low Open High Go",
            "current_iteration": 0,
            "best_metrics": {"best_5d_return": 0.0, "win_rate_5d": 0.0, "sharpe_ratio": 0.0, "signal_count": 0},
            "history": [],
            "fatigue_count": 0
        }

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, 'w') as f:
            json.dump(self.state, f, indent=2, default=str)

    def update(self, metrics):
        self.state['current_iteration'] += 1
        iter_num = self.state['current_iteration']

        # 记录历史
        entry = {"iteration": iter_num, "time": datetime.now().isoformat(), **metrics}
        self.state['history'].append(entry)
        if len(self.state['history']) > 50:
            self.state['history'] = self.state['history'][-50:]

        # 疲劳检测：连续 N 次未破纪录
        new_ret = metrics.get('ret_5d', 0) or 0
        best_ret = self.state['best_metrics'].get('best_5d_return', 0) or 0

        if new_ret > best_ret:
            self.state['best_metrics'] = {
                'best_5d_return': new_ret,
                'win_rate_5d': metrics.get('win_5d', 0),
                'sharpe_ratio': metrics.get('sharpe_5d', 0),
                'signal_count': metrics.get('count', 0),
                'best_params': metrics.get('params', {})
            }
            self.state['fatigue_count'] = 0
            print(f"🎉 New Record! {new_ret:.2%} > {best_ret:.2%}. Fatigue Reset.")
        else:
            self.state['fatigue_count'] += 1
            print(f"⚠️ Fatigue: {self.state['fatigue_count']} (best={best_ret:.2%}, cur={new_ret:.2%})")

        self.save()

    def should_continue(self, max_fatigue=10):
        """超过最大疲劳阈值则建议归档"""
        return self.state['fatigue_count'] < max_fatigue

# ============================================================
# 假设生成器 (不重复采样)
# ============================================================

def sample_params(history):
    """随机从全量参数空间采样，避开历史已测组合"""
    param_keys = list(PARAM_SPACE.keys())
    max_attempts = 50

    for _ in range(max_attempts):
        # 随机选 3~6 个过滤条件
        n_filters = random.randint(3, 6)
        selected_keys = random.sample(param_keys, min(n_filters, len(param_keys)))

        params = {}
        for k in selected_keys:
            vals = PARAM_SPACE[k]
            # None 保持为 None，表示不限制该维度
            v = random.choice(vals)
            if v is not None:
                params[k] = v

        # 最少 2 个有效过滤条件
        if len(params) < 2:
            continue

        # 查重：检查是否和历史 combination 完全一致
        dup = False
        for h in history[-20:]:
            hp = h.get('params', {})
            if set(hp.keys()) == set(params.keys()) and all(hp[k] == params[k] for k in params):
                dup = True
                break
        if not dup:
            return params

    return params  # fallback

# ============================================================
# 主循环
# ============================================================

def main():
    print("=" * 60)
    print("🤖 Orchestrator v4: Load All Data, Explore All Params")
    print("=" * 60)
    os.chdir(SCRIPT_DIR)

    sm = StateManager()
    state = sm.state

    if not sm.should_continue():
        print("🛑 Max fatigue reached. Consider archiving this topic.")
        print("    State saved — run again after adding new data sources.")
        sys.exit(0)

    iter_num = state['current_iteration'] + 1
    iter_dir = f"iter_{iter_num:03d}"
    os.makedirs(f"logs/{iter_dir}", exist_ok=True)

    best = state['best_metrics'].get('best_5d_return', 0)
    print(f"📊 Iteration: {iter_num} | Fatigue: {state['fatigue_count']}")
    print(f"🏆 Best 5D Return: {best:.2%} (count={state['best_metrics'].get('signal_count',0)}, sharpe={state['best_metrics'].get('sharpe_ratio',0):.2f})")

    # 1. 生成假设
    params = sample_params(state.get('history', []))
    print(f"🧪 New Params ({len(params)} filters): {json.dumps(params)}")

    # 2. 写配置
    config = {
        "data_layers": FIXED_LAYERS,
        "variables": {k: [v] for k, v in params.items()},
        "holding_periods": [1, 5, 7, 8],
        "output_dir": "logs",
        "iteration_dir": iter_dir,
    }
    with open("grid_config.json", 'w') as f:
        json.dump(config, f, indent=2)

    # 3. 执行回测
    print("⚙️  Running Grid Engine...")
    engine_path = os.path.join(SCRIPT_DIR, "scripts", "grid_engine.py")
    result = subprocess.run(
        [sys.executable, engine_path, "grid_config.json"],
        capture_output=True, text=True, timeout=300
    )

    if result.returncode != 0:
        print(f"❌ Engine Failed. Stderr:\n{result.stderr[-500:]}")
        sm.update({"ret_5d": -0.1, "win_5d": 0, "sharpe_5d": 0, "count": 0, "params": params})
        sys.exit(1)

    print(result.stdout[-400:])

    # 4. 解析结果
    summary_path = f"logs/{iter_dir}/summary.json"
    if os.path.exists(summary_path):
        with open(summary_path, 'r') as f:
            summary = json.load(f)

        if summary.get('top_10'):
            best_row = summary['top_10'][0]
            metrics = {
                "ret_5d": best_row.get('avg_ret_5d', 0),
                "win_5d": best_row.get('win_rate_5d', 0),
                "sharpe_5d": best_row.get('sharpe_5d', 0),
                "count": best_row.get('signal_count_5d', 0),
                "params": params
            }
            ret = metrics['ret_5d']
            wr = metrics['win_5d']
            sh = metrics['sharpe_5d']
            ret_s = f"{ret:.2%}" if ret is not None else "N/A"
            wr_s = f"{wr:.1%}" if wr is not None else "N/A"
            sh_s = f"{sh:.2f}" if sh is not None else "N/A"
            print(f"📈 Result: Ret={ret_s} | WR={wr_s} | Sharpe={sh_s} | Count={metrics['count']}")
            sm.update(metrics)
        else:
            sm.update({"ret_5d": -0.05, "win_5d": 0, "sharpe_5d": 0, "count": 0, "params": params})
    else:
        print("❌ Summary not found.")
        sm.update({"ret_5d": -0.1, "win_5d": 0, "sharpe_5d": 0, "count": 0, "params": params})

    generate_report(state)

    print("🏁 Done.")

# ============================================================
# 报告生成器
# ============================================================

def generate_report(state):
    """根据 state 数据生成 final_report.md"""
    best = state.get('best_metrics', {})
    history = state.get('history', [])
    alpha = state.get('alpha_detected', {})
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # 计算最近几次有效迭代
    valid_iters = [h for h in history if h.get('count', 0) > 0 and h.get('ret_5d', -1) > 0]

    lines = []
    lines.append(f"# Low Open High Go (低开高走) — 研究报告")
    lines.append(f"")
    lines.append(f"**生成时间**: {now}")
    lines.append(f"**状态**: 第 {state.get('current_iteration', 0)} 次迭代 | 疲劳度 {state.get('fatigue_count', 0)}")
    lines.append(f"")
    lines.append(f"---")
    lines.append(f"")
    lines.append(f"## 🏆 当前最佳参数")
    lines.append(f"")
    if best.get('best_params'):
        lines.append(f"| 参数 | 值 |")
        lines.append(f"|------|-----|")
        for k, v in best['best_params'].items():
            lines.append(f"| {k} | {v} |")
    lines.append(f"")
    lines.append(f"## 📊 最佳回测绩效")
    lines.append(f"")
    lines.append(f"| 指标 | 值 |")
    lines.append(f"|------|-----|")
    lines.append(f"| 5日平均收益 | {best.get('best_5d_return', 0):.2%} |")
    lines.append(f"| 5日胜率 | {best.get('win_rate_5d', 0):.1%} |")
    lines.append(f"| Sharpe 比率 | {best.get('sharpe_ratio', 0):.2f} |")
    lines.append(f"| 信号数量 | {best.get('signal_count', 0)} |")
    lines.append(f"")
    if alpha:
        lines.append(f"## 🔬 Alpha 信号")
        lines.append(f"")
        lines.append(f"| 属性 | 值 |")
        lines.append(f"|------|-----|")
        for k, v in alpha.items():
            if not isinstance(v, list):
                lines.append(f"| {k} | {v} |")
    lines.append(f"")
    lines.append(f"## 📈 最近有效迭代")
    lines.append(f"")
    if valid_iters:
        lines.append(f"| # | 5D收益 | 胜率 | Sharpe | 信号数 |")
        lines.append(f"|---|--------|------|--------|--------|")
        for h in valid_iters[-8:]:
            i = h.get('iteration', h.get('iter_num', '?'))
            r = h.get('ret_5d', 0)
            w = h.get('win_5d', 0)
            s = h.get('sharpe_5d', 0)
            c = h.get('count', 0)
            lines.append(f"| {i} | {r:.2%} | {w:.1%} | {s:.2f} | {c} |")
    lines.append(f"")
    lines.append(f"## ⚙️ 迭代历史摘要")
    lines.append(f"")
    total_configs = sum(h.get('configs', 1) for h in history)
    lines.append(f"- 总迭代次数: {state.get('current_iteration', 0)}")
    lines.append(f"- 总参数组合评估: {total_configs}")
    lines.append(f"- 数据层探索: {', '.join(state.get('data_exploration', {}).get('tested_layers', []))}")
    lines.append(f"- 疲劳度: {state.get('fatigue_count', 0)} / {state.get('data_exploration', {}).get('fatigue_count', 0)}")
    if state.get('status'):
        lines.append(f"- 状态: {state['status']}")
    lines.append(f"")
    lines.append(f"---")
    lines.append(f"")
    lines.append(f"*由 A 股 LowOpen Orchestrator v4 自动生成*")

    os.makedirs("logs", exist_ok=True)
    with open("logs/final_report.md", 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print("📄 Report saved: logs/final_report.md")


if __name__ == '__main__':
    main()
