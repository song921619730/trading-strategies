#!/usr/bin/env python3
"""Update research state after round73 — M1/M5 Scalping 第35/33/31月跟踪 + 第27/26/25/24/23月验证"""
import json, os
from datetime import datetime

BASE = '/mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/scalping-m1'

# ── 研究运行日志 ──
RUN_LOG_FILE = os.path.join(BASE, "logs", "research_run.log")
RUN_LOG_MAX = 10 * 1024 * 1024
os.makedirs(os.path.join(BASE, "logs"), exist_ok=True)
try:
    if os.path.exists(RUN_LOG_FILE) and os.path.getsize(RUN_LOG_FILE) > RUN_LOG_MAX:
        os.rename(RUN_LOG_FILE, RUN_LOG_FILE + ".1")
    with open(RUN_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().isoformat()}] Round 73 update_state 开始\n")
except Exception:
    pass

state = {
    "current_round": 73,
    "last_run": datetime.now().strftime("%Y-%m-%d %H:%M"),
    "status": "completed",
    "hypotheses": {
        "round73_001": "XAUUSD M1 第35月常规跟踪: EU CB3+RSI10 WR=85.7% n=63 hold=55 第35月通过✅(WR从97.2%回落至85.7%,n从36增至63); EU CB2+RSI10 WR=82.2% n=73 hold=55 第27月通过✅(WR从93.2%回落至82.2%); EU CB3+RSI8 WR=89.2% n=37 hold=55(第25月跟踪WR从100%降至89.2%但n增长); US CB3+RSI10 WR=81.2% n=48 hold=30 第35月通过✅(WR从85.4%回落至81.2%); 双极值WR=81.1% n=111 hold=55 第35月通过✅(WR从85.7%回落至81.1%). EU_RSI7第24月: CB3+RSI7 WR=89.7% n=29(从100%回落但n增长); EU_CB2_RSI5 WR=100% n=19(停滞). XAU M1 US CB4+RSI12 WR=70.6% n=68 hold=30 ⚠️从76.4%下降至70.6%,恢复候选状态不稳。结论:数据更新后所有XAU M1 EU策略WR出现系统回落但n均增长,M1核心策略仍通过第35月里程碑,但需关注下降趋势是否持续。数据差异注意:MT5增量更新后数据范围变化(R72→R73出现系统WR差异,疑似数据快照不同)。",
        "round73_002": "XAUUSD M5 US RSI<6 冻结归档跳过(下次季度检查8月)。无变化。",
        "round73_003": "XAGUSD M5 RSI<5 ALL第26月跟踪 + RSI4第21月跟踪: RSI5 CB1 ALL WR=89.3% n=75 ✅第26月质量监控通过(n从69增至75); RSI5 CB2 ALL WR=88.4% n=69(↑从59); RSI4 CB1 ALL WR=94.4% n=54 ✅第21月确认(n从51增至54); RSI4 CB2 ALL WR=94.1% n=51。结论:所有XAG M5策略通过第26月/第21月验证,n全面增长,信号健康。",
        "round73_004": "US500 M5 EU 第33月常规跟踪: CB5+RSI14 WR=66.7% n=99 ❌从84.6%显著下降,连续33月稳定记录在第33月出现严重恶化; CB6+RSI14 WR=67.1% n=70; CB5+RSI10 WR=77.5% n=40 hold=30(唯一>75%但n=40较小); CB5+RSI12 WR=70.0% n=60; CB6+RSI12 WR=69.6% n=46。结论:⚠️⚠️ US500 EU核心策略第33月WR系统下降,CB5+RSI14从84.6%降至66.7%,推荐需正式撤销。US500 EU策略出现严重老化趋势。",
        "round73_005": "XAUUSD M1 ASIA 第31月跟踪: CB3+RSI10 WR=78.2% n=78(↑从66) hold=10 ✅; CB2+RSI10 WR=76.9% n=91(↑从77) hold=10 ✅; CB4+RSI10 WR=79.1% n=67(↑从52) hold=10 ✅。结论:ASIA第31月通过验证,WR维持75%+,n全面增长,但hold=10偏短问题持续。",
        "round73_006": "US30 M1 EU 第26月跟踪综合: CB4+RSI12 WR=61.9% n=84 ❌第26月从77.8%显著下降,正式推荐撤销; CB5+RSI12 WR=70.0% n=60 hold=30 ⏳第25月从80.0%下降至观察级别; CB6+RSI12 WR=69.8% n=43 hold=30 ⚠️第23月从88.5%下降但hold改善至30。结论:US30 M1 EU全线恶化,所有策略WR均下降,CB4+RSI12正式推荐撤销,CB5+RSI12降至观察状态。",
        "round73_007": "XAUUSD M5 H15/H19冻结归档跳过(下次季度检查8月)。无变化。",
        "round73_008": "XAGUSD M5 RSI<5 ALL第26月跟踪(质量监控): RSI5 CB1 ALL WR=89.3% n=75 hold=55 Sharpe=20.69 ✅第26月通过(n↑). RSI4第21月: CB1 ALL WR=94.4% n=54 hold=55 Sharpe=25.64 ✅确认(n↑). 深度测试RSI4 CB1 DEEP hold=70: WR=98.1% n=54 Sharpe=28.07(第21月确认,表现维持). 信号频率: RSI4=3.2次/月, RSI5=4.4次/月, RSI6=6.1次/月(n全面增长). 结论:正式推荐后第26月质量监控通过,白银策略为当前最强推荐。",
        "round73_009": "JP225 M5 最低权重监控: US CB3+RSI10 WR=65.2% n=112 hold=15(边界); US CB4+RSI10 WR=66.7% n=87 hold=45; US CB5+RSI12 WR=64.0% n=89; EU CB3+RSI10 WR=66.2% n=77 hold=45(↑从55.6% n=54 WR改善但持续性待验证). 结论:维持不推荐。",
        "round73_010": "新探索: ①XAG M5 RSI4深度hold=70第21月确认: WR=98.1% n=54 Sharpe=28.07(第21月确认,连续21轮维持极佳表现) ②US30 CB6+RSI12 hold稳定性第23月: WR=69.8% n=43 hold=30(从88.5% WR下降但hold从15改善至30) ③XAU M5边界: US_CB3_RSI15 WR=63.4% n=213(维持边界); US_CB4_RSI12 WR=63.0% n=100; EU全部<53% ❌ ④AUDUSD M30参数调优: CB4+RSI15 WR=70.9% n=79 hold=60 Sharpe=1.61(WR从76.5%下降至70.9%,Sharpe低); CB3+RSI15 WR=70.3% n=111 hold=60 Sharpe=2.42。结论:AUDUSD M30 CB4+RSI15 WR首次跌破75%(70.9%),连续17轮突破75%记录中止,不推荐。⑤XAU M1 ASIA深度hold测试: hold=10为最佳(78.2%),hold>10后WR下降,hold偏短问题持续。⑥数据源: M1截止5/14 01:47 UTC(新数据+85行),M5截止5/14 01:45 UTC(新数据+17行)。",
        "round73_notable": "⚠️ 重要: R73数据经MT5增量更新(+85 M1行,+17 M5行),所有策略n值普遍增长但WR系统下降。XAU M1 EU核心WR下降(97.2%→85.7%)但n增长(36→63),可能是数据快照刷新带来的统计变化。US500 EU核心策略第33月出现严重WR下降(84.6%→66.7%),建议正式撤销推荐。US30 M1 EU全线恶化。",
        "round73_notable2": "XAG M5为当前最强板块: RSI4 CB1 DEEP hold=70 WR=98.1% n=54连续21月极佳表现; RSI5 CB1 ALL WR=89.3% n=75第26月通过。白银策略全线稳定。",
        "round73_bugfix": "继续使用修复后的grid_engine.py(DST重复索引修正)。R73数据经过增量更新(MT5 Windows Python),数据覆盖至5/14 01:47 UTC。"
    },
    "best_known": {
        "XAUUSD_M5_EU": "双枪欧盘做多XAU: M5 EU 9-11 RSI<18+CB>=4 hold=42 WR=77.1% n=70 [月跟踪: 连续13月有效]",
        "XAUUSD_M5_US": "双枪美盘做多XAU: M5 US 15-16 RSI<20+CB>=2 hold=115 WR=80.5% n=123 [24月跟踪]",
        "XAUUSD_M5_combo": "双枪组合(欧+美): WR=79.2% n=192 [38次/月]",
        "XAUUSD_resonance_us": "共振美盘->XAU: M5 US 15-16 RSI<18+CB>=1 hold=115 WR=81.7% n=109",
        "XAUUSD_M1_EU_extreme": "XAUUSD M1 EU CB>=3+RSI<10 WR=85.7% n=63 hold=55 [CP35/35 第35月跟踪通过✅ WR从97.2%回落至85.7%但n增长]",
        "XAUUSD_M1_EU_CB2": "XAUUSD M1 EU CB>=2+RSI<10 WR=82.2% n=73 hold=55 [R73第27月确认-WR从93.2%回落至82.2%但n从44增至73]",
        "XAUUSD_M1_EU_RSI8": "XAUUSD M1 EU CB>=3+RSI<8 WR=89.2% n=37 hold=55 [第25月跟踪-WR从100%降至89.2%但n从25增至37]",
        "XAUUSD_M1_EU_CB2_RSI8": "XAUUSD M1 EU CB>=2+RSI<8 WR=87.2% n=39 hold=55 [R73-从93.1%降至87.2%但n从29增至39]",
        "XAUUSD_M1_EU_CB3_RSI7": "XAUUSD M1 EU CB>=3+RSI<7 WR=89.7% n=29 hold=55 [R73第24月跟踪-WR从100%降至89.7%但n从19增至29]",
        "XAUUSD_M1_US_strong": "XAUUSD M1 US CB>=3+RSI<10 WR=81.2% n=48 hold=30 [第35月通过✅ WR从85.4%回落至81.2%,n=48维持]",
        "XAUUSD_M1_Dual_extreme": "XAUUSD M1 双极值联合 EU+US CB>=3+RSI<10 WR=81.1% n=111 hold=55 [第35月通过✅ WR从85.7%回落至81.1%但n从84增至111]",
        "XAUUSD_M1_ASIA": "XAUUSD M1 ASIA CB>=3+RSI<10 WR=78.2% n=78 hold=10 [第31月确认稳定 WR维持75%+✅ n增长]",
        "XAUUSD_M1_ASIA_CB2": "XAUUSD M1 ASIA CB>=2+RSI<10 WR=76.9% n=91 hold=10 [R73 WR维持75%+✅ n增长]",
        "XAUUSD_M1_ASIA_CB4": "XAUUSD M1 ASIA CB>=4+RSI<10 WR=79.1% n=67 hold=10 [R73 WR维持75%+✅ n增长]",
        "XAUUSD_M5_US_RSI6": "XAUUSD M5 US RSI<6+CB>=1 WR=89.3% n=28 hold=55 [❗数据冻结-连续12月n=28-归档]",
        "XAUUSD_M5_US_RSI6_CB2": "XAUUSD M5 US RSI<6+CB>=2 WR=87.0% n=23 hold=30 [备用阈值-冻结]",
        "XAUUSD_M5_US_RSI6_CB3": "XAUUSD M5 US RSI<6+CB>=3 WR=84.2% n=19 hold=30 [备用阈值-冻结]",
        "XAUUSD_M5_US_RSI5": "XAUUSD M5 US RSI<5+CB>=1 WR=90.5% n=21 hold=55 [RSI5版本-n冻结]",
        "XAUUSD_M5_SHORT_any": "XAUUSD M1/M5做空WR均<65%,不推荐 [做空分支已正式关闭]",
        "XAGUSD_M5_EU_long": "XAGUSD M5 EU CB>=3+RSI<10做多 WR=76.2% n=42 CP3/3",
        "XAGUSD_M5_EU_new": "XAGUSD M5 EU CB>=2+RSI<8做多 WR=96.4% n=28 hold=35 [n=28停滞冻结归档]",
        "XAGUSD_M5_RSI6": "XAGUSD M5 CB>=1+RSI<6做多 WR=86.4% n=103 hold=55 [第26月-确认有效-信号~6.1次/月]",
        "XAGUSD_M5_EU_RSI8": "XAGUSD M5 EU RSI<8+CB>=1做多 WR=90.3% n=31 hold=30 [第6月验证-冻结归档]",
        "XAGUSD_M5_RSI5_ALL": "XAGUSD M5 RSI<5+CB>=1做多 WR=89.3% n=75 hold=55 [R73第26月确认-正式推荐稳定✅n增长]",
        "XAGUSD_M5_RSI5_CB2_ALL": "XAGUSD M5 RSI<5+CB>=2做多 WR=88.4% n=69 hold=55 [R73稳定!CB2版本推荐]",
        "XAGUSD_M5_RSI6_strict": "XAGUSD M5 CB>=5+RSI<6做多 WR=85.5% n=76 hold=55 [严格阈值]",
        "XAGUSD_M5_RSI4_ALL": "XAGUSD M5 RSI<4+CB>=1做多 WR=94.4% n=54 hold=55 Sharpe=25.64 [R73第21月确认!候选正式纳入✅]",
        "XAGUSD_M5_RSI4_DEEP": "XAGUSD M5 RSI<4+CB>=1做多 hold=70 WR=98.1% n=54 Sharpe=28.07 [R73深度优化!WR极高hold=70极佳-第21月确认✅]",
        "XAGUSD_M5_RSI4_CB2_DEEP": "XAGUSD M5 RSI<4+CB>=2做多 hold=70 WR=98.0% n=51 Sharpe=27.95 [R73深度优化CB2版本-第21月确认]",
        "US500_M5_EU_long": "US500 M5 EU CB>=4+RSI<14做多 WR=63.0% n=127 hold=20 ❌[第33月显著下降-不推荐]",
        "US500_M5_EU_strong": "US500 M5 EU CB>=5+RSI<14做多 WR=66.7% n=99 hold=25 ❌[第33月从84.6%显著下降-推荐撤销⚠️]",
        "US500_M5_EU_stronger": "US500 M5 EU CB>=6+RSI<14做多 WR=67.1% n=70 hold=25 [WR显著下降]",
        "US500_M5_EU_RSI12": "US500 M5 EU CB>=5+RSI<12做多 WR=70.0% n=60 hold=30 [RSI12版本从83.3%下降至70.0%]",
        "US500_M5_EU_CB6_RSI12": "US500 M5 EU CB>=6+RSI<12做多 WR=69.6% n=46 hold=25 [WR从84.6%下降至69.6%]",
        "US30_M1_EU_long": "US30 M1 EU CB>=4+RSI<14做多 WR=55.9% n=143 hold=30 ❌[全线恶化]",
        "US30_M1_EU_CB5": "US30 M1 EU CB>=5+RSI<14做多 WR=63.5% n=104 hold=30 ⚠️[从73.2%下降]",
        "US30_M1_EU_RSI12": "US30 M1 EU CB>=4+RSI<12做多 WR=61.9% n=84 ❌[第26月从77.8%显著下降-正式推荐撤销]",
        "US30_M1_EU_CB5_RSI12": "US30 M1 EU CB>=5+RSI<12做多 WR=70.0% n=60 hold=30 ⏳[第25月从80.0%下降至观察级别]",
        "US30_M1_EU_CB4_RSI10": "US30 M1 EU CB>=4+RSI<10做多 WR=62.7% n=51 ❌[从77.8%下降]",
        "XAU_M1_EU_CB3_RSI7": "XAU M1 EU CB>=3+RSI<7做多 WR=89.7% n=29 hold=55 [R73第24月跟踪-从100%降至89.7%但n从19增至29]",
        "XAU_M1_EU_CB2_RSI5": "XAU M1 EU CB>=2+RSI<5 hold=55 WR=100% n=19 Sharpe=149.43 [极端!n=19需积累]",
        "US30_M1_EU_CB6_RSI12": "US30 M1 EU CB>=6+RSI<12做多 WR=69.8% n=43 hold=30 [R73第23月-从88.5%下降但hold从15改善至30]",
        "XAU_M1_US_CB4_RSI12": "XAU M1 US CB>=4+RSI<12做多 WR=70.6% n=68 hold=30 ❌[第23月从76.4%下降-恢复候选不稳]",
        "JP225_H1_long": "JP225 H1 CB>=5+RSI<25做多 WR=100% n=16 hold=40 [H1远优于M5]",
        "JP225_M30_long": "JP225 M30 CB>=4+RSI<20做多 WR=95.5% n=22 hold=135 [M30远优于M5]",
        "AUDUSD_M30_long": "AUDUSD M30 CB>=4+RSI<15做多 WR=70.9% n=79 hold=60 Sharpe=1.61 ❌[R73首次跌破75%(70.9%),连续17轮75%+记录中止]",
        "AUDUSD_M30_CB2_long": "AUDUSD M30 CB>=2+RSI<18做多 WR=66.3% n=267 hold=60 [基线参考]",
        "AUDUSD_M30_CB3_RSI15": "AUDUSD M30 CB>=3+RSI<15做多 WR=70.3% n=111 hold=60 [R73从72.0%降至70.3%]",
        "XAU_M5_H15_doublegun2": "XAU M5 H15 CB>=1 RSI<10 hold=55 WR=91.7% n=12 [美盘开盘精确定时-冻结归档]",
        "XAU_M5_H19_doublegun": "XAU M5 H19 CB>=4 RSI<12 hold=55 WR=90.9% n=11 [美盘盘中精确定时-冻结归档]"
    },
    "warnings": [
        "❗XAUUSD M5 US RSI<6+CB>=1 n=28连续12月无增长 — 数据冻结正式归档(季度检查)",
        "❗XAUUSD M5美盘H精确定时所有策略连续12月无增长(n=7-12) — 冻结归档",
        "❗XAGUSD M5 EU RSI<8+CB>=1 n=31连续12月无增长 — 冻结归档",
        "M5数据截至2026-05-14 01:45 UTC(新数据,较上一轮更新+17行)",
        "M1数据截至2026-05-14 01:47 UTC(新数据,较上一轮更新+85行)",
        "H1/M30数据由M5重采样生成(非MT5直采),覆盖2024-12至2026-05-13 20:00",
        "XAGUSD M5 RSI4信号数n=54(↑从51),RSI5信号数n=75(↑从69),信号数整体增长",
        "JP225 M5级别信号质量差(最大WR=66.7%但Sharpe仅5.79)，远不如H1/M30 (WR>90%)",
        "做空信号在M1/M5全线<65% WR，做空分支已正式关闭(不再扫描)",
        "XAUUSD M1 ASIA所有版本WR维持75%+但hold=10较短,大hold无信号(极值不够深)",
        "US30 M1 EU CB5+RSI14 WR=63.5% n=104但hold=30,全线恶化",
        "XAU M1 EU CB3+RSI7 WR=89.7% n=29(从100%下降但n从19增至29),接近n≥25验证通过",
        "XAU M1 EU CB2+RSI5 n=19 WR=100%但n太小,距离验证门槛(n≥25)还有距离",
        "US30 M1 EU CB6+RSI12 WR=69.8% n=43 hold=30(从88.5%下降至69.8%,hold从15改善至30)",
        "XAU M1 EU CB3+RSI10 WR从97.2%降至85.7%(第35月下降趋势),n从36增至63",
        "XAG M5 RSI4深度hold=70 WR=98.1% n=54极佳,第21月确认通过✅",
        "US500 M5 EU全线老化:CB5+RSI14从84.6%降至66.7%(第33月),推荐撤销⚠️",
        "US30 M1 EU全线恶化:CB4+RSI12从77.8%降至61.9%,CB5+RSI12从80.0%降至70.0%,均撤销推荐",
        "AUDUSD M30 CB4+RSI15 WR=70.9%(首次跌破75%,连续17轮记录中止),不能正式推荐",
        "XAU M5 US_CB3_RSI15 n=213 WR=63.4%维持边界,宽松阈值无改善迹象",
        "⚠️ R73数据经过MT5增量更新,与R72数据快照不同,导致系统WR差异。XAU M1 EU核心WR从97.2%降至85.7%与此相关。",
        "⚠️ 需持续关注US500 M5 EU和US30 M1 EU策略老化趋势是否继续恶化"
    ],
    "next_actions": [
        "round74_001: XAUUSD M1 EU/US 第36月常规跟踪 + EU_CB2第28月 + EU_RSI8第26月 + CB3+RSI7第25月 + US_CB4_RSI12第24月跟踪(关注WR下降趋势是否稳定)",
        "round74_002: XAUUSD M5 US RSI<6 冻结归档跳过(下次季度检查8月)",
        "round74_003: XAGUSD M5 RSI<5 ALL第27月跟踪(质量监控) + RSI<4第22月跟踪(确认验证) + RSI4深度hold=70第22月跟踪",
        "round74_004: US500 M5 EU 第34月常规跟踪(关注WR下降是否继续恶化,如再降则正式关闭) + 寻找新EU替代策略",
        "round74_005: XAUUSD M1 ASIA 第32月跟踪(WR维持75%+确认)",
        "round74_006: US30 M1 EU 第27月跟踪(重新评估-CB5+RSI12第26月继续观察) + 寻找替代策略",
        "round74_007: XAUUSD M5 H15/H19冻结归档跳过",
        "round74_008: XAGUSD M5 RSI<5 ALL第27月跟踪 + RSI<4第22月跟踪(深度hold=70) + 信号频率更新",
        "round74_009: JP225 M5最低权重监控(维持边界)",
        "round74_010: 新探索: ①XAG M5 RSI4深度hold=70第22月确认 ②US30 CB5+RSI12持续观察(第26月) ③XAU M5 US_CB3_RSI15边界跟踪 ④AUDUSD M30停止跟踪(WR跌破75%) ⑤XAU M1 ASIA WR维持75%+ ⑥新数据自动下载(MT5 API)",
        "round74_data: 持续通过MT5 API增量更新数据,确保最新交易时段数据可用"
    ]
}

fp = os.path.join(BASE, 'state', 'research_state.json')
os.makedirs(os.path.dirname(fp), exist_ok=True)
with open(fp, 'w', encoding='utf-8') as f:
    json.dump(state, f, ensure_ascii=False, indent=2)
print(f"✅ State updated: round {state['current_round']}")
try:
    with open(RUN_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().isoformat()}] Round {state['current_round']} update_state 完成 ✅\n")
except Exception:
    pass
