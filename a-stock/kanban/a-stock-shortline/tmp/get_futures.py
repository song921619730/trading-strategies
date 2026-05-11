
import sys
sys.path.insert(0, r"F:\AIcoding_space\skills\global-futures\scripts")
import time, json

commodities = {
    "谷物": ["Corn", "Soybean", "Wheat", "SoybeanMeal"],
    "软商品": ["Sugar11", "Cotton", "Canola"],
    "能源": ["CrudeOil", "BrentOil", "NaturalGas"],
    "金属": ["Gold", "Silver", "Copper"],
    "利率": ["Treasury10Y", "Treasury30Y"]
}

tickers = {
    "Corn": "ZC=F", "Soybean": "ZS=F", "Wheat": "ZW=F", "SoybeanMeal": "ZM=F",
    "Sugar11": "SB=F", "Cotton": "CT=F", "Canola": "RS=F",
    "CrudeOil": "CL=F", "BrentOil": "BZ=F", "NaturalGas": "NG=F",
    "Gold": "GC=F", "Silver": "SI=F", "Copper": "HG=F",
    "Treasury10Y": "ZN=F", "Treasury30Y": "ZB=F"
}

names_cn = {
    "Corn": "玉米", "Soybean": "大豆", "Wheat": "小麦", "SoybeanMeal": "豆粕",
    "Sugar11": "糖11号", "Cotton": "棉花", "Canola": "油菜籽",
    "CrudeOil": "WTI原油", "BrentOil": "布伦特原油", "NaturalGas": "天然气",
    "Gold": "黄金", "Silver": "白银", "Copper": "铜",
    "Treasury10Y": "10年期美债", "Treasury30Y": "30年期美债"
}

import yfinance as yf

results = {}

for category, items in commodities.items():
    results[category] = {}
    for item in items:
        entry = {}
        ticker = yf.Ticker(tickers[item])
        
        price_ok = False
        for attempt in range(3):
            try:
                hist = ticker.history(period="5d", interval="1d")
                if hist is not None and len(hist) > 0:
                    last = hist.iloc[-1]
                    entry["price"] = {
                        "code": item, "yahoo": tickers[item], "name": names_cn[item],
                        "price": round(float(last["Close"]), 4),
                        "open": round(float(last["Open"]), 4),
                        "high": round(float(last["High"]), 4),
                        "low": round(float(last["Low"]), 4),
                        "close": round(float(last["Close"]), 4),
                        "volume": int(last["Volume"]),
                        "time": str(hist.index[-1].date())
                    }
                    if len(hist) >= 2:
                        prev_close = float(hist.iloc[-2]["Close"])
                        curr_close = float(last["Close"])
                        daily_pct = (curr_close - prev_close) / prev_close * 100
                        entry["price"]["daily_change_pct"] = round(daily_pct, 2)
                    price_ok = True
                    break
            except Exception as e:
                if "Rate" in str(e) and attempt < 2:
                    time.sleep(30 * (attempt + 1))
                    continue
                entry["price"] = {"error": str(e)}
                break
        
        if not price_ok and "price" not in entry:
            entry["price"] = {"error": "failed after retries"}
        
        hist_ok = False
        for attempt in range(3):
            try:
                time.sleep(2)
                hist3m = ticker.history(period="3mo", interval="1d")
                if hist3m is not None and len(hist3m) > 0:
                    closes = hist3m["Close"].dropna().tolist()
                    if len(closes) >= 2:
                        pct_3m = (closes[-1] - closes[0]) / closes[0] * 100
                        entry["trend_3m"] = {
                            "start_price": round(closes[0], 4),
                            "end_price": round(closes[-1], 4),
                            "pct_change": round(pct_3m, 2),
                            "direction": "up" if pct_3m > 0 else "down",
                            "num_bars": len(closes)
                        }
                    else:
                        entry["trend_3m"] = {"error": "insufficient data"}
                    hist_ok = True
                    break
            except Exception as e:
                if "Rate" in str(e) and attempt < 2:
                    time.sleep(30 * (attempt + 1))
                    continue
                entry["trend_3m"] = {"error": str(e)}
                break
        
        if not hist_ok and "trend_3m" not in entry:
            entry["trend_3m"] = {"error": "failed after retries"}
        
        results[category][item] = entry
        time.sleep(3)

print(json.dumps(results, ensure_ascii=False, indent=2))
