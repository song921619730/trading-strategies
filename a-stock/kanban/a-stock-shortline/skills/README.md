# A 股短线策略专属技能库 (Strategy Skills)

本目录用于存放 **仅适用于 a-stock-shortline 策略** 的业务规则和技能文件。
这些文件将在 Kanban 任务运行时，按需注入到对应的 Profile 任务上下文中。

## 文件命名规范
- 使用小写字母和连字符，例如：`risk-rules.md`
- 文件名应反映其服务的角色或功能，例如：`risk-rules.md`（供风控官使用）、`sector-analysis.md`（供专家使用）。

## 使用方式
在 `cron-prompts/` 的任务描述中，通过以下方式挂载：
- 例如：`T6 risk_manager (+skills/risk-rules.md) 风控审核`

## 当前可用技能
目前为空，请根据策略需求添加。
