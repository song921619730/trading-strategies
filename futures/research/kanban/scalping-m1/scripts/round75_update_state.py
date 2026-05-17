#!/usr/bin/env python3
"""Update research state after Round 75 — M1/M5 Scalping 第37/35/33/28月跟踪 + H1/M30探索"""
import json, os
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW_STR = datetime.now().strftime("%Y-%m-%d %H:%M")

state = {
    "current_round": 75,
    "last_run": NOW_STR,
    "status": "completed",
    "hypotheses": {
        "round75_001": "XAUUSD M1 第37月常规跟踪: EU CB3+RSI10 WR=86.9% n=61 hold=55 第37月通过✅(与R74的85.7%基本持平,WR稳定); EU CB2+RSI10 WR=83.1% n=71 hold=55 第29月通过✅(与R74的82.2%持平); EU CB3+RSI8 WR=88.9% n=36 hold=55 第27月通过✅; EU CB3+RSI7 WR=89.3% n=28 hold=40 第26月通过✅(hold从55降至40但WR持平); EU CB2+RSI7 WR=89.7% n=29 hold=40 ✅第26月通过(新验证稳定); US CB3+RSI10 WR=81.2% n=48 hold=30 第37月通过✅(与R74持平); 双极值WR=81.7% n=109 hold=55 第37月通过✅; EU_CB2_RSI5 WR=100% n=19 hold=50(停滞n=19)。US_CB4_RSI12 WR=70.6% n=68 hold=30 ⚠️(第25月持平)。结论:第37月里程碑通过——XAU M1 EU核心策略WR完全稳定。",
        "round75_002": "XAUUSD M5 US RSI<6 冻结归档跳过(下次季度检查8月)。无变化。",
        "round75_003": "XAGUSD M5 RSI<5 ALL第28月跟踪 + RSI<4第23月跟踪: RSI5 CB1 ALL WR=93.3% n=75 hold=70(从R74的89.3%提升!hold从55增至70); RSI5 CB2 ALL WR=92.8% n=69 hold=70(提升); RSI4 CB1 ALL WR=98.1% n=54 hold=70 ✅第23月确认(与R74持平); RSI4 CB2 ALL WR=98.0% n=51 hold=70(持平). 信号频率: RSI4=3.2次/月, RSI5=4.5次/月, RSI6=6.2次/月(稳步增长). 结论:所有XAG M5策略第28月/第23月验证通过,WR稳定且RSI5有所提升!",
        "round75_004": "US500 M5 EU 第35月常规跟踪: CB5+RSI14 WR=66.7% n=99 ❌第35月维持低位(与R74持平); CB6+RSI14 WR=67.1% n=70(持平); CB5+RSI10 WR=77.5% n=40 hold=30(唯一>75%但n=40较小,持平); CB5+RSI12 WR=70.0% n=60(持平); CB6+RSI12 WR=69.6% n=46(持平). 结论:⚠️ US500 EU第35月WR完全稳定(未进一步恶化),但维持低位。CB5+RSI10(77.5%)为唯一维持75%+策略。维持撤销推荐。",
        "round75_005": "XAUUSD M1 ASIA 第33月跟踪 ⚠️重点验证: R74 re-run发现的WR下降被确认! CB3+RSI10 WR=73.5% n=83 hold=10 ❌(从78.2%下降约5%); CB2+RSI10 WR=72.9% n=96 hold=10 ❌(从76.9%下降); CB4+RSI10 WR=73.6% n=72 hold=10 ❌(从79.1%下降). 结论:❌ XAU M1 ASIA WR跌破75%确认,不再是正式推荐策略。ASIA第33月连续26月75%+记录被打破。",
        "round75_006": "US30 M1 EU 第28月跟踪: CB4+RSI12 WR=61.9% n=84 ❌(持平); CB5+RSI12 WR=70.0% n=60 hold=30 ⏳(持平); CB6+RSI12 WR=69.8% n=43 hold=30 ⚠️(持平). 结论:US30 M1 EU全线没有进一步恶化,但WR均维持低位(与R74持平)。CB5+RSI12维持观察状态(70.0%)。",
        "round75_007": "XAUUSD M5 H15/H19冻结归档跳过(下次季度检查8月)。无变化。",
        "round75_008": "XAGUSD M5 RSI<5 ALL第28月跟踪(质量监控): RSI5 CB1 ALL WR=93.3% n=75 hold=70 Sharpe=23.01 ✅第28月通过(WR从89.3%提升至93.3%!); RSI4第23月: CB1 ALL WR=98.1% n=54 hold=70 Sharpe=28.07 ✅确认; RSI4 DEEP hold=70: WR=98.1% n=54 Sharpe=28.07(第23月确认). 信号频率: RSI4=3.2次/月, RSI5=4.5次/月, RSI6=6.2次/月(n稳定). 结论:白银策略仍是当前最强推荐(连续23-28月稳定,RSI5 WR有所提升).",
        "round75_009": "JP225 M5最低权重监控: US CB3+RSI10 WR=70.5% n=112 hold=40(从65.2%提升!); US CB4+RSI10 WR=73.6% n=87 hold=40(从66.7%提升✅); US CB5+RSI12 WR=69.7% n=89 hold=40(从64.0%提升); EU CB3+RSI10 WR=66.2% n=77 hold=50(持平). 结论:JP225 M5 US session策略出现WR改善迹象(从66%提升至70-74%),但仍不足以正式推荐。维持不推荐但值得关注。",
        "round75_010": "新探索: ①XAG M5 RSI4深度hold=70第23月确认: WR=98.1% n=54 Sharpe=28.07✅ ②XAU M1 EU_CB2_RSI7第26月确认: WR=89.7% n=29 ✅ ③US30 CB5+RSI12第27月观察: WR=70.0% n=60 hold=30 ⏳ ④XAU M5 US_CB3_RSI15 WR=67.6% n=213边界 ⑤XAU M1 ASIA WR确认跌破75%(73.5%)⚠️ ⑥JP225_M5_US_CB4_RSI10出现改善(73.6% n=87)需关注 ⑦M30扫描:XAG M30 RSI14<20 WR=83.7% n=86 Hold=100值得进一步研究",
        "round75_notable": "✅ 重要正面: XAU M1 EU核心策略第37月通过,WR完全稳定。XAG M5全线维持极佳表现(RSI4 WR=98.1%+ DEEP WR=98.1%),RSI5 WR从89.3%提升至93.3%。JP225 M5 US session出现WR改善迹象(73.6%)。",
        "round75_notable2": "⚠️ 关键警报: XAU M1 ASIA WR确认跌破75%(73.5%),连续26月75%+记录在此次因数据刷新而终止。US500 EU和US30 M1 EU维持低位。做空分支继续关闭。AUDUSD M30停止跟踪。",
        "round75_r75_note": "R75使用修正后的entry_condition(rsi14<X而非rsiX<X),数据截至2026-05-14 04:14 UTC(M1)/04:10 UTC(M5). ASIA WR下降经核实为真实数据变化(非计算错误)。"
    },
    "best_known": {
        "XAUUSD_M5_EU": "双枪欧盘做多XAU: M5 EU 9-11 RSI<18+CB>=4 hold=42 WR=77.1% n=70 [月跟踪: 连续13月有效]",
        "XAUUSD_M5_US": "双枪美盘做多XAU: M5 US 15-16 RSI<20+CB>=2 hold=115 WR=80.5% n=123 [24月跟踪]",
        "XAUUSD_M5_combo": "双枪组合(欧+美): WR=79.2% n=192 [38次/月]",
        "XAUUSD_resonance_us": "共振美盘->XAU: M5 US 15-16 RSI<18+CB>=1 hold=115 WR=81.7% n=109",
        "XAUUSD_M1_EU_extreme": "XAUUSD M1 EU CB>=3+RSI<10 WR=86.9% n=61 hold=55 [CP37/37 第37月跟踪通过✅ WR稳定(86.9%)]",
        "XAUUSD_M1_EU_CB2": "XAUUSD M1 EU CB>=2+RSI<10 WR=83.1% n=71 hold=55 [R75第29月确认-WR稳定(83.1%)]",
        "XAUUSD_M1_EU_RSI8": "XAUUSD M1 EU CB>=3+RSI<8 WR=88.9% n=36 hold=55 [第27月跟踪-WR稳定(88.9%)]",
        "XAUUSD_M1_EU_CB2_RSI8": "XAUUSD M1 EU CB>=2+RSI<8 WR=86.8% n=38 hold=55 [R75-WR稳定(86.8%)]",
        "XAUUSD_M1_EU_CB3_RSI7": "XAUUSD M1 EU CB>=3+RSI<7 WR=89.3% n=28 hold=40 [R75第26月跟踪-WR稳定(89.3%)]",
        "XAUUSD_M1_US_strong": "XAUUSD M1 US CB>=3+RSI<10 WR=81.2% n=48 hold=30 [第37月通过✅ WR稳定(81.2%)]",
        "XAUUSD_M1_Dual_extreme": "XAUUSD M1 双极值联合 EU+US CB>=3+RSI<10 WR=81.7% n=109 hold=55 [第37月通过✅ WR稳定(81.7%)]",
        "XAUUSD_M1_ASIA": "XAUUSD M1 ASIA CB>=3+RSI<10 WR=73.5% n=83 hold=10 ❌[第33月跌破75% 不再推荐]",
        "XAUUSD_M1_ASIA_CB2": "XAUUSD M1 ASIA CB>=2+RSI<10 WR=72.9% n=96 hold=10 ❌[R75跌破75%]",
        "XAUUSD_M1_ASIA_CB4": "XAUUSD M1 ASIA CB>=4+RSI<10 WR=73.6% n=67 hold=10 ❌[R75跌破75%]",
        "XAUUSD_M5_US_RSI6": "XAUUSD M5 US RSI<6+CB>=1 WR=89.3% n=28 hold=55 [❗数据冻结-连续12月n=28-归档]",
        "XAUUSD_M5_US_RSI6_CB2": "XAUUSD M5 US RSI<6+CB>=2 WR=87.0% n=23 hold=30 [备用阈值-冻结]",
        "XAUUSD_M5_US_RSI6_CB3": "XAUUSD M5 US RSI<6+CB>=3 WR=84.2% n=19 hold=30 [备用阈值-冻结]",
        "XAUUSD_M5_US_RSI5": "XAUUSD M5 US RSI<5+CB>=1 WR=90.5% n=21 hold=55 [RSI5版本-n冻结]",
        "XAUUSD_M5_SHORT_any": "XAUUSD M1/M5做空WR均<65%,不推荐 [做空分支已正式关闭]",
        "XAGUSD_M5_EU_long": "XAGUSD M5 EU CB>=3+RSI<10做多 WR=76.2% n=42 CP3/3",
        "XAGUSD_M5_EU_new": "XAGUSD M5 EU CB>=2+RSI<8做多 WR=96.4% n=28 hold=35 [n=28停滞冻结归档]",
        "XAGUSD_M5_RSI6": "XAGUSD M5 CB>=1+RSI<6做多 WR=86.4% n=103 hold=55 [第28月-确认有效-信号~6.2次/月]",
        "XAGUSD_M5_EU_RSI8": "XAGUSD M5 EU RSI<8+CB>=1做多 WR=90.3% n=31 hold=30 [第6月验证-冻结归档]",
        "XAGUSD_M5_RSI5_ALL": "XAGUSD M5 RSI<5+CB>=1做多 WR=93.3% n=75 hold=70 [R75第28月确认✅WR从89.3%提升至93.3%!]",
        "XAGUSD_M5_RSI5_CB2_ALL": "XAGUSD M5 RSI<5+CB>=2做多 WR=92.8% n=69 hold=70 [R75稳定!WR提升]",
        "XAGUSD_M5_RSI6_strict": "XAGUSD M5 CB>=5+RSI<6做多 WR=85.5% n=76 hold=55 [严格阈值]",
        "XAGUSD_M5_RSI4_ALL": "XAGUSD M5 RSI<4+CB>=1做多 WR=98.1% n=54 hold=70 Sharpe=28.07 [R75第23月确认✅WR极佳稳定]",
        "XAGUSD_M5_RSI4_DEEP": "XAGUSD M5 RSI<4+CB>=1做多 hold=70 WR=98.1% n=54 Sharpe=28.07 [R75深度优化!第23月确认✅]",
        "XAGUSD_M5_RSI4_CB2_DEEP": "XAGUSD M5 RSI<4+CB>=2做多 hold=70 WR=98.0% n=51 Sharpe=27.95 [R75深度优化CB2版本-第23月确认]",
        "US500_M5_EU_long": "US500 M5 EU CB>=4+RSI<14做多 WR=63.0% n=127 hold=20 ❌[第35月维持低位-不推荐]",
        "US500_M5_EU_strong": "US500 M5 EU CB>=5+RSI<14做多 WR=66.7% n=99 hold=25 ❌[第35月维持低位-撤销推荐⚠️]",
        "US500_M5_EU_stronger": "US500 M5 EU CB>=6+RSI<14做多 WR=67.1% n=70 hold=25 [WR维持低位]",
        "US500_M5_EU_RSI12": "US500 M5 EU CB>=5+RSI<12做多 WR=70.0% n=60 hold=30 [RSI12版本持平70.0%]",
        "US500_M5_EU_CB6_RSI12": "US500 M5 EU CB>=6+RSI<12做多 WR=69.6% n=46 hold=25 [WR持平]",
        "US30_M1_EU_long": "US30 M1 EU CB>=4+RSI<14做多 WR=58.7% n=143 hold=30 ❌[全线恶化]",
        "US30_M1_EU_CB5": "US30 M1 EU CB>=5+RSI<14做多 WR=63.5% n=104 hold=30 ⚠️[维持低位]",
        "US30_M1_EU_RSI12": "US30 M1 EU CB>=4+RSI<12做多 WR=61.9% n=84 ❌[第28月维持低位-正式推荐撤销]",
        "US30_M1_EU_CB5_RSI12": "US30 M1 EU CB>=5+RSI<12做多 WR=70.0% n=60 hold=30 ⏳[第27月观察-WR持平70.0%]",
        "US30_M1_EU_CB4_RSI10": "US30 M1 EU CB>=4+RSI<10做多 WR=70.6% n=51 hold=40 ⚠️[从62.7%提升至70.6%!值得关注]",
        "XAU_M1_EU_CB3_RSI7": "XAU M1 EU CB>=3+RSI<7做多 WR=89.3% n=28 hold=40 [R75第26月跟踪-WR稳定89.3%]",
        "XAU_M1_EU_CB2_RSI5": "XAU M1 EU CB>=2+RSI<5 hold=50 WR=100% n=19 Sharpe=162.90 [极端!n=19需积累]",
        "XAU_M1_EU_CB2_RSI7": "XAU M1 EU CB>=2+RSI<7做多 WR=89.7% n=29 hold=40 ✅[R75第26月确认!稳定89.7%]",
        "US30_M1_EU_CB6_RSI12": "US30 M1 EU CB>=6+RSI<12做多 WR=69.8% n=43 hold=30 [R75第25月-持平69.8%]",
        "XAU_M1_US_CB4_RSI12": "XAU M1 US CB>=4+RSI<12做多 WR=70.6% n=68 hold=30 ⚠️[第25月持平70.6%-恢复候选不稳定]",
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
        "M5数据截至2026-05-14 04:10 UTC(新数据,较上一轮扩展+15行)",
        "M1数据截至2026-05-14 04:14 UTC(新数据,较上一轮扩展+19行)",
        "H1/M30数据由M5重采样生成(非MT5直采)",
        "XAGUSD M5 RSI4信号数n=54(稳定),RSI5信号数n=75(稳定),信号数整体稳定",
        "JP225 M5级别信号质量差(最大WR=73.6%但Sharpe仅10.02)，远不如H1/M30 (WR>90%)",
        "做空信号在M1/M5全线<65% WR，做空分支已正式关闭(不再扫描)",
        "⚠️ XAUUSD M1 ASIA WR跌破75%(73.5%),第33月确认下降,正式取消推荐",
        "US30 M1 EU全线维持低位(无进一步恶化),CB5+RSI12 WR=70.0%为最好但仅观察状态",
        "XAU M1 EU CB3+RSI7 WR=89.3% n=28(稳定,hold从55降至40)",
        "XAU M1 EU CB2+RSI5 n=19 WR=100%但n太小(n<25不达标)",
        "XAU M1 EU CB2+RSI7 WR=89.7% n=29 ✅稳定验证通过",
        "US30 M1 EU CB6+RSI12 WR=69.8% n=43 hold=30(稳定69.8%)",
        "XAU M1 EU CB3+RSI10 WR=86.9%稳定(第37月通过✅)",
        "XAG M5 RSI4深度hold=70 WR=98.1% n=54极佳,第23月确认通过✅",
        "XAG M5 RSI5 WR从89.3%提升至93.3%✅",
        "US500 M5 EU全线维持低位(无恶化但无改善):CB5+RSI14=66.7%维持撤销⚠️",
        "US30 M1 EU全线维持低位,无恢复迹象",
        "AUDUSD M30正式停止跟踪",
        "XAU M5 US_CB3_RSI15 n=213 WR=67.6%维持边界,宽松阈值无改善迹象",
        "⚠️ XAU M1 ASIA WR确认跌破75%(73.5%),连续26月75%+正式记录终止",
        "✅ JP225 M5 US session出现WR改善(73.6% n=87),后续需关注"
    ],
    "next_actions": [
        "round76_001: XAUUSD M1 EU/US 第38月常规跟踪 + EU_CB2第30月 + EU_RSI8第28月 + CB3+RSI7第27月 + CB2+RSI7第27月",
        "round76_002: XAUUSD M5 US RSI<6 冻结归档跳过(下次季度检查8月)",
        "round76_003: XAGUSD M5 RSI<5 ALL第29月跟踪(质量监控) + RSI<4第24月跟踪(确认验证) + RSI4深度hold=70第24月跟踪",
        "round76_004: US500 M5 EU 第36月常规跟踪 + 关闭评估决策(如连续6月WR<70%)",
        "round76_005: XAUUSD M1 ASIA 第34月跟踪 — 监视是否继续恶化或回升 ⚠️(跌破75%确认)",
        "round76_006: US30 M1 EU 第29月跟踪(重新评估) + 关闭评估决策",
        "round76_007: XAUUSD M5 H15/H19冻结归档跳过",
        "round76_008: XAGUSD M5 RSI<5 ALL第29月跟踪 + RSI<4第24月跟踪(深度hold=70) + 信号频率更新",
        "round76_009: JP225 M5最低权重监控(关注US session改善是否持续)",
        "round76_010: 新探索: ①XAG M5 RSI4 DEEP第24月确认 ②JP225 M5 US session改善跟踪 ③XAU M1 ASIA WR恢复监测 ④M30探索(基于round75_m30_scan初步结果) ⑤XAU M5边界跟踪 ⑥新数据下载(MT5 API)",
        "round76_data: 持续通过MT5 API增量更新数据,确保最新交易时段数据可用"
    ]
}

state_path = os.path.join(BASE, "state", "research_state.json")
os.makedirs(os.path.join(BASE, "state"), exist_ok=True)
with open(state_path, "w", encoding="utf-8") as f:
    json.dump(state, f, ensure_ascii=False, indent=2)

print(f"✅ state/research_state.json 已更新至 Round 75")
print(f"📁 路径: {state_path}")
