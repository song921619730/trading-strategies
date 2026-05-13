#!/usr/bin/env python3
"""C6: deep panic + deep value + retail selloff — the ultimate reversal combo"""
import json
from urllib.request import Request, urlopen
from collections import defaultdict

CH_URL = "http://172.24.224.1:8123"
CH_USER = "ai_reader"  
CH_PASS = "OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ"
CH_DB = "tushare"

def chq(sql):
    url = f"{CH_URL}/?user={CH_USER}&password={CH_PASS}&database={CH_DB}&default_format=JSON"
    req = Request(url, data=sql.encode('utf-8'))
    req.add_header('Content-Type', 'text/plain')
    with urlopen(req, timeout=300) as resp:
        return json.loads(resp.read().decode('utf-8'))

def chqr(sql):
    return chq(sql).get('data', [])

MAX_DATE = '20260511'

# Load stock data
print("Loading stock data...")
all_daily = chqr(f"""
SELECT ts_code, trade_date, close
FROM (SELECT * FROM tushare.tushare_stock_daily FINAL)
WHERE trade_date >= '20200101' AND trade_date <= '{MAX_DATE}'
  AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%'
  AND ts_code NOT LIKE '920%' AND ts_code NOT LIKE '%ST%'
  AND close > 0
ORDER BY ts_code, trade_date
""")
print(f"Loaded {len(all_daily):,} rows")

stock_prices = defaultdict(list)
for row in all_daily:
    stock_prices[row['ts_code']].append((row['trade_date'], row['close']))

def fwd_returns(signals):
    res = {'5d':[],'10d':[],'20d':[]}
    for td,tc in signals:
        px = stock_prices.get(tc,[])
        if not px: continue
        idx = next((i for i,(d,_) in enumerate(px) if d==td), None)
        if idx is None: continue
        c0 = px[idx][1]
        if c0<=0: continue
        if idx+5<len(px): res['5d'].append((px[idx+5][1]/c0-1)*100)
        if idx+10<len(px): res['10d'].append((px[idx+10][1]/c0-1)*100)
        if idx+20<len(px): res['20d'].append((px[idx+20][1]/c0-1)*100)
    return res

def stats(r5,r10,r20):
    def _s(rl,l):
        if not rl: return {'l':l,'n':0,'avg':0,'wr':0,'shp':0}
        avg=sum(rl)/len(rl); w=sum(1 for r in rl if r>0); wr=w/len(rl)*100
        std=(sum((r-avg)**2 for r in rl)/(len(rl)-1))**0.5 if len(rl)>1 else 0
        shp=avg/std*(252/5)**0.5 if std>0.001 else 0
        sr=sorted(rl)
        return {'l':l,'n':len(rl),'avg':round(avg,2),'wr':round(wr,2),'shp':round(shp,2),
                'p10':round(sr[int(len(sr)*0.1)],2),'p50':round(sr[int(len(sr)*0.5)],2),'p90':round(sr[int(len(sr)*0.9)],2)}
    return {'5d':_s(r5,'5D'),'10d':_s(r10,'10D'),'20d':_s(r20,'20D')}

# C6: Deep panic + deep value + retail selling + micro cap
print("\nC6: 恐慌+深价值+散户割肉+微盘 — 跌≥7%+振幅≥7%+PE≤15+PB≤2+散户净卖出+CM≤30亿+底20%")
data = chqr(f"""
SELECT s.ts_code, s.trade_date
FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS s
INNER JOIN (SELECT * FROM tushare.tushare_moneyflow FINAL) AS m
  ON s.ts_code = m.ts_code AND s.trade_date = m.trade_date
INNER JOIN (SELECT * FROM tushare.tushare_daily_basic FINAL) AS b
  ON s.ts_code = b.ts_code AND s.trade_date = b.trade_date
WHERE s.trade_date >= '20200101' AND s.trade_date <= '{MAX_DATE}'
  AND s.ts_code NOT LIKE '30%' AND s.ts_code NOT LIKE '688%' 
  AND s.ts_code NOT LIKE '920%' AND s.ts_code NOT LIKE '%ST%'
  AND s.close <= s.low + (s.high - s.low) * 0.20
  AND s.pct_chg <= -7
  AND (s.high - s.low) / s.pre_close * 100 >= 7
  AND b.pe_ttm <= 15 AND b.pe_ttm > 0
  AND b.pb <= 2 AND b.pb > 0
  AND b.circ_mv <= 300000
  AND m.sell_sm_amount > m.buy_sm_amount
  AND m.net_mf_amount < 0
""")
print(f"Raw: {len(data)}")
signals = list(set((r['s.trade_date'], r['s.ts_code']) for r in data))
print(f"Unique: {len(signals)}")
if len(signals) >= 100:
    fwd = fwd_returns(signals)
    st = stats(fwd['5d'], fwd['10d'], fwd['20d'])
    print(f"N={st['5d']['n']:,} | R5={st['5d']['avg']:.2f}% | WR={st['5d']['wr']:.1f}% | Sharpe={st['5d']['shp']:.2f}")
    print(f"R10={st['10d']['avg']:.2f}% | R20={st['20d']['avg']:.2f}%")
    print(f"P10={st['5d']['p10']:.1f}% P50={st['5d']['p50']:.1f}% P90={st['5d']['p90']:.1f}%")
    passed = st['5d']['wr']>=52 and st['5d']['avg']>=3.0 and st['5d']['n']>=200
    print(f"{'✅' if passed else '❌'} PASS={passed}")
else:
    print("Too few signals")
