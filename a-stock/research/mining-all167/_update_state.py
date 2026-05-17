#!/usr/bin/env python3
"""Update state.json, knowledge_base.md, and convergence report for Iter26"""
import json
import os
from datetime import datetime

ROOT = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167"
STATE_PATH = f"{ROOT}/state/state.json"
KB_PATH = f"{ROOT}/state/knowledge_base.md"
CONV_PATH = f"{ROOT}/logs/iter_26/analysis_T10_收敛.md"
ITER = 26
NOW = "2026-05-13"
TODAY = "2026-05-13 UTC+8"

# ====== 1. Read current state ======
with open(STATE_PATH) as f:
    state = json.load(f)

print(f"current_iteration: {state['current_iteration']}")
print(f"fatigue_count: {state['fatigue_count']}")
print(f"best WR: {state['best_metrics']['win_rate_5d']}%")
print(f"best R5: {state['best_metrics']['ret_5d']}%")
print(f"best Sharpe: {state['best_metrics']['sharpe_5d']}")
print(f"best P10: 40.96% (T8-C1b)")

# ====== 2. Check if any Iter26 combo breaks global records ======
global_wr = 99.55    # CROSS-6, Iter25
global_r5 = 25.23    # CROSS-6, Iter25
global_sharpe = 20.227  # CROSS-6, Iter25
global_p10 = 40.96   # T8-C1b, Iter25

# Iter26 best values
iter26_best_wr = 84.22     # T3-C5 (双日温和恐慌+SPX+ELG)
iter26_best_r5 = 16.51     # T7-C3 (恐慌+振幅7%+三重资金流+微盘)
iter26_best_sharpe = 6.564 # T3-C5 Sharpe (or CROSS-14 Sharpe=6.97)
iter26_best_r5_cross10 = 12.12  # CROSS-10
iter26_best_p10 = -1.72    # CROSS-14

records_broken = []
if iter26_best_wr > global_wr:
    records_broken.append(f"WR: {iter26_best_wr}% > {global_wr}%")
if iter26_best_r5 > global_r5:
    records_broken.append(f"R5: {iter26_best_r5}% > {global_r5}%")
if iter26_best_sharpe > global_sharpe:
    records_broken.append(f"Sharpe: {iter26_best_sharpe} > {global_sharpe}")
if iter26_best_p10 > global_p10:
    records_broken.append(f"P10: {iter26_best_p10}% > {global_p10}%")

no_record_broken = len(records_broken) == 0
new_fatigue = state['fatigue_count'] + 1 if no_record_broken else 0

print(f"\nRecords broken: {records_broken if records_broken else 'None'}")
print(f"fatigue_count: {state['fatigue_count']} -> {new_fatigue}")

# ====== 3. Update state.json ======
state['current_iteration'] = ITER

if not no_record_broken:
    # Update best_metrics if any record is broken
    # (not happening this iteration)
    pass

state['fatigue_count'] = new_fatigue

# Build history entry
history_entry = {
    "iteration": ITER,
    "ret_5d": iter26_best_r5,
    "win_5d": iter26_best_wr,
    "signal_count": 586,  # T7-C3 signal count
    "sharpe_5d": iter26_best_sharpe,
    "analyst": "T10_主控收敛 (Iter26完整汇总)",
    "params": "各流派最佳汇总 (详见收敛报告)",
    "note": ""
}

# Build the note
note_parts = []

# PASS stats
# T2: 0/5, T3: 3/5, T4: 5/5, T5: 1/5, T6: 4/10 (two reports), T7: 5/5, T8: 0/8, T9: 9/14
total_pass = 0 + 3 + 5 + 1 + 4 + 5 + 0 + 9
total_combos = 5 + 5 + 5 + 5 + 10 + 5 + 8 + 14
pass_rate = round(total_pass / total_combos * 100, 1)

note_parts.append(f"📊 Iter26完整汇总 — 8个流派共测试{total_combos}组组合，{total_pass}组PASS({pass_rate}%)。")

