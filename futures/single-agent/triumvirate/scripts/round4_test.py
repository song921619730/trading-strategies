#!/usr/bin/env python3
"""
scripts/round4_test.py — Round 4: Scalping M1/M5 Pattern Research
=============================================================
流程:
  Phase 1: 通过 MT5 获取 M1/M5 实时数据
  Phase 2: Grid Engine 模式挖掘 + 预测能力分析
  Phase 3: 生成研究报告 + 更新 State
"""
import sys, os, json, subprocess
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)

STATE_PATH = os.path.join(PROJECT_DIR, "state", "research_state.json")
GRID_ENGINE_PATH = os.path.join(PROJECT_DIR, "grid_engine.py")
FETCH_SCRIPT_PATH = os.path.join(SCRIPT_DIR, "fetch_m1m5_data.py")

WINDOWS_PYTHON = r"C:\Users\gj\AppData\Local\Programs\Python\Python312\python.exe"
WSL_PYTHON = sys.executable


def step1_fetch_data():
    """Phase 1: Fetch M1/M5 data from MT5 via Windows Python"""
    print("=" * 60)
    print("📡 Phase 1: 获取 M1/M5 数据")
    print("=" * 60)
    
    # Check if data already exists
    latest_data = os.path.join(PROJECT_DIR, "data", "m1m5_latest.json")
    if os.path.exists(latest_data):
        with open(latest_data, 'r') as f:
            existing = json.load(f)
        fetch_time = existing.get('meta', {}).get('fetch_time_cst', '')
        print(f"  已有数据: {fetch_time}")
        
        # Check if data is fresh (< 30 min)
        if fetch_time:
            try:
                ft = datetime.strptime(fetch_time, "%Y-%m-%d %H:%M:%S")
                now = datetime.now(CST)
                diff_min = (now - ft).total_seconds() / 60
                if diff_min < 30:
                    print(f"  数据够新 ({diff_min:.0f}分钟前)，跳过重新获取")
                    return existing
            except:
                pass
    
    # Try to fetch via Windows Python
    print(f"  执行: {WINDOWS_PYTHON} {FETCH_SCRIPT_PATH}")
    try:
        result = subprocess.run(
            [WINDOWS_PYTHON, FETCH_SCRIPT_PATH],
            capture_output=True, text=True, timeout=60,
            cwd=PROJECT_DIR
        )
        if result.returncode == 0:
            try:
                data = json.loads(result.stdout)
                print(f"  ✅ 获取成功: {len(data.get('data', {}))} 个品种")
                return data
            except json.JSONDecodeError:
                print(f"  ⚠️ 输出非JSON格式，尝试文件")
        else:
            print(f"  ❌ 获取失败 (rc={result.returncode})")
            print(f"     stderr: {result.stderr[:200]}")
    except FileNotFoundError:
        print(f"  ⚠️ Windows Python 不可用: {WINDOWS_PYTHON}")
    except subprocess.TimeoutExpired:
        print(f"  ⚠️ MT5 数据获取超时")
    except Exception as e:
        print(f"  ⚠️ 异常: {e}")
    
    # Fallback: try using existing data
    if os.path.exists(latest_data):
        print("  使用已有数据文件")
        with open(latest_data, 'r') as f:
            return json.load(f)
    
    print("  ❌ 无可用数据")
    return None


