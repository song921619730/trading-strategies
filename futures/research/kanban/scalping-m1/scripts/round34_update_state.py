#!/usr/bin/env python3
"""Update research state after round34"""
import json
from datetime import datetime

state = {
    "current_round": 34,
    "last_run": datetime.now().strftime("%Y-%m-%d %H:%M"),
    "status": "completed",
    "hypotheses": {
        "round34_001": "XAUUSD M1 EU CB>=3+RSI<10 深度验证 — WR=97.2% n=36 hold=55 Bootstrap CI=[91.7%,100.0%]；跨周期3/3通过(P1=91.7% P2=100% P3=100%)；hold敏感性稳定(80-97%)；点差成本需核实(M1原始点差195.8pt可能为MT5原始单位)。结论:🧪 极高胜率模式已通过跨周期验证，待成本核实后正式纳入",
        "round34_002": "USDJPY H1 做多月度跟踪 — CB>=5+RSI<25 WR=100% n=17 hold=185；月度跟踪2026-02~04 n=10 WR=100% avg=0.45%；宽松版CB>=4+RSI<30 WR=93.5% n=31。结论:✅ 正式纳入best_known，开启月度跟踪",
        "round34_003": "双枪策略月度跟踪 — 欧盘n=70 WR=77.1%；美盘n=122 WR=80.3%；组合n=192 WR=79.2% (38.4次/月)；2026-05本月欧盘100%(n=5)美盘80%(n=15)。结论:✅ 持续有效，关注2026-06~07回撤窗口",
        "round34_004": "USOIL M30欧洲盘做空验证 — CBull>=5+RSI>75+europe WR=52.9% n=17 hold=40 (Round33报告的88.2% hold=80未通过跨hold扫描)。全样本CBull>=4+RSI>80 WR=60.5% n=38。结论:⏳ n不足且WR不稳定，需继续积累",
        "round34_005": "XAGUSD M30做空策略重做(方向修正) — CBull>=4+RSI>80 SHORT WR=78.6% n=28 hold=100 CI=[64.3%,92.9%] 跨周期3/3✅。CBull>=5+RSI>80 WR=82.4% n=17。CBull>=6+RSI>80 WR=90.0% n=10。结论:✅ 方向修正后仍有统计显著性，推荐CBull>=4+RSI>80做空(hold=100)纳入候补",
        "round34_006": "GBPUSD积累检查 — n=26/30 缺口=4(无新增数据)；AUDUSD n=45✅；JP225 n=64✅；XAGUSD美盘n=60✅(增长+29)。结论:📡 GBPUSD需等美盘数据更新",
        "round34_007": "XAUUSD M5新时段探索 — EU hour=8 RSI<18+CB>=4 WR=73.1% n=26 hold=5；US 13-14 RSI<20+CB>=3 WR=65.6% n=125 hold=35；US 17-18 RSI<20+CB>=3 WR=65.8% n=76 hold=65。结论:🧪 US盘初/盘后策略有潜力(>65%WR, n>50)"
    },
    "best_known": {
        "XAUUSD_M5_EU": "双枪欧盘做多XAU: M5 EU 9-11 RSI<18+CB>=4 hold=42 WR=77.1% n=70",
        "XAUUSD_M5_US": "双枪美盘做多XAU: M5 US 15-16 RSI<20+CB>=2 hold=115 WR=80.3% n=122",
        "XAUUSD_M5_combo": "双枪组合(欧+美): WR=79.2% n=192 [38次/月]",
        "XAUUSD_resonance_us": "共振美盘→XAU: M5 US 15-16 RSI<18+CB>=1 hold=115 WR=81.7% n=109",
        "XAUUSD_M1_EU_extreme": "🏆 XAUUSD M1 EU CB>=3+RSI<10 WR=97.2% n=36 hold=55 [跨周期3/3通过✅]",
        "XAUUSD_M1_EU_strong": "XAUUSD M1 EU CB>=4+RSI<10 WR=96.6% n=29 hold=55",
        "XAUUSD_M1_US_extreme": "XAUUSD M1 US CB>=3+RSI<10 WR=86.4% n=44 hold=30",
        "USDJPY_H1_long": "✅ USDJPY H1 CB>=5+RSI<25做多 WR=100% n=17 hold=185 [月度跟踪100%✅正式纳入]",
        "USDJPY_H1_long_loose": "USDJPY H1 CB>=4+RSI<30做多 WR=93.5% n=31 hold=190",
        "AUDUSD_US": "AUDUSD美盘RSI<16+CB>=3 hold=125 WR=77.8% n=45 [✅已达标]",
        "GBPUSD_US": "GBPUSD美盘RSI<14+CB>=3 hold=145 WR=69.2% n=26 [⏳n=26/30]",
        "JP225_US": "JP225美盘RSI<14+CB>=2 hold=55 WR=73.4% n=64",
        "XAGUSD_US": "XAG美盘RSI<18+CB>=3 hold=105 WR=75.0% n=60",
        "XAGUSD_EU": "XAG欧盘RSI<14+CB>=3 hold=85 WR=86.5% n=37",
        "XAGUSD_M30_SHORT": "🆕 XAGUSD M30 SHORT CBull>=4+RSI>80 WR=78.6% n=28 hold=100 CI=[64.3%,92.9%] 跨周期3/3✅",
        "XAGUSD_M30_SHORT_strong": "XAGUSD M30 SHORT CBull>=5+RSI>80 WR=82.4% n=17 hold=100",
        "USOIL_M30_SHORT": "USOIL M30 CBull>=4+RSI>80做空 WR=60.5% n=38 hold=140 [⏳边缘]",
        "XAUUSD_M5_US_open": "🧪 XAUUSD M5 US 13-14 RSI<20+CB>=3 WR=65.6% n=125 hold=35 [新发现]",
        "XAUUSD_M5_US_close": "🧪 XAUUSD M5 US 17-18 RSI<20+CB>=3 WR=65.8% n=76 hold=65 [新发现]"
    },
    "warnings": [
        "🔴 XAUUSD M1点差成本过高(原始spread=195.8pt)，需核实MT5 spread单位",
        "🔴 M1/M5数据最新为13:45/13:48 UTC，美盘后半段(18+ UTC)可能未覆盖",
        "⚠️ USOIL M30欧洲盘做空WR从之前报告88.2%降至52.9%，可能因hold参数不同",
        "⚠️ GBPUSD n=26/30无增长，美盘数据未更新",
        "⚠️ US500/US30 M5指数策略WR仅51-57%，未达到可用阈值(≥60%)"
    ],
    "next_actions": [
        "round35_001: XAUUSD M1 EU CB>=3+RSI<10 点差成本核实 — 需检查MT5 spread原始单位，若实际成本<0.1%则正式纳入实盘",
        "round35_002: USDJPY H1 持续月度跟踪 — 首次正式月度跟踪",
        "round35_003: 双枪策略月度跟踪 — 2026-06~07是关键回撤验证窗口",
        "round35_004: XAGUSD M30 SHORT继续积累 — CBull>=4+RSI>80 n=28→目标50",
        "round35_005: GBPUSD继续监测 — 等待美盘数据更新补齐缺口",
        "round35_006: XAUUSD M5 US盘初策略(EU hour=8)交叉验证 — WR=73.1% n=26需跨周期验证",
        "round35_007: MT5数据下载时间调整 — 当前~13 UTC需改为18-20 UTC覆盖完整美盘",
        "round35_008: XAUUSD M5 US 13-14/17-18策略深度验证 — WR>65% n>50需Bootstrap验证"
    ]
}

with open('/mnt/f/AIcoding_space/Hermes/strategies/futures/research/kanban/scalping-m1/state/research_state.json', 'w') as f:
    json.dump(state, f, ensure_ascii=False, indent=2)

print("State updated successfully (current_round=34)")