# T7最佳
note_parts.append(f"🏆 T7流派全满贯(5/5): C3(R5=16.51%,WR=77.47%,Sharpe=7.20)为Iter26全场最佳! C2(双日-3%+CPX+R5=14.07%), C4(非恐慌模式N=1516,R5=9.64%)均为高质量.")

# T3
note_parts.append(f"🏆 T3流派3/5 PASS: C5双日温和-3%+SPX+ELG(R5=13.02%,WR=84.22%,R20=25.69%)创新Sharpe纪录6.564. Cap2双日恐慌+大单+N=415 PASS. C4跨T5高股息迁移PASS.")

# T4
note_parts.append(f"🏆 T4流派全满贯(5/5): C1恐慌+振幅7%+散户割肉+净流入(R5=6.43%,R10=15.45%), C3v2(N=4787,WR=71.97%), C4振幅7%高换手(R5=6.13%,R10=15.47%).")

# T6
note_parts.append(f"🏆 T6流派双报告: 报告1(C5极致恐慌反转:R5=6.93%,N=2392) + 报告2(C1双日恐慌SPX双涨:PASS, N=1062,WR=83.15%).")

# T9
note_parts.append(f"🏆 T9交叉9/14 PASS: CROSS-10(恐慌+振幅7%+VR1.3+大单+SPX R5=12.12%,N=784,Sharpe=5.20)最佳容量质量平衡. CROSS-14(恐慌+深价值 WR=82.35%,P10=-1.72%极致低回撤). CROSS-9(双日恐慌+资金流 N=2486,WR=72%).")

# New discoveries
note_parts.append(f"🆕 新因子发现: (1)振幅≥7%跨流派验证为通用强化因子(T4/T7/T9均有效), (2)双日温和恐慌-3%替代-5%获得2.6倍信号量, (3)散户割肉+净流入双确认=T4最强因子对, (4)深价值(PE≤15+dv≥3%)在恐慌场景中提供极致尾部风险保护(P10=-1.72%), (5)跨流派振幅因子叠加效应(宏观+资金+振幅=SPX+资金+7% R5从6.93%→12.12%).")

# No record broken
note_parts.append(f"❌ 未超越全局纪录(WR=99.55%, R5=25.23%, Sharpe=20.227). 全部记录仍由Iter25 CROSS-6保持.")

if no_record_broken:
    note_parts.append(f"fatigue_count: {state['fatigue_count']}→{new_fatigue}.")

history_entry["note"] = "\n".join(note_parts)

# Prepend to history (insert at position 2, after the Iter26 placeholder)
state['history'].insert(1, history_entry)

