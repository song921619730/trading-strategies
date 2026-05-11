#!/bin/bash
# 批量运行 lowopen 研究 50 次 (v2 - 容错版)
cd /mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/lowopen

MAX_RUNS=50
SUCCESS=0
FAIL=0

for i in $(seq 1 $MAX_RUNS); do
    echo ""
    echo "========================================"
    echo "  Batch $i / $MAX_RUNS  |  $(date '+%H:%M:%S')"
    echo "========================================"
    python3 orchestrator.py
    RC=$?
    if [ $RC -eq 0 ]; then
        ((SUCCESS++))
    else
        ((FAIL++))
        echo "⚠️  异常退出 (code=$RC)，跳过继续下一轮"
        sleep 1
        # 检查是否还有必要继续
        python3 -c "
import json
with open('state/lowopen_state.json') as f:
    s = json.load(f)
fc = s.get('fatigue_count', 0)
print(f'Current fatigue: {fc}')
if fc >= 10:
    print('MAX_FATIGUE')
else:
    print('CONTINUE')
" 2>/dev/null | grep -q "MAX_FATIGUE" && { echo "🛑 疲劳度已达上限，停止"; break; }
    fi
    sleep 1
done

# 最终报告打包
TIMESTAMP=$(date +"%Y%m%d-%H%M")
cp logs/final_report.md "reports/lowopen-research-batch50-${TIMESTAMP}.md"

echo ""
echo "========================================"
echo "  ✅ 批量运行完成"
echo "  成功: $SUCCESS  |  失败: $FAIL"
echo "  最终报告: reports/lowopen-research-batch50-${TIMESTAMP}.md"
python3 -c "
import json
with open('state/lowopen_state.json') as f:
    s = json.load(f)
print(f'  总迭代: {s[\"current_iteration\"]}')
print(f'  最佳: {s[\"best_metrics\"].get(\"best_5d_return\", 0):.2%}')
print(f'  疲劳度: {s[\"fatigue_count\"]}')
"
echo "========================================"
