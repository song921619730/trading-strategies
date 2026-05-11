# Pure AI CIO Strategy (Magic 234003)

**定位**: 低频·高容错·净值优先的执行型 CIO

## 核心原则
- **净值稳定**: 避免连续亏损，捕捉已验证趋势。
- **第二段行情**: 只交易 H1 级别的回调确认后的第二段趋势。
- **严格过滤**: Trade Gate 拦截震荡和假突破。
- **不交易也是决策**: 市场不满足条件时强制空仓。

## 目录结构
- `config/`: Cron Prompt 和策略规则配置
- `scripts/`: 交易执行脚本 (`execute_trade.py`)
- `templates/`: 扫描报告模板 (`report.md`)
- `logs/`: 交易日志和扫描记录

## 注意事项
- Magic Number: **234003**
- 执行脚本位于 `scripts/execute_trade.py`
