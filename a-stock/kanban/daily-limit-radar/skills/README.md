# DLR 策略技能目录

## 通用角色灵魂文件（4 个）

从 `a-stock-shortline` 策略复制，定义跨策略通用行为：

| 文件 | Profile | 用途 |
|------|---------|------|
| `researcher-soul.md` | researcher | 纯数据查询，不做分析 |
| `analyst-soul.md` | analyst | 评分协议、风险校准 |
| `writer-soul.md` | writer | 格式优先，不修改结论 |
| `reze-soul.md` | analyst (主控) | 框架定义、专家收敛、最终裁决 |

## DLR 专属业务规则（2 个）

| 文件 | 用途 | 挂载时机 |
|------|------|---------|
| `scoring-engine.md` | 10 因子打分体系 + 三层收敛阈值 | T6 主控初筛、T13 主控裁决 |
| `risk-rules.md` | 风险过滤规则（硬淘汰 + 扣分） | T5 财经扫描、T13 主控裁决 |

## 挂载方式

在 `kanban_create` body 中引用：

```markdown
你的核心工作原则请参考：./skills/researcher-soul.md。
(+skills/scoring-engine.md)
(+skills/risk-rules.md)
```

系统自动将 `./skills/` 下对应文件注入 Worker 上下文。
