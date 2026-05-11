# Kanban 任务创建规则 — 通用模板

> 新建 Kanban 策略时复制此文件到 `新策略/rules/task-creation-rules.md`，替换所有 `{{占位符}}`。
> 基于 2026-05-10 实际测试经验总结。

---

## 一、流水线架构

```
{{阶段一名称}} {{时间}}（T1-T{{n1}}）──→ {{阶段二名称}} {{时间}}（T{{n1+1}}-T{{n2}}）──→ {{阶段三名称}} {{时间}}（T{{n2+1}}-T{{n3}}）
```

### 任务依赖链

```
{{填写任务依赖图，示例：}}
T1(researcher) ─┐
T2(researcher) ─┼──→ T5(analyst) ──→ T6(analyst) ──→ T7(writer)
T3(researcher) ─┤
T4(researcher) ─┘
```

> **规则**：无依赖任务并发创建，有依赖的通过 `parents=[...]` 串行。

---

## 二、数据查询工具规范

### 2.1 主数据源

**脚本路径**：`{{填写主数据查询脚本的绝对路径}}`

```bash
# 示例命令（根据实际工具修改）
python3 {{路径}} sql "SELECT ..."
python3 {{路径}} max_date
```

**硬规则**：
- SQL 规则：{{如 ReplacingMergeTree 必须加 FINAL}}
- 日期格式：{{如 YYYYMMDD}}
- 连接方式：{{如 直连 / MCP}}

**⚠️ 字段名验证**：

| 表 | 正确字段 | ❌ 不存在的字段 |
|---|---------|---------------|
| {{表1}} | {{字段}} | ~~{{错误字段}}~~ |
| {{表2}} | {{字段}} | ~~{{错误字段}}~~ |

不确定时先用 `describe` 确认字段。

### 2.2 外盘行情

```bash
# MT5 或等效工具
{{填写命令}}

# global-futures 或等效工具
{{填写命令}}
```

### 2.3 新闻搜索

```bash
# tavily-skills 或等效工具
{{填写命令}}
```

**⚠️ 禁止用新闻工具查询价格/指数/汇率等数值行情。**

---

## 三、时间上下文注入规则

每个 `kanban_create` 任务的 `body` 开头必须注入：

```
## 📅 时间上下文（强制遵守）
- 系统执行时间：YYYY-MM-DD HH:mm UTC+8
- 今日日期：YYYY-MM-DD
- ⚠️ 规则：
  1. 日志文件名中的日期必须使用系统执行日期。
  2. 数据查询必须先确认数据基准日期。
  3. 报告中的日期必须读取交易日历结果。
  4. 禁止使用"周一/周五"等推测词，统一使用 YYYY-MM-DD。
```

---

## 四、日志与报告路径

### 4.1 绝对路径（禁止相对路径）

```
策略目录：{{策略绝对路径}}/
日志：{{策略绝对路径}}/logs/
报告：{{策略绝对路径}}/reports/
```

**⚠️ Worker 的 scratch workspace 是独立的（各自 profile 下），不能假设 `./logs/` 指向策略目录。**

### 4.2 文件命名规范

```
{{阶段一}}：screen-{YYYYMMDD}-{01..{{n1}}}-{步骤名}.md
{{阶段二}}：converge-{YYYYMMDD}-{{...}}-{步骤名}.md
{{阶段三}}：preopen-{YYYYMMDD}-{{...}}-{步骤名}.md

最终报告：
  {{报告文件名格式1}}
  {{报告文件名格式2}}
```

---

## 五、Profile 角色分配

| 任务 | Profile | 角色 | 说明 |
|------|---------|------|------|
| T1-T4 | researcher | 数据查询 | {{说明}} |
| T5 | analyst | 分析 | {{说明}} |
| T6 | analyst | 分析 | {{说明}} |
| T7 | writer | 报告 | {{说明}} |

> 根据实际策略增减任务行。

### 5.1 Soul 注入

每个任务 `body` 中必须追加对应 Soul：
- researcher: `你的核心工作原则请参考：./skills/researcher-soul.md。`
- analyst: `你的核心工作原则请参考：./skills/analyst-soul.md。`
- writer: `你的核心工作原则请参考：./skills/writer-soul.md。`

---

## 六、Cron Job 配置

| Job | 调度 | 模型 | 工作目录 |
|-----|------|------|---------|
| {{阶段一}} | `{{cron表达式}}` | deepseek-v4-flash | `{{策略路径}}/` |
| {{阶段二}} | `{{cron表达式}}` | deepseek-v4-flash | `{{策略路径}}/` |
| {{阶段三}} | `{{cron表达式}}` | deepseek-v4-flash | `{{策略路径}}/` |

**注意**：Orchestrator 统一用 flash 模型，pro 模型曾导致 `[SILENT]` 静默失败。

---

## 七、已知陷阱清单

| # | 陷阱 | 表现 | 修复 |
|---|------|------|------|
| 1 | 周末手动触发 Cron | 模型识别非交易日返回 `[SILENT]` | 添加测试标记，或等待交易日自动触发 |
| 2 | 日志写到 scratch workspace | 策略目录找不到日志 | 使用绝对路径 |
| 3 | 字段名不存在 | SQL 报错 | 先用 `describe` 确认字段 |
| 4 | pro 模型 Orchestrator | 返回 `[SILENT]` | 统一用 flash 模型 |
| {{n}} | | | |

> 每踩一个新坑就在此追加一行。

---

## 八、Kanban DB 软链接（首次部署必做）

```bash
cd ~/.hermes/profiles
for p in researcher analyst writer; do
  [ -f "$p/kanban.db" ] && mv "$p/kanban.db" "$p/kanban.db.bak"
  ln -sf ../reze/kanban.db "$p/kanban.db"
done
```