# Update recent_combos
new_combos = [
    "iter26_T7_C3: SPX+恐慌≥-5%+振幅≥7%+VR+散户割肉+大单+底20%+CM≤30亿 N=586,WR=77.47%,R5=16.51%,Sharpe=7.20,R10=24.30%,R20=30.26% 🏆Iter26全场最佳",
    "iter26_T3_C5: 双日温和恐慌(-3%)+SPX+ELG+底20%+VR1.2+CM≤50亿 N=602,WR=84.22%,R5=13.02%,Sharpe=6.564,R20=25.69% 🏆T3新Sharpe纪录",
    "iter26_CROSS-10: 恐慌-5%+振幅7%+VR1.3+底20%+CM≤30亿+大单+SPX N=784,WR=70.54%,R5=12.12%,Sharpe=5.20 🏆T9最佳容量质量平衡",
    "iter26_T4_C1: 恐慌-5%+振幅7%+散户割肉+净流入+底20%+CM≤100亿 N=771,WR=72.89%,R5=6.43%,R10=15.45% 🏆T4全满贯",
    "iter26_T7_C4: SPX+今涨≥3%+VR+散户割肉+大单+底30%+CM≤100亿 N=1516,WR=71.77%,R5=9.64%,Sharpe=5.04 🏆非恐慌模式最大容量",
    "iter26_T6_C1: 双日恐慌+SPX双涨+散户割肉+大单+微盘 N=1062,WR=83.15%,R5=3.72%,Sharpe=3.79 🏆T6板块轮动PASS",
    "iter26_CROSS-14: 恐慌+振幅7%+VR1.3+大单+PE≤15+dv≥3%+CM≤50亿 N=221,WR=82.35%,R5=9.32%,P10=-1.72% 🏆极致低回撤",
    "iter26_CROSS-9: 双日恐慌-3%+散户割肉+大单+底20%+CM≤100亿+VR+振幅≥6% N=2486,WR=72.00%,R5=6.00% 🏆最佳大容量版",
    "iter26_T5_C3: PE≤15+dv≥3%+底40%+VR+振幅5%+CM≤50亿 N=2725,WR=64.07%,R5=3.39%,Sharpe=2.81 🏆T5纯基本面容量版",
    "iter26_T4_C3v2: 恐慌+散户割肉+大单+VR+底20%+CM≤50亿 N=4787,WR=71.97%,R5=5.46% 🏆T4大容量版",
]
state['recent_combos'] = new_combos + state['recent_combos']
# Keep only 50
state['recent_combos'] = state['recent_combos'][:50]

with open(STATE_PATH, 'w') as f:
    json.dump(state, f, ensure_ascii=False, indent=2)
print(f"\n✅ state.json updated. fatigue_count: {state['fatigue_count']}")

