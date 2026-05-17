#!/usr/bin/env python3
"""全流程测试: 扫描 → 保存 → 注入"""
import sys, os, json
sys.path.insert(0, '/mnt/f/AIcoding_space/Hermes/strategies/futures/scripts')
from discovery_engine import run_discovery

DATA = '/mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/scalping-m1/data'
STATE = '/mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/scalping-m1/state'

print("=" * 60)
print("STEP 1: 全指标扫描发现")
print("=" * 60)
result = run_discovery(
    data_dir=DATA,
    timeframe='H1',
    symbols=['XAUUSD', 'EURUSD'],
    dry_run=False,
    top_n=10,
)

print(f"\n状态: {result['status']}")
print(f"总发现: {result['total_findings']}")
print(f"耗时: {result['duration_s']}s")
print(f"best_known: {len(result.get('best_known', {}))} 条")

print("\n" + "=" * 60)
print("STEP 2: 保存到 state/discovery_result.json")
print("=" * 60)
state = {
    'status': result['status'],
    'current_round': 'auto_discovery',
    'last_run': __import__('datetime').datetime.utcnow().isoformat(),
    'best_known': result.get('best_known', {}),
    'hypotheses': [], 'warnings': [],
    'findings_summary': {
        'total': result['total_findings'],
        'duration_s': result['duration_s'],
        'top': [{'condition': r['condition'], 'win_rate': r['win_rate'],
                 'n': r['n'], 'sharpe': r['sharpe'], 'avg_return': r['avg_return']}
                for r in result['top_findings'][:10]],
    },
}
os.makedirs(STATE, exist_ok=True)
p = os.path.join(STATE, 'discovery_result.json')
with open(p, 'w') as f:
    json.dump(state, f, indent=2, ensure_ascii=False)
print(f"已保存到 {p}")

print("\n" + "=" * 60)
print("STEP 3: 注入到 scalping_strategies.json")
print("=" * 60)
ret = os.system(f'cd {os.path.dirname(STATE)} && python3 scripts/inject_discoveries.py 2>&1')
print(f"返回码: {ret}")

print("\n" + "=" * 60)
print("STEP 4: 验证配置")
print("=" * 60)
cfg_path = '/mnt/f/AIcoding_space/Hermes/strategies/futures/single-agent/scalping/config/scalping_strategies.json'
with open(cfg_path) as f:
    cfg = json.load(f)
print(f"总策略数: {len(cfg['signals'])}")
print(f"最后注入: {cfg.get('_last_auto_inject', 'N/A')}")
print(f"注入计数: {cfg.get('_auto_inject_count', 0)}")
print("\n✅ 全流程测试完成")