def step2_run_grid_engine(data):
    """Phase 2: Run Grid Engine for pattern mining"""
    print()
    print("=" * 60)
    print("🔬 Phase 2: Grid Engine 模式挖掘")
    print("=" * 60)
    
    # Save data for grid_engine
    data_path = os.path.join(PROJECT_DIR, "data", "m1m5_latest.json")
    with open(data_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    # Import and run grid_engine
    sys.path.insert(0, PROJECT_DIR)
    import grid_engine
    
    engine = grid_engine.GridEngine(data)
    result = engine.run()
    
    timestamp = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
    report_md = grid_engine.generate_report(result, timestamp)
    
    # Save report
    ts = datetime.now(CST).strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(PROJECT_DIR, "reports", f"{ts}_M1M5_超短线模式挖掘报告.md")
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report_md)
    
    # Save research data
    data_out_path = os.path.join(PROJECT_DIR, "reports", f"research_data_{ts}.json")
    with open(data_out_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    print(f"  ✅ 报告: {report_path}")
    print(f"  ✅ 数据: {data_out_path}")
    
    return result, report_md, report_path


def step3_update_state(result, report_path):
    """Phase 3: Update research state"""
    print()
    print("=" * 60)
    print("📝 Phase 3: 更新研究状态")
    print("=" * 60)
    
    agg = result.get('aggregated', {})
    meta = result.get('meta', {})
    
    # Build key findings
    findings = []
    for pname, st in sorted(agg.items(), key=lambda x: -x[1]['count']):
        if st['count'] < 3:
            continue
        n1b = st.get('bullish_rate_n1_pct', 0) or 0
        n1be = st.get('bearish_rate_n1_pct', 0) or 0
        n3c = st.get('avg_chg_n3_pct', 0) or 0
        
        cn_map = {
            'micro_bull_engulf': '微看涨吞没',
            'micro_bear_engulf': '微看跌吞没',
            'micro_doji_bull_reversal': '十字星看涨反转',
            'micro_doji_bear_reversal': '十字星看跌反转',
            'micro_volume_climax': '天量高潮反转',
            'micro_staircase_bull': '阶梯上涨',
            'micro_staircase_bear': '阶梯下跌',
            'micro_pinbar_bull': '锤头线(微)',
            'micro_pinbar_bear': '射击之星(微)',
            'micro_narrow_range_7': '窄幅7连',
            'micro_absorption': '吸收形态',
        }
        cn = cn_map.get(pname, pname)
        
        if n1b >= 65:
            findings.append(f"{cn} M1/M5看涨率{n1b:.1f}% (N3:{n3c:+.4f}%), 样本{st['count']}次")
        elif n1be >= 65:
            findings.append(f"{cn} M1/M5看跌率{n1be:.1f}% (N3:{n3c:+.4f}%), 样本{st['count']}次")
    
    if not findings:
        findings.append("本周期未发现高置信度模式，可能需要更多历史数据或调整形态阈值")
    
    # Next hypotheses
    hypotheses = [
        "M1吞没形态的ATR动态阈值优化",
        "分时段(亚/欧/美盘)M1/M5模式胜率差异研究",
        "结合tick_volume的微观形态预测能力提升",
    ]
    if agg:
        top_p = max(agg.items(), key=lambda x: x[1]['count'])[0]
        hypotheses.append(f"针对{cn_map.get(top_p, top_p)}的参数敏感性分析")
    
    state = {
        "round": 4,
        "topic": "M1/M5 超短线模式挖掘 (Scalping Research)",
        "branch": "scalping_research",
        "timeframes": ["M1", "M5"],
        "symbols": meta.get('symbols_analyzed', []),
        "status": "completed",
        "last_update": datetime.now(CST).strftime("%Y-%m-%dT%H:%M:%S"),
        "last_report": report_path,
        "total_patterns": meta.get('total_patterns_found', 0),
        "key_findings": findings,
        "next_hypotheses": hypotheses,
    }
    
    # Save state
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    
    # Also save round-specific state
    round4_path = os.path.join(PROJECT_DIR, "state", "research_state_round4.json")
    with open(round4_path, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    
    print(f"  ✅ 状态已更新: round 4")
    print(f"  📌 发现: {len(findings)} 条")
    
    return state


def main():
    print("🚀 Triumvirate Round 4: Scalping M1/M5 研究循环")
    print(f"   时间: {datetime.now(CST).strftime('%Y-%m-%d %H:%M:%S')} CST")
    print()
    
    # Phase 1: Fetch data
    data = step1_fetch_data()
    if data is None:
        print("❌ 无法获取M1/M5数据，终止研究循环")
        # Still produce a basic report
        basic_report_path = os.path.join(PROJECT_DIR, "reports", 
            f"{datetime.now(CST).strftime('%Y%m%d_%H%M%S')}_M1M5_报告_数据不可用.md")
        with open(basic_report_path, 'w', encoding='utf-8') as f:
            f.write("# ⚠️ M1/M5 数据不可用\n\nMT5 连接失败，请检查:\n1. MT5 是否运行\n2. 网络/路径配置\n")
        print(f"  ⚠️ 基本报告: {basic_report_path}")
        return
    
    # Phase 2: Run grid engine
    result, report_md, report_path = step2_run_grid_engine(data)
    
    # Phase 3: Update state
    state = step3_update_state(result, report_path)
    
    # Final output
    print()
    print("=" * 60)
    print("🎯 Round 4 研究循环完成")
    print("=" * 60)
    print()
    
    # Print report summary
    print(report_md[:2000])
    print()
    print("..." if len(report_md) > 2000 else "")
    
    # Print next steps
    print()
    print("📋 下一轮方向:")
    for i, h in enumerate(state['next_hypotheses'], 1):
        print(f"  {i}. {h}")


if __name__ == "__main__":
    main()