# ====== 4. Write convergence report ======
conv = f"""# Iteration {ITER} — T10 主控收敛报告

> 生成时间: {NOW} {TODAY}
> 任务: 读取 T2-T9 所有流派输出 → 收敛分析

---

## 📊 总览

| 流派 | 测试组数 | PASS | NEAR-PASS | FAIL | PASS率 |
|:----|:-------:|:----:|:---------:|:----:|:-----:|
| T2 动量趋势 | 5 | 0 | 0 | 5 | 0% |
| T3 反转低吸 | 5 | 3 | 0 | 2 | 60% 🏆 |
| T4 资金主力 | 5 | 5 | 0 | 0 | 100% 🏆🏆 |
| T5 基本面估值 | 5 | 1 | 1 | 3 | 20% |
| T6 板块轮动 | 10 | 4 | 5 | 1 | 40% |
| T7 跨市场联动 | 5 | 5 | 0 | 0 | 100% 🏆🏆 |
| T8 量价形态 | 8 | 0 | 1 | 7 | 0% |
| T9 组合交叉 | 14 | 9 | 0 | 5 | 64.3% 🏆 |
| **合计** | **{total_combos}** | **{total_pass}** | **7** | **23** | **{pass_rate}%** |

---

## 🏆 本轮最佳策略及新发现

### 🥇 T7-C3: 恐慌+振幅7%+三重资金流+微盘 (全场最佳!)

**参数**: SPX前日涨>0% + pct≤-5% + 振幅≥7% + VR≥1.0 + sell_sm>buy_sm + buy_lg>sell_lg + 底20% + CM≤30亿

| 指标 | 值 | 超越? |
|:----:|:--:|:-----:|
| N | 586 | ✅ 适中 |
| WR-5D | 77.47% | ✅ 优秀 |
| **R5** | **16.51%** | 🏆 **全场最高(不含小N组合)** |
| R10 | 24.30% | 🏆 极强持续性 |
| R20 | 30.26% | 🏆 极强持续性 |
| Sharpe | 7.20 | 🏆 全场最高 |
| P10 | -10.38% | 可控 |

**对比历史**: T7-C3的R5=16.51% > Iter25 T4-V6(R5=11.47%)+44%，Sharpe=7.20全场最高。

---

### 🥇 T3-C5: 双日温和恐慌+SPX+ELG (T3新Sharpe纪录)

**参数**: SPX前日涨>0% + 双日连续跌≥-3% + 振幅≥7% + VR≥1.2 + buy_elg>sell_elg + 底20% + CM≤50亿

| 指标 | 值 |
|:----:|:--:|
| N | 602 |
| WR | 84.22% |
| R5 | 13.02% |
| R10 | 19.02% |
| R20 | 25.69% 🏆 |
| **Sharpe** | **6.564** 🏆 **T3流派历史新高** |

---

### 🥇 CROSS-10: 恐慌+振幅7%+VR1.3+大单+SPX (T9最佳容量质量平衡)

| 指标 | 值 |
|:----:|:--:|
| N | 784 |
| WR | 70.54% |
| **R5** | **12.12%** |
| R10 | 17.57% |
| R20 | 22.39% |
| Sharpe | 5.20 |

**最佳可执行策略**: 对比Iter25 CROSS-6(N=222), 容量+253%且R5仍有12.12%。

---

### 🥇 CROSS-14: 恐慌+深价值 (极致低回撤)

| 指标 | 值 |
|:----:|:--:|
| N | 221 |
| WR | **82.35%** |
| R5 | 9.32% |
| Sharpe | 6.97 |
| **P10** | **-1.72%** 🏆 **全场最低回撤** |

**逻辑创新**: 恐慌反转框架 + 深价值安全垫(PE≤15+dv≥3%) = 近乎零爆仓风险的抄底策略。

---

## 🆕 新因子及模式发现

### 1. 🆕 振幅≥7% = 通用强化因子 (跨流派验证成功)
- T4中: 恐慌+资金流+振幅7% R5=6.43%(N=771)
- T7中: 恐慌+SPX+资金流+振幅7% R5=16.51%(N=586)
- CROSS-10: 恐慌+VR1.3+大单+SPX+振幅7% R5=12.12%(N=784)
- **核心发现**: 振幅因子价值随宏观和资金条件叠加而放大

### 2. 🆕 双日温和恐慌-3% (替代-5%信号扩容)
- CROSS-2: 双日-3%+SPX+资金流 N=1,007, WR=65.44%, R5=8.81%
- CROSS-9: 双日-3%+资金流+振幅6% N=2,486, WR=72.00%, R5=6.00%
- **信号量**: 比-5%版+158%(CROSS-6 N=222 → CROSS-2 N=1,007)

### 3. 🆕 散户割肉+净流入双确认 = T4最强因子对
- T4-C1使用此因子对获得R5=6.43%(无SPX)
- CROSS-10添加SPX后R5=12.12%

### 4. 🆕 深价值(PE≤15+dv≥3%)恐慌反转保护
- CROSS-14: P10=-1.72% 全场最低尾部风险
- 深价值作为安全垫在恐慌抄底中提供极端保护

### 5. 🆕 非恐慌模式验证: SPX+涨≥3%+散户割肉+大单
- T7-C4: N=1,516, WR=71.77%, R5=9.64%
- 散户在上涨中卖出(解套盘)+大单买入=有效的非恐慌反转模式

---

## 📈 流派对比历史基准

| 流派 | 本轮最佳 | 指标 | 流派历史最佳 | 对比 |
|:----|:--------|:----:|:-----------:|:----:|
| T2 | 0/5 PASS | — | T2-C2 R5=22.11% | ❌ 全部FAIL |
| T3 | C5 R5=13.02% | WR=84.22% | T3-C2 WR=87.70% | 🟡 WR未超越, Sharpe创新高 |
| T4 | C1 R5=6.43% | N=771 | T4-C5-MIX R5=13.48% | ❌ R5低于历史最佳 |
| T5 | C3 R5=3.39% | N=2,725 | T5-C8 R5=10.29% | ❌ 纯基本面版, 容量取胜 |
| T6 | C1 R5=3.72% | N=1,062 | T6-C4 R5=6.96% | ❌ |
| T7 | C3 **R5=16.51%** | WR=77.47% | T7历史最佳 | 🏆 **T7流派R5新纪录!** |
| T8 | C7 R5=2.94% | N=1,091 | C1b R5=24.49% | ❌ |
| T9 | CROSS-10 R5=12.12% | N=784 | CROSS-6 R5=25.23% | ❌ 容量质量平衡是亮点 |

---

## ✅ 待涨/接盘判定

本轮无T5/T6/T2日线选股任务产出(纯回测挖掘迭代), 所有发现为回测信号策略, 不涉及当日选股判定。

---

## 📌 下轮建议

1. **T7-C3扩容**: CM 30亿→50亿→100亿分步测试(R5预计12-14%)
2. **CROSS-10参数精炼**: VR阈值1.0/1.2/1.5寻找最优平衡点
3. **振幅分层测试**: 5%/7%/10%在SPX+资金流框架下的边际收益
4. **CROSS-14扩容**: CM 50亿→100亿, PE≤15→PE≤20, 预期N>500
5. **双日恐慌阈值优化**: -2%/-3%/-4%/-5%四种阈值容量-质量曲线
6. **CROSS-9+SPX**: 在CROSS-9基础上添加SPX过滤, 预期N~1,500, WR~76%
7. **T7振幅≥7%→T8迁移**: T8-C7添加振幅≥7%预期R5>5%

---

## 📦 全局纪录状态

| 指标 | 当前纪录 | 保持者 | 发现轮次 | 本轮最佳 | 超越? |
|:----:|:--------:|:------:|:--------:|:--------:|:----:|
| WR | 99.55% | CROSS-6 | Iter25 | 84.22% | ❌ |
| R5 | 25.23% | CROSS-6 | Iter25 | 16.51% | ❌ |
| Sharpe | 20.227 | CROSS-6 | Iter25 | 6.564 | ❌ |
| P10 | +40.96% | T8-C1b | Iter25 | -1.72% | ❌ |

**fatigue_count: {state['fatigue_count']} → {new_fatigue}** (未超越全局纪录+1)

---

*收敛报告完成时间: {NOW} {TODAY}*
"""

