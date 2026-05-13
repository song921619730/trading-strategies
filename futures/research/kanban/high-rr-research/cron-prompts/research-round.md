# High-RR Research Round — 低胜率高盈亏比策略挖掘

> **仅研究模式，不注入交易系统。** 等积累足够数据后再开启自动注入。
> 所有输出必须使用中文。

## 执行步骤

### Step 1: 运行研究引擎
把以下脚本写到临时文件 `/mnt/c/Users/gj/Desktop/hrr_run.py`：
```python
import sys, os
os.chdir('F:/AIcoding_space/Hermes/strategies/futures/research/kanban/high-rr-research/scripts')
sys.path.insert(0, '.')
import orchestrator
orchestrator.main()
```

### Step 2: 执行
```
/mnt/c/Users/gj/AppData/Local/Programs/Python/Python312/python.exe C:/Users/gj/Desktop/hrr_run.py
```
预计执行时间 3-5 分钟（14品种 × 每个品种采样若干参数）

### Step 3: 检查结果
```bash
cat F:/AIcoding_space/Hermes/strategies/futures/research/kanban/high-rr-research/state/research_state.json | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'轮次: {d[\"current_round\"]}, 发现: {len(d[\"best_findings\"])}')"
```

### Step 4: 报告
列出本轮新发现中 Sharpe > 1.0 且 PF > 1.2 且 n > 30 的策略，按 Sharpe 排序。
格式：
```
品种 | 形态 | 方向 | n | WR | Sharpe | PF | DD%
```
不需要额外分析，纯数据。
