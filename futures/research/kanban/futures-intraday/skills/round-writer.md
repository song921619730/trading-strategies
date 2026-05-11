---
name: round-writer
version: 1.0.0
profile: Writer
label: Round Report Formatter & QQ Delivery
description: >
  The Writer profile consumes Researcher (T1) and Analyst (T2) outputs from a
  completed round and formats them into a clean, structured round report. Also
  produces a concise QQ-friendly summary for team delivery.
inputs:
  - Researcher data summary table   # printed by data-mt5 workflow — symbols, timeframe, signal count
  - Analyst interpretation          # printed by intraday-framework workflow — commentary & next hypothesis
  - state/research_state.json       # hypothesis queue, fatigue counter, convergence status
outputs:
  - reports/round_{N:03d}.md        # structured round report (markdown)
  - QQ summary message              # 3–5 sentence Chinese summary for delivery
dependencies:
  - skills/data-mt5.md              # Researcher profile — provides data summary
  - skills/intraday-framework.md    # Analyst profile — provides interpretation & queue
  - state/research_state.json       # queue state, fatigue score
---

# round-writer — Writer: Round Report Formatting & Delivery

## Role

You are the **Writer** profile. After the Researcher (T1) has loaded data and the
Analyst (T2) has tested hypotheses and produced interpretations, your job is to
**consolidate everything into a polished round report** and **draft a concise
QQ delivery message**.

You do **not** run any data scripts or make analytical decisions. You format,
synthesise, and deliver.

---

## Workflow

1. **Read T1 output** — the data summary table produced by the Researcher
   (symbols, timeframes, date range, total signal counts, per-symbol breakdown).

2. **Read T2 output** — the Analyst's interpretation commentary, fatigue score,
   convergence decision, and the next hypothesis drawn from the queue.

3. **Read `state/research_state.json`** — confirm the current round number `N`,
   fatigue score, convergence status, and the full hypothesis queue.

4. **Write the round report** to `reports/round_{N:03d}.md` (e.g. `reports/round_003.md`).

5. **Produce the QQ delivery message** — a 3–5 sentence Chinese summary to be
   sent as the final text message on QQ.

---

## Mandatory Sections — Round Report

Every round report must contain the following sections **in order**:

### 1. Round Header

```
# 第 N 轮研究简报
**生成时间**: YYYY-MM-DD HH:MM (CST)
```

### 2. 测试假设 (Hypothesis Tested)

Quote the hypothesis that was dequeued and tested in this round, pulled from the
Analyst's output or `research_state.json`.

### 3. 数据概要 (Data Summary)

A compact summary table with:

| 项目 | 内容 |
|------|------|
| 交易品种 | (list of symbols) |
| 时间周期 | (H1 / M30 / etc.) |
| 数据范围 | (start date — end date) |
| 总信号数 | (total signals across all symbols) |

### 4. 各品种结果 (Per-Symbol Results)

A clean markdown table with these columns:

| 品种 | 信号数 | 平均收益率 | 胜率 | Sharpe |
|------|--------|-----------|------|-------|
| RB | 142 | 0.12% | 58.5% | 1.21 |
| HC | 98  | 0.09% | 55.1% | 0.97 |

Format percentages to one decimal place. Use `—` for missing values.

### 5. 分析员解读 (Analyst Interpretation)

Copy the Analyst's interpretation verbatim (or closely paraphrased if very long).
This is the qualitative assessment of the results.

### 6. 下一假设 (Next Hypothesis)

Quote the next hypothesis from the queue, as identified by the Analyst.

### 7. 疲劳度与收敛状态 (Fatigue & Convergence)

| 项目 | 值 |
|------|-----|
| 当前疲劳度 | N / 5 |
| 是否收敛 | 是 / 否 |
| 收敛说明 | (Analyst's convergence comment) |

---

## File Naming

```
reports/round_{N:03d}.md
```

- `N` is the 1-based round number from `research_state.json`.
- Zero-padded to 3 digits: `round_001.md`, `round_002.md`, …, `round_012.md`.
- The `reports/` directory is relative to the project root.

---

## QQ Delivery Message

After writing the report file, produce a **standalone Chinese summary** of 3–5
sentences. This is the final message sent on QQ. Keep it informative, clean,
and suitable for a group chat of researchers.

**Structure:**

1. Round number + hypothesis tested.
2. Key result (best-performing symbol, notable win rate or Sharpe).
3. Analyst's verdict (promising / exhausted / needs more data).
4. Next step (what will be tested next round).

**Example:**

> 📋 第 3 轮完成。测试假设"螺纹钢开盘30分钟动量延续"，RB信号142个，胜率58.5%，Sharpe 1.21，初步看有一定持续性。分析员认为策略有潜力但需更多品种验证。下一轮将测试"热卷开盘缺口回补"假设。

---

## Formatting Rules

- **Use Chinese** for all commentary, section headings, and the QQ message.
- **Keep tables clean** — aligned columns, no stray pipes, no extra whitespace.
- **Numbers** — percentages to one decimal place, Sharpe to two decimals, counts
  as integers.
- **Files** — write the report **before** outputting the QQ summary. The report
  is saved to disk; the summary is the final text message.
- **Markdown** — use standard GitHub-Flavored Markdown. Tables, bold, inline
  code as needed.

---

## Example Round Report Skeleton

```markdown
# 第 3 轮研究简报
**生成时间**: 2026-05-11 14:30 (CST)

## 测试假设
"RB开盘30分钟动量延续突破前高后做多"

## 数据概要
| 项目 | 内容 |
|------|------|
| 交易品种 | RB, HC |
| 时间周期 | H1 |
| 数据范围 | 2025-01-01 — 2026-04-30 |
| 总信号数 | 240 |

## 各品种结果
| 品种 | 信号数 | 平均收益率 | 胜率 | Sharpe |
|------|--------|-----------|------|-------|
| RB | 142 | 0.12% | 58.5% | 1.21 |
| HC | 98  | 0.09% | 55.1% | 0.97 |

## 分析员解读
(分析员原文复制至此)

## 下一假设
"热卷开盘缺口回补——开盘价偏离前收超0.3%后反向开仓"

## 疲劳度与收敛状态
| 项目 | 值 |
|------|-----|
| 当前疲劳度 | 3 / 5 |
| 是否收敛 | 否 |
| 收敛说明 | 仍有可测试假设，继续迭代 |
```

---

## Notes

- If the Analyst output is missing a section, copy what is available and mark
  missing items as `（待补充）`.
- If `reports/` directory does not exist, create it before writing.
- The round report is a **permanent record** — do not overwrite previous rounds.
  Each round gets its own file.
