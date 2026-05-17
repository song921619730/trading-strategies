#!/usr/bin/env python3
"""Update research state after round37"""
import json, os
from datetime import datetime

BASE = '/mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/scalping-m1'

state = {
    "current_round": 37,
    "last_run": datetime.now().strftime("%Y-%m-%d %H:%M"),
    "status": "completed",
    "hypotheses": {
        "round37_001": "JP225 H1/M30做多正式纳入+月度跟踪 — H1 CB>=4+RSI<20 WR=94.7% n=19 hold=50 跨周期3/3✅; M30 CB>=4+RSI<20 WR=95.5% n=22 跨周期3/3✅; 月度跟踪启动: n=25 WR=92.0% 连续稳定。结论:✅ JP225正式纳入best_known",
        "round37_002": "UKOIL M30做多积累 n=32→目标50 — CB>=4+RSI<25 WR=96.9% n=32 hold=140 跨周期3/3✅; CB>=4+RSI<20 WR=100% n=23 hold=60 跨周期3/3✅; USOIL CB>=4+RSI<25 WR=79.5% n=39。结论:✅ UKOIL极强(推荐候补)，USOIL接近目标40",
        "round37_003": "XAUUSD M1 EU CB>=3+RSI<10跨周期再确认 — WR=97.2% n=36 hold=55 CI=[91.7%,100%] 跨周期3/3✅; CB>=4+RSI<14 WR=79.5% n=83跨周期3/3✅。结论:🏆 XAUUSD M1极值信号确认纳入best_known",
        "round37_004": "EURUSD H1做多月度跟踪第5月 — CB>=3+RSI<20 WR=100% n=11 hold=60 跨周期3/3✅; CB>=3+RSI<25 WR=82.1% n=28 月度跟踪: 2026-02/03/04/05稳定83.3%。结论:✅ 连续5月有效",
        "round37_005": "XAGUSD M30 SHORT积累 n=28→目标50 — CBull>=4+RSI>80 WR=78.6% n=28 hold=100 跨周期3/3✅; CBull>=5+RSI>80 WR=82.4% n=17。结论:✅ n=28不变(需更多数据)，跨周期稳健",
        "round37_006": "XAGUSD M5/M1 EU做多策略验证 — M5 CB>=3+RSI<10 WR=76.2% n=42 跨周期3/3✅; M1 CB>=3+RSI<10 WR=82.8% n=29 跨周期2/3⚠️; M5 CB>=4+RSI<14 WR=74.3% n=70 跨周期3/3✅。结论:✅ XAGUSD M5 EU做多稳定(纳入候补)，M1继续积累",
        "round37_007": "US500 M5 EU CB>=4+RSI<14做多验证 — WR=78.1% n=73 hold=25 CI=[69.9%,86.3%] 跨周期2/3⚠️(P3 WR=59.1%)。结论:🧪 n>70但P3略低于60%，需下轮再确认",
        "round37_008": "M1/M5超短线新品种策略挖掘 — XAUUSD M1 US CB>=2+RSI<10 WR=82.8% n=58(新发现🏆); US30 M1 EU CB>=3+RSI<10 WR=71.7% n=46; US30 M1 EU CB>=4+RSI<14 WR=70.4% n=81。结论:🧪 XAUUSD M1美盘极值值得深入"
    },
    "best_known": {
        "XAUUSD_M5_EU": "双枪欧盘做多XAU: M5 EU 9-11 RSI<18+CB>=4 hold=42 WR=77.1% n=70 [月度跟踪: 连续8月有效]",
        "XAUUSD_M5_US": "双枪美盘做多XAU: M5 US 15-16 RSI<20+CB>=2 hold=115 WR=80.3% n=122 [18月跟踪]",
        "XAUUSD_M5_combo": "双枪组合(欧+美): WR=79.2% n=192 [38次/月]",
        "XAUUSD_resonance_us": "共振美盘→XAU: M5 US 15-16 RSI<18+CB>=1 hold=115 WR=81.7% n=109",
        "XAUUSD_M1_EU_extreme": "🏆 XAUUSD M1 EU CB>=3+RSI<10 WR=97.2% n=36 hold=55 [跨周期3/3✅ 已确认纳入]",
        "XAUUSD_M1_US_extreme": "🆕 XAUUSD M1 US CB>=2+RSI<10 WR=82.8% n=58 hold=30 [新发现-美盘极值]",
        "USDJPY_H1_long": "✅ USDJPY H1 CB>=5+RSI<25做多 WR=100% n=17 hold=190 [月度跟踪100%✅]",
        "EURUSD_H1_long": "✅ EURUSD H1 CB>=3+RSI<20做多 WR=100% n=11 hold=60 CI=[100%,100%] 跨周期3/3✅",
        "EURUSD_H1_long_safe": "✅ EURUSD H1 CB>=3+RSI<25做多 WR=82.1% n=28 hold=60 CI=[67.9%,96.4%] 跨周期3/3✅ 月度跟踪5月稳定83.3%",
        "EURUSD_M30_long": "✅ EURUSD M30 CB>=3+RSI<20做多 WR=76.9% n=39 hold=70 CI=[64.1%,89.7%] 跨周期3/3✅",
        "XAGUSD_M30_SHORT": "✅ XAGUSD M30 SHORT CBull>=4+RSI>80 WR=78.6% n=28 hold=100 CI=[64.3%,92.9%] 跨周期3/3✅",
        "XAGUSD_M30_SHORT_us": "XAGUSD M30 SHORT CBull>=4+RSI>80+us WR=85.7% n=14 hold=35",
        "XAGUSD_M5_EU_long": "🆕 XAGUSD M5 EU CB>=3+RSI<10 WR=76.2% n=42 跨周期3/3✅ [推荐候补]",
        "XAGUSD_M5_EU_long_safe": "🆕 XAGUSD M5 EU CB>=4+RSI<14 WR=74.3% n=70 跨周期3/3✅",
        "JP225_H1_long": "✅ JP225 H1 CB>=5+RSI<25做多 WR=100% n=16 hold=40 跨周期3/3✅ [正式纳入]",
        "JP225_H1_long_safe": "✅ JP225 H1 CB>=4+RSI<25做多 WR=92.3% n=26 hold=40 跨周期3/3✅",
        "JP225_M30_long": "✅ JP225 M30 CB>=4+RSI<20做多 WR=95.5% n=22 hold=135 跨周期3/3✅ [正式纳入]",
        "JP225_M30_long_safe": "✅ JP225 M30 CB>=3+RSI<20做多 WR=94.3% n=35 hold=135 跨周期3/3✅",
        "UKOIL_M30_long": "🆕 UKOIL M30 CB>=4+RSI<25做多 WR=96.9% n=32 hold=140 跨周期3/3✅ [推荐候补]",
        "UKOIL_M30_long_strong": "🆕 UKOIL M30 CB>=4+RSI<20做多 WR=100% n=23 hold=60 跨周期3/3✅",
        "USOIL_M30_inside_long": "🆕 USOIL M30 InsideBar+RSI<20做多 WR=100% n=15 hold=80",
        "USOIL_M30_long": "USOIL M30 CB>=4+RSI<25做多 WR=79.5% n=39 hold=110 跨周期3/3✅",
        "XAUUSD_M30_Doji_short": "🧪 XAUUSD M30 Doji+RSI>75+us做空 WR=100% n=12 hold=35 [n=12无增长]",
        "US500_M5_EU_long": "🆕 US500 M5 EU CB>=4+RSI<14做多 WR=78.1% n=73 hold=25 [跨周期2/3⚠️待确认]",
        "US500_H1_long": "🧪 US500 H1 CB>=4+RSI<20做多 WR=100% n=11 hold=30 [数据不足]",
        "US30_H1_long": "✅ US30 H1 CB>=4+RSI<20做多 WR=92.9% n=14 hold=70 跨周期3/3✅",
        "US30_M1_EU_long": "🆕 US30 M1 EU CB>=4+RSI<14做多 WR=70.4% n=81 hold=30 [新发现]",
        "AUDUSD_US": "AUDUSD美盘RSI<16+CB>=3 hold=125 WR=77.8% n=45",
        "JP225_US": "JP225美盘RSI<14+CB>=2 hold=55 WR=73.4% n=64",
        "XAGUSD_US": "XAG美盘RSI<18+CB>=3 hold=105 WR=75.0% n=60",
        "XAGUSD_EU": "XAG欧盘RSI<14+CB>=3 hold=85 WR=86.5% n=37"
    },
    "warnings": [
        "🔴 H1数据最新停于13:00/M30停于13:30 UTC，美盘后半段数据缺失(US18+=M1/M5的1/30)",
        "🔴 US500 H1 P3无数据，跨周期统计不全(2/3)",
        "⚠️ M1/M5做空信号整体弱于做多，XAUUSD/XAGUSD/JP225/US500/US30做空均<60% WR",
        "⚠️ US30 M5未发现任何WR>65%的可靠策略(M1 EU勉强达到70%)",
        "⚠️ XAUUSD M30 Doji+RSI>75+us做空WR=100%但n=12无增长(连续3轮无新增)",
        "⚠️ XAGUSD M30 SHORT n=28无增长，需检查数据下载是否覆盖白银最新数据",
        "⚠️ XAGUSD M1 EU CB>=3+RSI<10 n=29跨周期仅2/3通过(P2 WR=57.1%)"
    ],
    "next_actions": [
        "round38_001: XAUUSD M1 US CB>=2+RSI<10 WR=82.8% n=58 → 跨周期验证+纳入best_known",
        "round38_002: XAGUSD M5 EU CB>=3+RSI<10 n=42→目标60积累监控",
        "round38_003: UKOIL M30做多 n=32→目标50，达标后正式纳入best_known",
        "round38_004: EURUSD H1做多月度跟踪(第6月)",
        "round38_005: US500 M5 EU CB>=4+RSI<14 n=73 跨周期再确认(P3需>60%)",
        "round38_006: XAGUSD M30 SHORT n=28→检查数据覆盖范围是否不足",
        "round38_007: US30 M1 EU CB>=4+RSI<14 n=81 → 跨周期验证+深度优化",
        "round38_008: JP225 H1/M30做多月度跟踪(第2月)"
    ]
}

with open(os.path.join(BASE, 'state', 'research_state.json'), 'w') as f:
    json.dump(state, f, ensure_ascii=False, indent=2)

print("✅ State updated successfully (current_round=37)")
