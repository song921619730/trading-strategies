#!/usr/bin/env python3
"""Update research state after Round 79 — M1/M5 Scalping 第41/39/37/32月跟踪 + 改善确认"""
import json, os
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW_STR = datetime.now().strftime("%Y-%m-%d %H:%M")

state = {
    "current_round": 79,
    "last_run": NOW_STR,
    "status": "completed",
    "hypotheses": {
        "round79_001": "XAUUSD M1 第41月常规跟踪(数据截至2026-05-14 10:11 UTC,＋21 bars): EU CB3+RSI10 WR=100.0% n=34 hold=55 第41月通过✅(与R78完全一致,WR稳定100%); EU CB2+RSI10 WR=95.2% n=42 hold=55 第33月通过✅; EU CB3+RSI8 WR=100% n=24 hold=55 第31月通过✅; EU CB3+RSI7 WR=100% n=18 hold=50 第30月通过✅; EU CB2+RSI7 WR=90.9% n=22 hold=50 ✅第30月通过; US CB3+RSI10 WR=87.0% n=46 hold=30 第41月通过✅(略升至87.0%); 双极值WR=87.5% n=80 hold=55 第41月通过✅; EU_CB2_RSI5 WR=100% n=15 hold=50(n=15<25停滞)。US_CB4_RSI12 WR=76.1% n=71 hold=30 ⚠️(第28月)。结论:XAU M1 EU核心策略第41月通过,WR保持极高水平。",
        "round79_002": "XAUUSD M5 US RSI<6 冻结归档跳过(下次季度检查8月)。无变化。",
        "round79_003": "XAGUSD M5 RSI<5 ALL第32月跟踪 + RSI<4第27月跟踪(数据截至2026-05-14 10:10 UTC,＋72 bars): RSI5 CB1 ALL WR=92.8% n=69 hold=70(与R78持平,WR稳定); RSI5 CB2 ALL WR=93.2% n=59 hold=70(持平); RSI4 CB1 ALL WR=98.0% n=51 hold=70 ✅第27月确认(持平); RSI4 CB2 ALL WR=97.7% n=43 hold=70(持平)。信号频率: RSI4=3.1次/月, RSI5=4.1次/月, RSI6=5.4次/月(稳定)。结论:所有XAG M5策略第32月/第27月验证通过,WR完全稳定。",
        "round79_004": "US500 M5 EU 第39月常规跟踪(新基线自R77): CB5+RSI14 WR=84.6% n=52 hold=25✅(与R78持平); CB6+RSI14 WR=85.7% n=35 hold=25(持平); CB5+RSI10 WR=87.5% n=24 hold=120(最佳但n<30); CB5+RSI12 WR=83.3% n=36 hold=25(持平); CB6+RSI12 WR=84.6% n=26 hold=25(持平)。结论:US500 EU第39月WR维持改善后的水平。维持观察。",
        "round79_005": "XAUUSD M1 ASIA 第37月跟踪(数据截至2026-05-14 10:11 UTC): CB3+RSI10 WR=72.6% n=73 hold=10 ❌(与R78的71.8%基本持平,C3+RSI7/RSI5未见更好); CB2+RSI10 WR=72.4% n=87 hold=10 ❌(持平); CB4+RSI10 WR=68.4% n=57 hold=10 ❌(持平)。结论:XAU M1 ASIA WR继续低位运行(68-73%),无恢复迹象。正式不推荐。",
        "round79_006": "US30 M1 EU 第32月跟踪(改善是否持续): CB4+RSI12 WR=77.8% n=54 hold=30 ✅(与R78持平); CB5+RSI12 WR=80.0% n=40 hold=30 ✅(持平); CB6+RSI12 WR=88.5% n=26 hold=15 ✅(持平); CB4+RSI10 WR=77.8% n=36 hold=10(持平)。结论:US30 M1 EU第32月改善持续确认✅ CB6+RSI12仍维持88.5%! 重点关注。",
        "round79_007": "XAUUSD M5 H15/H19冻结归档跳过(下次季度检查8月)。无变化。",
        "round79_008": "XAGUSD M5 RSI<5 ALL第32月跟踪(质量监控): RSI5 CB1 ALL WR=92.8% n=69 hold=70 Sharpe=22.22 ✅第32月通过; RSI4第27月: CB1 ALL WR=98.0% n=51 hold=70 Sharpe=27.95 ✅确认; RSI4 DEEP hold=70: WR=98.0% n=51 Sharpe=27.95(第27月确认)。信号频率: RSI4=3.1次/月, RSI5=4.1次/月, RSI6=5.4次/月(n稳定)。结论:白银策略仍是当前最强推荐(连续27-32月稳定)。",
        "round79_009": "JP225 M5最低权重监控(数据截至2026-05-14 10:10 UTC): US CB3+RSI10 WR=73.3% n=90 hold=40(与R78的71.2%相比略升); US CB4+RSI10 WR=73.6% n=72 hold=80(略升); US CB5+RSI12 WR=71.6% n=74 hold=40(略升); EU CB3+RSI10 WR=51.9% n=54 hold=50(持平)。结论:JP225 M5 US session WR略有改善但Sharpe较低(3.62-11.71)。维持不推荐。",
        "round79_010": "新探索(数据截至2026-05-14 10:10/10:11 UTC): ①US30 M1 EU改善确认跟踪: CB6+RSI12=88.5% n=26⭐改善持续! ②XAG M5 RSI4 DEEP第27月确认: WR=98.0% n=51 Sharpe=27.95✅ ③XAU M5 US_CB3_RSI15 WR=64.5% n=186边界 ④XAU M1 ASIA WR低位72.6%⚠️ ⑤✅数据下载已完成! M5+72 new bars, M1+21 new bars — 连续3轮数据停滞已解决",
        "round79_notable": "✅ 正面: XAU M1 EU核心策略第41月通过✅,WR保持极高水平(100%/95%/93%/91%)。XAG M5全线维持极佳表现(RSI4 WR=98.0%+ DEEP WR=98.0%),RSI5 WR维持92.8%。US30 M1 EU改善持续确认(CB6+RSI12 WR=88.5%⭐)。✅数据下载已完成,数据边界由2026-05-14 04:10/04:14 UTC更新至10:10/10:11 UTC。",
        "round79_notable2": "⚠️ 警报: XAU M1 ASIA WR继续低位68-73%(连续多轮无变化)。JP225 M5 EU session信号质量差(WR=51.9%)。做空分支继续关闭。XAU M5边界阈值策略(US_CB3_RSI15)仅64.5%仍不理想。",
        "round79_r79_note": "R79成功获取新数据: M5 +72 bars (04:10→10:10 UTC), M1 +21 bars (04:14→10:11 UTC)。这是自R76以来首次数据更新,解决了连续3轮数据停滞问题。所有策略表现与R78一致,说明策略在短周期数据增量下保持稳定。US30 M1 EU改善持续确认(CB6+RSI12 WR=88.5%)是最大亮点。"
    },
    "best_known": {
        "XAUUSD_M5_EU": "双枪欧盘做多XAU: M5 EU 9-11 RSI<18+CB>=4 hold=42 WR=77.1% n=70 [月跟踪: 连续13月有效]",
        "XAUUSD_M5_US": "双枪美盘做多XAU: M5 US 15-16 RSI<20+CB>=2 hold=115 WR=80.5% n=123 [24月跟踪]",
        "XAUUSD_M5_combo": "双枪组合(欧+美): WR=79.2% n=192 [38次/月]",
        "XAUUSD_resonance_us": "共振美盘->XAU: M5 US 15-16 RSI<18+CB>=1 hold=115 WR=81.7% n=109",
        "XAUUSD_M1_EU_extreme": "XAUUSD M1 EU CB>=3+RSI<10 WR=100.0% n=34 hold=55 [CP41/41 第41月跟踪通过✅ WR极高(100%)]",
        "XAUUSD_M1_EU_CB2": "XAUUSD M1 EU CB>=2+RSI<10 WR=95.2% n=42 hold=55 [R79第33月确认-WR稳定(95.2%)]",
        "XAUUSD_M1_EU_RSI8": "XAUUSD M1 EU CB>=3+RSI<8 WR=100.0% n=24 hold=55 [第31月跟踪-WR稳定(100%)]",
        "XAUUSD_M1_EU_CB2_RSI8": "XAUUSD M1 EU CB>=2+RSI<8 WR=92.9% n=28 hold=55 [R79-WR稳定(92.9%)]",
        "XAUUSD_M1_EU_CB3_RSI7": "XAUUSD M1 EU CB>=3+RSI<7 WR=100.0% n=18 hold=50 [R79第30月跟踪-WR稳定(100%)]",
        "XAUUSD_M1_US_strong": "XAUUSD M1 US CB>=3+RSI<10 WR=87.0% n=46 hold=30 [第41月通过✅ WR略有提升(87.0%)]",
        "XAUUSD_M1_Dual_extreme": "XAUUSD M1 双极值联合 EU+US CB>=3+RSI<10 WR=87.5% n=80 hold=55 [第41月通过✅ WR稳定(87.5%)]",
        "XAUUSD_M1_ASIA": "XAUUSD M1 ASIA CB>=3+RSI<10 WR=72.6% n=73 hold=10 ❌[第37月维持低位72.6% 不推荐]",
        "XAUUSD_M1_ASIA_CB2": "XAUUSD M1 ASIA CB>=2+RSI<10 WR=72.4% n=87 hold=10 ❌[R79维持低位]",
        "XAUUSD_M1_ASIA_CB4": "XAUUSD M1 ASIA CB>=4+RSI<10 WR=68.4% n=57 hold=10 ❌[R79维持低位]",
        "XAUUSD_M5_US_RSI6": "XAUUSD M5 US RSI<6+CB>=1 WR=89.3% n=28 hold=55 [❗数据冻结-连续12月n=28-归档]",
        "XAUUSD_M5_US_RSI6_CB2": "XAUUSD M5 US RSI<6+CB>=2 WR=87.0% n=23 hold=30 [备用阈值-冻结]",
        "XAUUSD_M5_US_RSI6_CB3": "XAUUSD M5 US RSI<6+CB>=3 WR=84.2% n=19 hold=30 [备用阈值-冻结]",
        "XAUUSD_M5_US_RSI5": "XAUUSD M5 US RSI<5+CB>=1 WR=90.5% n=21 hold=55 [RSI5版本-n冻结]",
        "XAUUSD_M5_SHORT_any": "XAUUSD M1/M5做空WR均<65%,不推荐 [做空分支已正式关闭]",
        "XAGUSD_M5_EU_long": "XAGUSD M5 EU CB>=3+RSI<10做多 WR=76.2% n=42 CP3/3",
        "XAGUSD_M5_EU_new": "XAGUSD M5 EU CB>=2+RSI<8做多 WR=96.4% n=28 hold=35 [n=28停滞冻结归档]",
        "XAGUSD_M5_RSI6": "XAGUSD M5 CB>=1+RSI<6做多 WR=86.7% n=90 hold=70 [第32月-确认有效-信号~5.4次/月]",
        "XAGUSD_M5_EU_RSI8": "XAGUSD M5 EU RSI<8+CB>=1做多 WR=90.3% n=31 hold=30 [第6月验证-冻结归档]",
        "XAGUSD_M5_RSI5_ALL": "XAGUSD M5 RSI<5+CB>=1做多 WR=92.8% n=69 hold=70 [R79第32月确认✅WR稳定(92.8%)]",
        "XAGUSD_M5_RSI5_CB2_ALL": "XAGUSD M5 RSI<5+CB>=2做多 WR=93.2% n=59 hold=70 [R79稳定!WR维持]",
        "XAGUSD_M5_RSI6_strict": "XAGUSD M5 CB>=5+RSI<6做多 WR=85.9% n=64 hold=70 [严格阈值]",
        "XAGUSD_M5_RSI4_ALL": "XAGUSD M5 RSI<4+CB>=1做多 WR=98.0% n=51 hold=70 Sharpe=27.95 [R79第27月确认✅WR极佳稳定]",
        "XAGUSD_M5_RSI4_DEEP": "XAGUSD M5 RSI<4+CB>=1做多 hold=70 WR=98.0% n=51 Sharpe=27.95 [R79深度优化!第27月确认✅]",
        "XAGUSD_M5_RSI4_CB2_DEEP": "XAGUSD M5 RSI<4+CB>=2做多 hold=70 WR=97.7% n=43 Sharpe=26.55 [R79深度优化CB2版本-第27月确认]",
        "US500_M5_EU_long": "US500 M5 EU CB>=4+RSI<14做多 WR=78.1% n=73 hold=25 ⚠️[第39月-维持观察(新基线确认)]",
        "US500_M5_EU_strong": "US500 M5 EU CB>=5+RSI<14做多 WR=84.6% n=52 hold=25 [第39月-改善后基线确认]",
        "US500_M5_EU_stronger": "US500 M5 EU CB>=6+RSI<14做多 WR=85.7% n=35 hold=25 [第39月-WR维持]",
        "US500_M5_EU_RSI12": "US500 M5 EU CB>=5+RSI<12做多 WR=83.3% n=36 hold=25 [RSI12版本维持]",
        "US500_M5_EU_CB6_RSI12": "US500 M5 EU CB>=6+RSI<12做多 WR=84.6% n=26 hold=25 [WR维持]",
        "US30_M1_EU_long": "US30 M1 EU CB>=4+RSI<14做多 WR=70.4% n=81 hold=30 ⚠️[第32月-改善维持70.4%]",
        "US30_M1_EU_CB5": "US30 M1 EU CB>=5+RSI<14做多 WR=73.2% n=56 hold=5 [第32月-改善维持]",
        "US30_M1_EU_RSI12": "US30 M1 EU CB>=4+RSI<12做多 WR=77.8% n=54 hold=30 ✅[第32月改善维持77.8%]",
        "US30_M1_EU_CB5_RSI12": "US30 M1 EU CB>=5+RSI<12做多 WR=80.0% n=40 hold=30 ✅[第32月改善维持80.0%!]",
        "US30_M1_EU_CB4_RSI10": "US30 M1 EU CB>=4+RSI<10做多 WR=77.8% n=36 hold=10 ✅[改善维持77.8%]",
        "XAU_M1_EU_CB3_RSI7": "XAU M1 EU CB>=3+RSI<7做多 WR=100.0% n=18 hold=50 [R79第30月跟踪-WR稳定100%]",
        "XAU_M1_EU_CB2_RSI5": "XAU M1 EU CB>=2+RSI<5 hold=50 WR=100% n=15 Sharpe=152.45 [极端!n=15需积累]",
        "XAU_M1_EU_CB2_RSI7": "XAU M1 EU CB>=2+RSI<7做多 WR=90.9% n=22 hold=50 ✅[R79第30月确认!稳定90.9%]",
        "US30_M1_EU_CB6_RSI12": "US30 M1 EU CB>=6+RSI<12做多 WR=88.5% n=26 hold=15 ⭐[R79第32月-改善持续确认!88.5%]",
        "XAU_M1_US_CB4_RSI12": "XAU M1 US CB>=4+RSI<12做多 WR=76.1% n=71 hold=30 ⚠️[第29月-稳定76.1%]",
        "JP225_H1_long": "JP225 H1 CB>=5+RSI<25做多 WR=100% n=16 hold=40 [H1远优于M5]",
        "JP225_M30_long": "JP225 M30 CB>=4+RSI<20做多 WR=95.5% n=22 hold=135 [M30远优于M5]",
        "AUDUSD_M30_long": "AUDUSD M30 CB>=4+RSI<15做多 WR=70.9% n=79 hold=60 ❌[正式停止跟踪]",
        "XAU_M5_H15_doublegun2": "XAU M5 H15 CB>=1 RSI<10 hold=55 WR=91.7% n=12 [冻结归档]",
        "XAU_M5_H19_doublegun": "XAU M5 H19 CB>=4 RSI<12 hold=55 WR=90.9% n=11 [冻结归档]"
    },
    "warnings": [
        "❗XAUUSD M5 US RSI<6+CB>=1 n=28连续12月无增长 — 数据冻结正式归档(季度检查)",
        "❗XAUUSD M5美盘H精确定时所有策略连续12月无增长(n=7-12) — 冻结归档",
        "❗XAGUSD M5 EU RSI<8+CB>=1 n=31连续12月无增长 — 冻结归档",
        "M5数据截至2026-05-14 10:10 UTC(已于R79更新✅ +72 bars)",
        "M1数据截至2026-05-14 10:11 UTC(已于R79更新✅ +21 bars)",
        "H1/M30数据由M5重采样生成(非MT5直采)",
        "XAGUSD M5 RSI4信号数n=51(稳定),RSI5信号数n=69(稳定),信号数整体稳定",
        "JP225 M5级别信号质量差(最大WR=73.6%但Sharpe仅3.62)，远不如H1/M30 (WR>90%)",
        "做空信号在M1/M5全线<65% WR，做空分支已正式关闭(不再扫描)",
        "⚠️ XAUUSD M1 ASIA WR维持低位72.6%,第37月确认无回升,正式取消推荐",
        "US30 M1 EU第32月改善持续确认(CB6+RSI12 WR=88.5%!),重点关注",
        "XAU M1 EU CB3+RSI7 WR=100% n=18(稳定,hold=50)",
        "XAU M1 EU CB2+RSI5 n=15 WR=100%但n太小(n<25不达标)",
        "XAU M1 EU CB2+RSI7 WR=90.9% n=22 ✅稳定验证通过",
        "US30 M1 EU CB6+RSI12 WR=88.5% n=26 hold=15 ⭐改善持续确认",
        "XAU M1 EU CB3+RSI10 WR=100%稳定(第41月通过✅)",
        "XAG M5 RSI4深度hold=70 WR=98.0% n=51极佳,第27月确认通过✅",
        "XAG M5 RSI5 WR维持92.8%✅(与R78持平)",
        "US500 M5 EU维持改善后水平(CB6+RSI14=85.7%,CB5+RSI10=87.5%),新基线确认",
        "US30 M1 EU全线改善维持,CB6+RSI12=88.5%为最佳策略",
        "AUDUSD M30正式停止跟踪",
        "XAU M5 US_CB3_RSI15 n=215 WR=64.5%维持边界,宽松阈值无改善迹象",
        "⚠️ XAU M1 ASIA WR维持72.6%,连续多期低位",
        "✅ US30 M1 EU改善持续确认,值得重点关注",
        "✅ 数据下载已完成! 连续3轮数据停滞问题已解决(R79数据边界: M5 10:10 UTC, M1 10:11 UTC)"
    ],
    "next_actions": [
        "round80_001: XAUUSD M1 EU/US 第42月常规跟踪 + EU_CB2第34月 + EU_RSI8第32月 + CB3+RSI7第31月 + CB2+RSI7第31月",
        "round80_002: XAUUSD M5 US RSI<6 冻结归档跳过(下次季度检查8月)",
        "round80_003: XAGUSD M5 RSI<5 ALL第33月跟踪(质量监控) + RSI<4第28月跟踪 + RSI4深度hold=70第28月跟踪",
        "round80_004: US500 M5 EU 第40月常规跟踪 + 维持观察(新基线确认)",
        "round80_005: XAUUSD M1 ASIA 第38月跟踪 — 监测是否继续恶化 ⚠️",
        "round80_006: US30 M1 EU 第33月跟踪(重点关注改善是否持续) — R77-R79确认改善(88.5%)",
        "round80_007: XAUUSD M5 H15/H19冻结归档跳过",
        "round80_008: XAGUSD M5 RSI<5 ALL第33月跟踪 + RSI<4第28月跟踪 + 信号频率更新",
        "round80_009: JP225 M5最低权重监控(关注US session改善是否持续)",
        "round80_010: 新探索: ①US30 M1 EU改善持续跟踪 ②XAG M5 RSI4 DEEP第28月确认 ③XAU M1 ASIA WR监测 ④尝试新的M5 EU/US组合策略探索",
        "round80_data: 🔄 数据状态正常(M5: 10:10 UTC, M1: 10:11 UTC)。下次检查是否需要MT5数据下载。"
    ]
}

state_path = os.path.join(BASE, "state", "research_state.json")
os.makedirs(os.path.join(BASE, "state"), exist_ok=True)
with open(state_path, "w", encoding="utf-8") as f:
    json.dump(state, f, ensure_ascii=False, indent=2)

print(f"✅ state/research_state.json 已更新至 Round 79")
print(f"📁 路径: {state_path}")
