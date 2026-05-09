# 🔬 研究 → 实验 → 生产 流水线

## 完整流程

```
研究 Brief (每 2h 自动生成)
    ↓
AI 研究实验 (自主假设 + 数据验证)
    ↓
报告产出 (report.md + proposal.md)
    ↓
✅ 验证通过? → 自动调用孵化脚本
    ↓
experimental/ 影子模式策略
    ↓
AI 每 2h 影子扫描 (记录信号，不交易)
    ↓
≥20 笔信号后评估表现
    ↓
胜率>50% 且 PF>1.2 → 提示升级到 kanban/ 或 single-agent/
```

## 关键概念

### 影子模式 (Shadow Mode)
- AI 按策略规则分析盘面
- **不执行任何实际交易**
- 记录"如果交易会怎么做"
- 信号存入 `logs/shadow/signals.jsonl`

### 孵化 (Incubation)
- 实验验证通过 → 自动生成 experimental 策略
- 包含完整 SKILL.md、状态追踪、扫描 prompt
- 自动创建 cron job 进行影子扫描

### 升级 (Promotion)
- 影子表现达标 → 提示用户
- 用户决定升级到 kanban/ 或 single-agent/
- 用户要求后设置正式 cron job

## 文件结构

```
strategies/futures/
├── single-agent/          # 已验证的成熟策略
├── kanban/                # 多智能体策略
└── experimental/          # 影子模式实验策略
    └── <策略名>/
        ├── SKILL.md       # 策略规则 (从 proposal 生成)
        ├── config/
        │   ├── proposal.md
        │   ├── report.md
        │   └── cron_prompt.md
        ├── scripts/       # symlink 到通用脚本
        ├── logs/
        │   ├── scans/     # 扫描报告
        │   └── shadow/    # 影子信号
        └── status.json    # 表现追踪
```

## 自动化程度

| 环节 | 自动化 | 人工介入 |
|------|--------|----------|
| 生成 Brief | ✅ 自动 | 无 |
| 研究实验 | ✅ 自动 | 无 |
| 验证通过 | ✅ 自动 | 无 |
| 孵化策略 | ✅ 自动 | 无 |
| 影子扫描 | ✅ 自动 | 无 |
| 表现评估 | ✅ 自动 | 无 |
| **升级决策** | ❌ 提示 | **用户决定** |
| **设置 cron** | ❌ 提示 | **用户决定** |

