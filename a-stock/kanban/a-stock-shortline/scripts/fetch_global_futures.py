import sys
sys.path.insert(0, r"F:\AIcoding_space\skills\global-futures\scripts")
from global_futures import GlobalFutures
import json, time
from datetime import datetime

gf = GlobalFutures()

commodities = {
    "谷物": ["Corn", "Soybean", "Wheat", "SoybeanMeal"],
    "软商品": ["Sugar11", "Cotton", "Canola"],
    "能源": ["CrudeOil", "BrentOil", "NaturalGas"],
    "金属": ["Gold", "Silver", "Copper"],
    "利率": ["Treasury10Y", "Treasury30Y"],
}

result = {}
result["retrievedAt"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
result["source"] = "global-futures"
result["categories"] = {}

all_names = []
for cat, names in commodities.items():
    all_names.extend(names)

# First: get all prices at once (built-in rate limiting)
print("Fetching all prices...", file=sys.stderr)
all_prices = gf.get_all_prices()
print(f"Got {len(all_prices)} prices", file=sys.stderr)

# Build price lookup
price_lookup = {}
for _, row in all_prices.iterrows():
    price_lookup[row["Code"]] = row.to_dict()

for category, names in commodities.items():
    result["categories"][category] = {}
    for name in names:
        entry = {}
        
        # Price from batch fetch
        if name in price_lookup:
            entry["price"] = price_lookup[name]
        else:
            entry["price"] = {"error": "not in price lookup"}
        
        time.sleep(4)
        
        # 3-month history
        for attempt in range(3):
            try:
                hist = gf.get_history(name, period="3mo", interval="1d")
                if hist is not None and len(hist) > 0:
                    first_close = float(hist.iloc[0]["Close"])
                    last_close = float(hist.iloc[-1]["Close"])
                    change_pct = round((last_close - first_close) / first_close * 100, 2)
                    entry["trend_3m"] = {
                        "start_date": str(hist.index[0].date()),
                        "end_date": str(hist.index[-1].date()),
                        "start_price": first_close,
                        "end_price": last_close,
                        "change_pct": change_pct,
                        "direction": "up" if change_pct > 0 else ("down" if change_pct < 0 else "flat"),
                    }
                else:
                    entry["trend_3m"] = {"error": "no history data"}
                break
            except Exception as e:
                err_str = str(e).lower()
                if "rate" in err_str or "too many" in err_str:
                    wait = 20 * (attempt + 1)
                    print(f"Rate limited for {name}, waiting {wait}s (attempt {attempt+1})", file=sys.stderr)
                    time.sleep(wait)
                else:
                    entry["trend_3m"] = {"error": str(e)}
                    break
        if "trend_3m" not in entry:
            entry["trend_3m"] = {"error": "max retries exceeded"}

        result["categories"][category][name] = entry

print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