with open(CONV_PATH, 'w') as f:
    f.write(conv)
print(f"\n✅ Convergence report written to: {CONV_PATH}")

# ====== 5. Update knowledge_base.md ======
with open(KB_PATH, 'r') as f:
    kb = f.read()

# Append new findings
kb_addition = f"""

---

## {NOW} (iter {ITER}) — 🏆 T7流派全满贯 + T3新Sharpe纪录 + 振幅≥7%跨流派验证

### 🏆🏆 T7-C3: 恐慌+振幅7%+三重资金流+微盘 — T7流派R5新纪录!

**参数**: SPX前日涨>0% + pct≤-5% + 振幅≥7% + VR≥1.0 + sell_sm>buy_sm + buy_lg>sell_lg + 底20% + CM≤30亿

| 指标 | 值 |
|:----:|:--:|
| N | 586 |
| WR | 77.47% |
| **R5** | **16.51%** 🏆 **T7流派新R5纪录!** |
| R10 | 24.30% |
| R20 | 30.26% |
| Sharpe | 7.20 |

超越Iter25 T4-V6(R5=11.47%) +44%! 振幅≥7%在恐慌+资金流+SPX场景中有极致增益。

### 🏆 T7-C4: 非恐慌模式突破

**参数**: SPX+今涨≥3%+VR+散户割肉+大单+底30%+CM≤100亿
**指标**: N=1,516, WR=71.77%, R5=9.64%, Sharpe=5.04
**核心价值**: 唯一\"涨时买入\"模式在大容量(N=1516)下验证成功。

### 🏆 T7-C2: CROSS-6温和版(双日-3%)

**参数**: SPX+双日跌≥-3%+散户割肉+大单+底20%+CM≤50亿
**指标**: N=572, WR=71.15%, R5=14.07%, Sharpe=5.49
**信号量+158%**: 双日-3%替代-5%获得2.6倍信号量, WR仍保持71%。

### 🏆 T3-C5: 双日温和恐慌+SPX+ELG (T3流派Sharpe新纪录)

**参数**: SPX+双日-3%+振幅7%+VR1.2+ELG+底20%+CM≤50亿
**指标**: N=602, WR=84.22%, R5=13.02%, Sharpe=6.564 🏆, R20=25.69% 🏆
**核心创新**: 温和双日恐慌阈值(-3%)突破传统-5%, 信号量+45%。

### ✅ T4流派全满贯(5/5 PASS)

- **T4-C1**: 恐慌+振幅7%+散户割肉+净流入+底20%+CM≤100亿 (N=771, R5=6.43%, R10=15.45%)
- **T4-C3v2**: 恐慌+散户割肉+大单+VR+底20%+CM≤50亿 (N=4,787, WR=71.97%, R5=5.46%)
- **T4-C4**: 恐慌+高换手+散户割肉+净流入+振幅7%+底20%+CM≤50亿 (R10=15.47%)

### 🏆 T9交叉最佳

| 组合 | N | WR | R5 | Sharpe | 特点 |
|:---:|:-:|:--:|:--:|:-----:|:----:|
| CROSS-10 | 784 | 70.54% | 12.12% | 5.20 | 最佳容量质量平衡 |
| CROSS-1 | 501 | 74.25% | 11.22% | 5.03 | 双日恐慌+SPX+振幅7% |
| CROSS-14 | 221 | 82.35% | 9.32% | 6.97 | 极致低回撤(P10=-1.72%) |
| CROSS-3 | 981 | 67.58% | 10.49% | 4.72 | CM扩容版(30→50亿) |
| CROSS-9 | 2,486 | 72.00% | 6.00% | 2.85 | 最佳大容量版 |

### 🆕 新因子发现

1. **🆕 振幅≥7% = 通用强化因子**: 在T4/T7/T9中均验证有效。振幅因子价值随宏观和资金条件叠加而放大
2. **🆕 双日温和恐慌(-3%)替代-5%**: 信号量+158%, WR仅降28pp — 最佳质量-容量平衡阈值
3. **🆕 散户割肉+净流入双确认**: T4流派最强因子对
4. **🆕 深价值恐慌保护**: PE≤15+dv≥3%在恐慌场景中提供P10=-1.72%极致保护
5. **🆕 非恐慌模式**: 涨≥3%+散户割肉+大单(解套盘+机构接盘)在大容量下有效

### 流派纪录刷新

| 流派 | 新纪录 | 详情 |
|:----|:------|:-----|
| T7 | 🏆 **R5新纪录 16.51%** | T7-C3超越Iter25 T4-V6(11.47%)+44% |
| T3 | 🏆 **Sharpe新纪录 6.564** | T3-C5超越之前T3最佳 |
| T4 | ✅ 全满贯(5/5 PASS) | 史上首次T4流派全通过 |
| T7 | ✅ 全满贯(5/5 PASS) | 史上首次T7流派全通过 |

### ℹ️ 未超越全局纪录

- 全部全局纪录(WR=99.55%, R5=25.23%, Sharpe=20.227)仍由Iter25 CROSS-6保持
- **fatigue_count: {state['fatigue_count']} → {new_fatigue}**

### 📌 下轮建议
1. T7-C3扩容(CM 30→50→100亿)
2. CROSS-10参数精炼(VR阈值优化)
3. CROSS-14扩容(CM→100亿, PE→20)
4. T8-C7+振幅≥7%(预期R5>5%)
5. 双日恐慌阈值系统化优化(-2%/-3%/-4%/-5%)
"""

with open(KB_PATH, 'a') as f:
    f.write(kb_addition)

print(f"✅ knowledge_base.md updated")
print(f"\n=== ALL UPDATES COMPLETE ===")
print(f"fatigue_count: {state['fatigue_count']} -> {new_fatigue}")
print(f"Records broken: {len(records_broken)}")
