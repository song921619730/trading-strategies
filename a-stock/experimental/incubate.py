#!/usr/bin/env python3
"""
策略孵化脚本: proposal.md → experimental/shadow strategy
用法: python incubate.py <experiment_dir> <strategy_name>
"""
import sys
import json
import os
import shutil
from pathlib import Path
from datetime import datetime

# 路径配置
STRATEGIES_FUTURES = Path("/mnt/f/AIcoding_space/Hermes/strategies/futures")
STRATEGIES_A_STOCK = Path("/mnt/f/AIcoding_space/Hermes/strategies/a-stock")

def incubate(experiment_dir: str, strategy_name: str, market: str = "futures"):
    exp_path = Path(experiment_dir)
    if not exp_path.exists():
        print(f"❌ Experiment not found: {exp_path}")
        return False
    
    # 验证有 proposal.md 和 report.md
    proposal = exp_path / "proposal.md"
    report = exp_path / "report.md"
    if not proposal.exists():
        print("❌ No proposal.md found")
        return False
    
    base = STRATEGIES_FUTURES if market == "futures" else STRATEGIES_A_STOCK
    exp_base = base / "experimental"
    strategy_dir = exp_base / strategy_name
    
    if strategy_dir.exists():
        print(f"⚠️  Strategy already exists: {strategy_dir}")
        return False
    
    print(f"🔬 孵化实验策略: {strategy_name}")
    print(f"   市场: {market}")
    print(f"   来源: {exp_path.name}")
    
    # 创建目录
    for d in ["config", "scripts", "logs/scans", "logs/shadow"]:
        (strategy_dir / d).mkdir(parents=True, exist_ok=True)
    
    # 复制实验文件
    for f in [proposal, report]:
        if f.exists():
            shutil.copy2(f, strategy_dir / "config")
            print(f"  ✅ Copied {f.name}")
    
    # 复制通用脚本 (symlink)
    common_scripts = base / "single-agent/pure-ai-cio/scripts"
    if common_scripts.exists():
        for script in ["pre_analyze.py"]:
            src = common_scripts / script
            if src.exists():
                (strategy_dir / "scripts" / script).symlink_to(src)
                print(f"  ✅ Symlinked {script}")
    
    # 创建 SKILL.md (策略规则)
    proposal_text = proposal.read_text(encoding="utf-8")
    skill_md = f"""# 🔬 Experimental Strategy: {strategy_name}

**孵化时间**: {datetime.now().strftime("%Y-%m-%d")}
**来源实验**: `{exp_path.name}`
**模式**: 影子模式 (Shadow Mode — 仅记录信号，不实际交易)
**状态**: 孵化中

---

## 策略规则

> 以下内容从实验 proposal.md 中提取，作为 AI 分析的规则。

{proposal_text}

---

## 影子模式规则

1. AI 必须按上述规则分析盘面
2. **禁止执行任何实际交易操作**（不调用 execute_trade.py）
3. 必须在日志中记录：如果正式模式会做什么（品种、方向、SL、TP、理由）
4. 信号记录到 `logs/shadow/` 目录下

## 表现评估

- 模拟信号 ≥ 20 笔后自动评估
- 达标后可申请升级为正式策略 (kanban/ 或 single-agent/)
- 当前状态: `incubating`
"""
    (strategy_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")
    print("  ✅ Created SKILL.md")
    
    # 创建状态追踪
    status = {
        "name": strategy_name,
        "market": market,
        "status": "incubating",
        "mode": "shadow",
        "created_at": datetime.now().strftime("%Y-%m-%d"),
        "source_experiment": exp_path.name,
        "signals": [],
        "stats": {
            "total_signals": 0,
            "win_count": 0,
            "loss_count": 0,
            "win_rate": None,
            "avg_rr": None,
            "profit_factor": None,
            "max_drawdown_pct": None,
            "equity_curve": []
        },
        "upgrade_threshold": {
            "min_signals": 20,
            "min_win_rate": 0.50,
            "min_profit_factor": 1.2
        },
        "cron_job_id": None,
        "promoted_to": None,
        "notes": "Shadow mode — recording signals only, no actual trades"
    }
    with open(strategy_dir / "status.json", "w") as f:
        json.dump(status, f, indent=2, ensure_ascii=False)
    print("  ✅ Created status.json")
    
    # 创建影子模式扫描 prompt
    cron_prompt = f"""# 影子模式扫描 Prompt ({strategy_name})

⚠️ **这是影子模式 (Shadow Mode) — 禁止执行任何实际交易！**

## 你的任务
1. 执行 pre_analyze.py 获取实时市场数据
2. 按上述策略规则分析当前市场
3. **记录如果你在实际交易模式下会做什么操作**
4. **不要调用 execute_trade.py**，只输出分析报告

## 影子信号记录格式
在报告末尾增加此区块：

### 🔬 影子信号 (Shadow Signals)
| 品种 | 方向 | 建议入场 | SL | TP | 盈亏比 | 信心度 | 理由 |
|------|------|---------|----|----|--------|--------|------|

## 报告与日志
- 将完整报告写入: `logs/scans/[YYYY-MM-DD]/[HHMM].md`
- 将影子信号追加到: `logs/shadow/signals.jsonl` (每行一个 JSON)
- 即使"无信号"也必须写入日志

## 策略规则
（见 SKILL.md）
"""
    (strategy_dir / "config/cron_prompt.md").write_text(cron_prompt, encoding="utf-8")
    print("  ✅ Created cron_prompt.md")
    
    print(f"\n🎉 策略孵化完成: {strategy_dir}")
    print(f"📋 下一步: 等待足够信号后，告诉我升级为正式策略")
    return True

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python incubate.py <experiment_dir> <strategy_name> [market]")
        print("  market: futures (默认) 或 a-stock")
        sys.exit(1)
    
    exp_dir = sys.argv[1]
    name = sys.argv[2]
    market = sys.argv[3] if len(sys.argv) > 3 else "futures"
    
    success = incubate(exp_dir, name, market)
    sys.exit(0 if success else 1)
