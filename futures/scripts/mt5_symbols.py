"""mt5_symbols.py — Exness Demo MT5 全部 19 个可用品种"""

MT5_SYMBOLS_19 = [
    # 贵金属
    "XAUUSD",  # 黄金
    "XAGUSD",  # 白银
    # 美股指数
    "US500",   # S&P 500
    "US30",    # Dow Jones
    "USTEC",   # Nasdaq 100
    "JP225",   # Nikkei 225
    "HK50",    # Hang Seng
    # 能源
    "USOIL",   # WTI 原油
    "UKOIL",   # Brent 原油
    "XNGUSD",  # 天然气
    # 商品金属
    "XCUUSD",  # 铜
    # 主要货币对
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "AUDUSD",
    "USDCHF",
    "NZDUSD",
    "USDCAD",
    # 美元指数
    "DXY",
]

# 分组快捷引用
FX_MAJOR = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF", "NZDUSD", "USDCAD"]
METALS = ["XAUUSD", "XAGUSD", "XCUUSD"]
INDICES = ["US500", "US30", "USTEC", "JP225", "HK50"]
ENERGY = ["USOIL", "UKOIL", "XNGUSD"]
DXY_ONLY = ["DXY"]

# 常用子集
MT5_SYMBOLS_14 = FX_MAJOR + METALS[:-1] + INDICES + ENERGY[:-1]
# = 14 old set: EURUSD,GBPUSD,USDJPY,AUDUSD,USDCHF, XAUUSD,XAGUSD, US500,US30,USTEC,JP225,HK50, USOIL,UKOIL
