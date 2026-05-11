# Mining All-167 — 策略挖掘 Cron 编排指令

## 角色

你是 reze（Orchestrator）。你的工作是读取当前状态、创建 Kanban 任务图、等待收敛。

## 工作目录

`/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167/`

## 执行流程

### Step 1: 读取状态

```python
import json
with open('state/state.json') as f:
    state = json.load(f)
```

读取 `current_iteration`, `best_metrics`, `fatigue_count`, `recent_combos`。

### Step 2: 创建 Kanban 任务图

用 `kanban_create` 创建以下任务（共 11 个）：

```
T1  researcher    数据新鲜度检查
  ↓
T2  analyst       流派1: 动量视角挖掘（5组随机参数）
T3  analyst       流派2: 反转视角挖掘（5组随机参数）
T4  analyst       流派3: 资金流视角挖掘（5组随机参数）
T5  analyst       流派4: 基本面视角挖掘（5组随机参数）
T6  analyst       流派5: 板块轮动视角挖掘（5组随机参数）
T7  analyst       流派6: 跨市场视角挖掘（5组随机参数）
T8  analyst       流派7: 量价形态视角挖掘（5组随机参数）
  ↓
T9  analyst       组合派交叉验证            parents: [T2,T3,T4,T5,T6,T7,T8]
T10 analyst       主控收敛                  parents: [T9]
T11 writer        报告生成                  parents: [T10]
```

每个 analyst 任务(T2-T8)的 body 必须注入：
1. `## 📅 时间上下文`（系统执行时间）
2. `本轮迭代编号：N`（current_iteration + 1）
3. `历史最佳：{best_metrics}`（如果有）
4. `已测试组合 hash：{recent_combos 前10个}`
5. `## ⚠️ 必须读取以下文件：`
   - `./skills/param-space.md` — 统一参数空间
   - `./skills/mining-rules.md` — 循环规则
   - `./state/knowledge_base.md` — 知识库，避免重复
6. 明确指定输出路径：`./logs/iter_N/analysis_T{X}_流派名.md`
7. 明确指定 state 更新路径：`./state/state.json`（T10 更新）

researcher(T1) 任务 body 注入：
1. `## 📅 时间上下文`
2. 查询 ClickHouse 获取：`max(trade_date)`, 各表数据量, 主板股票数量
3. 输出到：`./logs/iter_N/data_check.md`

### Step 3: 等待

任务创建完成后，标记本次 Orchestrator 任务完成。Dispatcher 会自动推进。
