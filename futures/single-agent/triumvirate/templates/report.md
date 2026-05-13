# Triumvirate 扫描报告

**时间**: {{datetime}}
**扫描周期**: {{period}}
**Magic**: 234004

---

## 数据概况

- **数据源**: {{data_source}}
- **品种扫描**: 14/14 全品种
- **通过 Trade Gate 候选**: {{candidates_count}} 个
- **共识会议**: {{consensus_count}} 场

---

## 候选人分析

{% for candidate in candidates %}
### {{ candidate.symbol }} {{ candidate.direction }}

| 项目 | Analyst | RiskManager | President |
|------|---------|-------------|-----------|
| 评分/结论 | {{ candidate.round1.analyst.score }} | {{ candidate.round1.risk_manager.verdict }} | {{ candidate.round1.president.verdict }} |
| 第二轮 | {{ candidate.round2.analyst }} | {{ candidate.round2.risk_manager }} | {{ candidate.round2.president }} |
| 最终投票 | {{ candidate.final_vote }} |

**结构概要**: {{ candidate.structure_summary }}

**反对理由**（如果有）:
{% if candidate.objections %}
{% for o in candidate.objections %}
- [{{ o.role }}] {{ o.reason }}
{% endfor %}
{% else %}
无反对，全票通过 ✅
{% endif %}

---

{% endfor %}

---

## 执行结果

{% if executed_trades %}
| Ticket | 品种 | 方向 | 手数 | 入场价 | SL | TP | 状态 |
|--------|------|------|------|--------|----|----|------|
{% for t in executed_trades %}
| {{ t.ticket }} | {{ t.symbol }} | {{ t.direction }} | {{ t.volume }} | {{ t.entry }} | {{ t.sl }} | {{ t.tp }} | {{ t.status }} |
{% endfor %}
{% else %}
**无新交易** — 所有候选人未获全票通过。
{% endif %}

---

## 现有持仓管理

{% for pos in positions %}
| Ticket | 品种 | 方向 | 手数 | 入场价 | 浮动盈亏 | 操作 |
|--------|------|------|------|--------|---------|------|
| {{ pos.ticket }} | {{ pos.symbol }} | {{ pos.direction }} | {{ pos.volume }} | {{ pos.entry }} | {{ pos.pnl }} | {{ pos.action }} |

{% endfor %}

---

## Trade Gate 拦截记录（观察清单）

| 品种 | 拦截原因 | 形态描述 |
|------|---------|---------|
{% for blocked in blocked_list %}
| {{ blocked.symbol }} | {{ blocked.reason }} | {{ blocked.notes }} |
{% endfor %}

---

**总结**: 本次扫描 {{ executed_count }} 笔交易执行，{{ blocked_count }} 笔被拦截，净持仓 {{ net_positions }} 笔。
