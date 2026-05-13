#!/usr/bin/env python3
"""Iteration 12 backtest - run all combo queries and save results."""
import json, hashlib, math, subprocess, sys, time

CH_USER = "ai_reader"
CH_PASS = "OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ"
CH_URL = "http://127.0.0.1:8123"
CH_DB = "tushare"
END_DATE = "20260511"

def ch_query(sql, timeout=120):
    with open('/tmp/ch_q.sql', 'w') as f:
        f.write(sql.rstrip().rstrip(";") + "\nFORMAT JSON")
    cmd = ["curl", "-s", "-X", "POST",
           f"{CH_URL}/?user={CH_USER}&password={CH_PASS}&max_execution_time={timeout}&database={CH_DB}",
           "--data-binary", "@/tmp/ch_q.sql"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout+10)
        return json.loads(result.stdout)
    except Exception as e:
        return {"error": str(e)[:500]}

def compute_stats(rows):
    n = len(rows)
    if n == 0:
        return {"signal_count": 0, "wr_5d": 0, "ret_5d": 0, "ret_10d": 0, "ret_20d": 0, "sharpe_5d": 0}
    def avg(lst): return sum(lst)/len(lst) if lst else 0
    def std(lst):
        if len(lst)<2: return 0
        m=avg(lst); return math.sqrt(sum((x-m)**2 for x in lst)/len(lst))
    stats={"signal_count": n}
    for k in ["ret_5d","ret_10d","ret_20d"]:
        vals = [r.get(k) for r in rows if r.get(k) is not None]
        if vals:
            stats[f"wr_{k.split('_')[1]}"] = round(sum(1 for v in vals if v>0)/len(vals)*100, 2)
            stats[k] = round(avg(vals)*100, 4)
        else:
            stats[f"wr_{k.split('_')[1]}"] = 0
            stats[k] = 0
    ret5 = [r.get("ret_5d") for r in rows if r.get("ret_5d") is not None]
    if len(ret5)>1:
        m5,s5=avg(ret5),std(ret5)
        stats["sharpe_5d"] = round(m5/s5*math.sqrt(252/5),4) if s5>0 else 0
    else:
        stats["sharpe_5d"] = 0
    return stats

# Base stock filter
ST_FILTER = "AND ts_code NOT IN (SELECT ts_code FROM tushare.tushare_stock_basic FINAL WHERE name LIKE '%ST%')"
BOARD_FILTER = "AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%' AND ts_code NOT LIKE '920%'"

def build_sql_base():
    """Return base subquery with position_ratio, amplitude computed."""
    return f"""
    SELECT ts_code, trade_date,
           close AS sig_close,
           pct_chg,
           (close - min60) / nullIf(max60 - min60, 0) AS position_ratio,
           (high - low) / nullIf(pre_close, 0) * 100 AS amplitude,
           groupArray(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 1 FOLLOWING AND 20 FOLLOWING) AS fc
    FROM (
        SELECT ts_code, trade_date, close, pct_chg, high, low, pre_close,
               min(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS min60,
               max(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS max60
        FROM tushare.tushare_stock_daily FINAL
        WHERE trade_date >= '20200101' AND trade_date <= '{END_DATE}'
          {BOARD_FILTER}
          {ST_FILTER}
    )
    """

def extract_returns(rows):
    """Convert ClickHouse rows with fc array to return values."""
    results = []
    for r in rows:
        fc = r.get("fc", [])
        sig_close = float(r["sig_close"])
        def get_ret(idx):
            if idx < len(fc) and fc[idx] is not None:
                fv = float(fc[idx])
                if fv > 0 and sig_close > 0:
                    return fv/sig_close - 1
            return None
        results.append({
            "ts_code": r["ts_code"],
            "trade_date": r["trade_date"],
            "ret_5d": get_ret(4),
            "ret_10d": get_ret(9),
            "ret_20d": get_ret(19),
        })
    return results

# ════════════════════════════════════════════
# Define all combos for Iteration 12
# ════════════════════════════════════════════

all_combos = []

# --- T2 动量趋势 ---
SQL_T2_BASE = build_sql_base()
all_combos.extend([
    {
        "analyst":"T2","name":"C1:X04扩容",
        "sql":f"SELECT ts_code,trade_date,sig_close,fc[5] as c5d,fc[10] as c10d,fc[20] as c20d FROM ({SQL_T2_BASE}) dw INNER JOIN (SELECT ts_code,trade_date,volume_ratio,circ_mv,turnover_rate FROM tushare.tushare_daily_basic FINAL) b USING (ts_code,trade_date) WHERE position_ratio<=0.20 AND pct_chg>=3 AND amplitude>=5 AND volume_ratio>=1.3 AND circ_mv<=500000 AND turnover_rate>=1 AND turnover_rate<=10 LIMIT 50000",
        "params":"底20%,涨≥3%,振幅≥5%,VR≥1.3,CM≤50亿,TR1-10%"
    },
    {
        "analyst":"T2","name":"C2:振幅测试",
        "sql":f"SELECT ts_code,trade_date,sig_close,fc[5] as c5d,fc[10] as c10d,fc[20] as c20d FROM ({SQL_T2_BASE}) dw INNER JOIN (SELECT ts_code,trade_date,volume_ratio,circ_mv FROM tushare.tushare_daily_basic FINAL) b USING (ts_code,trade_date) WHERE position_ratio<=0.10 AND pct_chg>=5 AND amplitude>=7 AND volume_ratio>=1.2 AND circ_mv<=300000 LIMIT 50000",
        "params":"底10%,涨≥5%,振幅≥7%,VR≥1.2,CM≤30亿"
    },
    {
        "analyst":"T2","name":"C3:缩量后放量",
        "sql":f"SELECT ts_code,trade_date,sig_close,fc[5] as c5d,fc[10] as c10d,fc[20] as c20d FROM ({SQL_T2_BASE}) dw INNER JOIN (SELECT ts_code,trade_date,volume_ratio,circ_mv FROM tushare.tushare_daily_basic FINAL) b USING (ts_code,trade_date) WHERE position_ratio<=0.20 AND pct_chg>=3 AND amplitude>=5 AND volume_ratio>=1.5 AND circ_mv<=500000 LIMIT 50000",
        "params":"底20%,涨≥3%,振幅≥5%,VR≥1.5,CM≤50亿"
    },
    {
        "analyst":"T2","name":"C4:趋势加速",
        "sql":f"SELECT ts_code,trade_date,sig_close,fc[5] as c5d,fc[10] as c10d,fc[20] as c20d FROM ({SQL_T2_BASE}) dw INNER JOIN (SELECT ts_code,trade_date,volume_ratio,circ_mv FROM tushare.tushare_daily_basic FINAL) b USING (ts_code,trade_date) WHERE position_ratio<=0.20 AND pct_chg>=2 AND amplitude>=5 AND volume_ratio>=1.0 AND circ_mv>=300000 AND circ_mv<=1000000 LIMIT 50000",
        "params":"底20%,涨≥2%,振幅≥5%,VR≥1.0,CM30-100亿"
    },
    {
        "analyst":"T2","name":"C5:底部跳空",
        "sql":f"SELECT ts_code,trade_date,sig_close,fc[5] as c5d,fc[10] as c10d,fc[20] as c20d FROM ({SQL_T2_BASE}) dw INNER JOIN (SELECT ts_code,trade_date,volume_ratio,circ_mv FROM tushare.tushare_daily_basic FINAL) b USING (ts_code,trade_date) WHERE position_ratio<=0.15 AND pct_chg>=2 AND amplitude>=5 AND volume_ratio>=1.2 AND circ_mv<=500000 LIMIT 50000",
        "params":"底15%,涨≥2%,振幅≥5%,VR≥1.2,CM≤50亿"
    },
])

# --- T3 反转低吸 ---
SQL_T3_BASE = build_sql_base()
all_combos.extend([
    {
        "analyst":"T3","name":"C1:恐慌-6%微调",
        "sql":f"SELECT ts_code,trade_date,sig_close,fc[5] as c5d,fc[10] as c10d,fc[20] as c20d FROM ({SQL_T3_BASE}) dw INNER JOIN (SELECT ts_code,trade_date,volume_ratio,circ_mv FROM tushare.tushare_daily_basic FINAL) b USING (ts_code,trade_date) WHERE pct_chg<=-6 AND position_ratio<=0.20 AND amplitude>=7 AND volume_ratio>=1.3 AND circ_mv<=500000 LIMIT 50000",
        "params":"恐慌≤-6%,底20%,振幅≥7%,VR≥1.3,CM≤50亿"
    },
    {
        "analyst":"T3","name":"C2:恐慌价值扩容",
        "sql":f"SELECT ts_code,trade_date,sig_close,fc[5] as c5d,fc[10] as c10d,fc[20] as c20d FROM ({SQL_T3_BASE}) dw INNER JOIN (SELECT ts_code,trade_date,volume_ratio,circ_mv,pe,pb FROM tushare.tushare_daily_basic FINAL) b USING (ts_code,trade_date) WHERE pct_chg<=-5 AND position_ratio<=0.20 AND amplitude>=6 AND volume_ratio>=1.0 AND circ_mv<=1000000 AND pe>0 AND pe<=20 AND pb>0 AND pb<=2 LIMIT 50000",
        "params":"恐慌≤-5%,底20%,振幅≥6%,VR≥1.0,PE≤20,PB≤2,CM≤100亿"
    },
    {
        "analyst":"T3","name":"C3:恐慌筹码锁定",
        "sql":f"SELECT ts_code,trade_date,sig_close,fc[5] as c5d,fc[10] as c10d,fc[20] as c20d FROM ({SQL_T3_BASE}) dw INNER JOIN (SELECT ts_code,trade_date,volume_ratio,circ_mv,turnover_rate FROM tushare.tushare_daily_basic FINAL) b USING (ts_code,trade_date) WHERE pct_chg<=-5 AND position_ratio<=0.20 AND amplitude>=5 AND volume_ratio>=1.2 AND circ_mv<=500000 AND turnover_rate>=0.3 AND turnover_rate<=3 LIMIT 50000",
        "params":"恐慌≤-5%,底20%,振幅≥5%,VR≥1.2,TR0.3-3%,CM≤50亿"
    },
    {
        "analyst":"T3","name":"C4:恐慌放量微盘",
        "sql":f"SELECT ts_code,trade_date,sig_close,fc[5] as c5d,fc[10] as c10d,fc[20] as c20d FROM ({SQL_T3_BASE}) dw INNER JOIN (SELECT ts_code,trade_date,volume_ratio,circ_mv FROM tushare.tushare_daily_basic FINAL) b USING (ts_code,trade_date) WHERE pct_chg<=-7 AND position_ratio<=0.15 AND amplitude>=7 AND volume_ratio>=1.5 AND circ_mv<=300000 LIMIT 50000",
        "params":"恐慌≤-7%,底15%,振幅≥7%,VR≥1.5,CM≤30亿"
    },
    {
        "analyst":"T3","name":"C5:恐慌放量企稳",
        "sql":f"SELECT ts_code,trade_date,sig_close,fc[5] as c5d,fc[10] as c10d,fc[20] as c20d FROM ({SQL_T3_BASE}) dw INNER JOIN (SELECT ts_code,trade_date,volume_ratio,circ_mv FROM tushare.tushare_daily_basic FINAL) b USING (ts_code,trade_date) WHERE pct_chg<=-3 AND position_ratio<=0.20 AND amplitude>=5 AND volume_ratio>=1.0 AND circ_mv<=500000 LIMIT 50000",
        "params":"恐慌≤-3%,底20%,振幅≥5%,VR≥1.0,CM≤50亿"
    },
])

# --- T5 基本面估值 ---
SQL_T5_BASE = build_sql_base()
all_combos.extend([
    {
        "analyst":"T5","name":"C1:极致深价值扩容",
        "sql":f"SELECT ts_code,trade_date,sig_close,fc[5] as c5d,fc[10] as c10d,fc[20] as c20d FROM ({SQL_T5_BASE}) dw INNER JOIN (SELECT ts_code,trade_date,volume_ratio,pe,pb,circ_mv,dv_ratio FROM tushare.tushare_daily_basic FINAL) b USING (ts_code,trade_date) WHERE position_ratio<=0.20 AND pe>0 AND pe<=8 AND pb>0 AND pb<=1 AND dv_ratio>=4 AND volume_ratio>=1.0 AND amplitude>=5 AND circ_mv<=500000 LIMIT 50000",
        "params":"PE≤8,PB≤1,dv≥4%,底20%,VR≥1.0,振幅≥5%,CM≤50亿"
    },
    {
        "analyst":"T5","name":"C2:高股息+振幅",
        "sql":f"SELECT ts_code,trade_date,sig_close,fc[5] as c5d,fc[10] as c10d,fc[20] as c20d FROM ({SQL_T5_BASE}) dw INNER JOIN (SELECT ts_code,trade_date,volume_ratio,pe,pb,circ_mv,dv_ratio FROM tushare.tushare_daily_basic FINAL) b USING (ts_code,trade_date) WHERE position_ratio<=0.30 AND pe>0 AND pe<=15 AND pb>0 AND pb<=2 AND dv_ratio>=3 AND volume_ratio>=1.2 AND amplitude>=6 AND circ_mv<=500000 LIMIT 50000",
        "params":"dv≥3%,PE≤15,PB≤2,底30%,VR≥1.2,振幅≥6%,CM≤50亿"
    },
    {
        "analyst":"T5","name":"C3:估值底部中盘",
        "sql":f"SELECT ts_code,trade_date,sig_close,fc[5] as c5d,fc[10] as c10d,fc[20] as c20d FROM ({SQL_T5_BASE}) dw INNER JOIN (SELECT ts_code,trade_date,volume_ratio,pe,pb,circ_mv,dv_ratio FROM tushare.tushare_daily_basic FINAL) b USING (ts_code,trade_date) WHERE position_ratio<=0.20 AND pe>0 AND pe<=12 AND pb>0 AND pb<=1.5 AND dv_ratio>=3 AND volume_ratio>=1.0 AND amplitude>=5 AND circ_mv>=300000 AND circ_mv<=1000000 LIMIT 50000",
        "params":"PE≤12,PB≤1.5,dv≥3%,底20%,VR≥1.0,振幅≥5%,CM30-100亿"
    },
    {
        "analyst":"T5","name":"C4:深底中阳价值",
        "sql":f"SELECT ts_code,trade_date,sig_close,fc[5] as c5d,fc[10] as c10d,fc[20] as c20d FROM ({SQL_T5_BASE}) dw INNER JOIN (SELECT ts_code,trade_date,volume_ratio,pe,pb,circ_mv,dv_ratio FROM tushare.tushare_daily_basic FINAL) b USING (ts_code,trade_date) WHERE pe>0 AND pe<=20 AND pb>0 AND pb<=2 AND dv_ratio>=2 AND position_ratio<=0.20 AND pct_chg>=2 AND amplitude>=5 AND volume_ratio>=1.3 AND circ_mv<=500000 LIMIT 50000",
        "params":"PE≤20,PB≤2,dv≥2%,底20%,涨≥2%,VR≥1.3,CM≤50亿"
    },
    {
        "analyst":"T5","name":"C5:超低PB深底",
        "sql":f"SELECT ts_code,trade_date,sig_close,fc[5] as c5d,fc[10] as c10d,fc[20] as c20d FROM ({SQL_T5_BASE}) dw INNER JOIN (SELECT ts_code,trade_date,volume_ratio,pe,pb,circ_mv,dv_ratio FROM tushare.tushare_daily_basic FINAL) b USING (ts_code,trade_date) WHERE pb>0 AND pb<=1.2 AND pe>0 AND pe<=15 AND position_ratio<=0.10 AND pct_chg>=3 AND amplitude>=5 AND volume_ratio>=1.2 AND circ_mv<=500000 LIMIT 50000",
        "params":"PB≤1.2,PE≤15,底10%,涨≥3%,振幅≥5%,VR≥1.2,CM≤50亿"
    },
])

# --- T6 板块轮动 ---
SQL_T6_BASE = build_sql_base()
all_combos.extend([
    {
        "analyst":"T6","name":"C1:板块恐慌筹码锁定",
        "sql":f"SELECT ts_code,trade_date,sig_close,fc[5] as c5d,fc[10] as c10d,fc[20] as c20d FROM ({SQL_T6_BASE}) dw INNER JOIN (SELECT ts_code,trade_date,volume_ratio,circ_mv,turnover_rate FROM tushare.tushare_daily_basic FINAL) b USING (ts_code,trade_date) WHERE pct_chg<=-5 AND position_ratio<=0.20 AND amplitude>=6 AND volume_ratio>=1.5 AND circ_mv<=500000 AND turnover_rate>=0.3 AND turnover_rate<=3 LIMIT 50000",
        "params":"恐慌≤-5%,底20%,振幅≥6%,VR≥1.5,TR0.3-3%,CM≤50亿"
    },
    {
        "analyst":"T6","name":"C2:深底大振幅微盘",
        "sql":f"SELECT ts_code,trade_date,sig_close,fc[5] as c5d,fc[10] as c10d,fc[20] as c20d FROM ({SQL_T6_BASE}) dw INNER JOIN (SELECT ts_code,trade_date,volume_ratio,circ_mv FROM tushare.tushare_daily_basic FINAL) b USING (ts_code,trade_date) WHERE position_ratio<=0.10 AND amplitude>=7 AND volume_ratio>=1.0 AND circ_mv<=300000 LIMIT 50000",
        "params":"底10%,振幅≥7%,VR≥1.0,CM≤30亿"
    },
    {
        "analyst":"T6","name":"C3:深底中盘微盘",
        "sql":f"SELECT ts_code,trade_date,sig_close,fc[5] as c5d,fc[10] as c10d,fc[20] as c20d FROM ({SQL_T6_BASE}) dw INNER JOIN (SELECT ts_code,trade_date,volume_ratio,circ_mv FROM tushare.tushare_daily_basic FINAL) b USING (ts_code,trade_date) WHERE position_ratio<=0.20 AND pct_chg>=2 AND amplitude>=5 AND volume_ratio>=1.3 AND circ_mv>=300000 AND circ_mv<=1000000 LIMIT 50000",
        "params":"底20%,涨≥2%,振幅≥5%,VR≥1.3,CM30-100亿"
    },
    {
        "analyst":"T6","name":"C4:恐慌价值反弹",
        "sql":f"SELECT ts_code,trade_date,sig_close,fc[5] as c5d,fc[10] as c10d,fc[20] as c20d FROM ({SQL_T6_BASE}) dw INNER JOIN (SELECT ts_code,trade_date,volume_ratio,circ_mv,pe,pb FROM tushare.tushare_daily_basic FINAL) b USING (ts_code,trade_date) WHERE pct_chg<=-5 AND position_ratio<=0.20 AND amplitude>=5 AND volume_ratio>=1.2 AND circ_mv<=500000 AND pe>0 AND pe<=30 AND pb>0 AND pb<=3 LIMIT 50000",
        "params":"恐慌≤-5%,底20%,振幅≥5%,VR≥1.2,PE≤30,PB≤3,CM≤50亿"
    },
    {
        "analyst":"T6","name":"C5:底部中阳放量中小盘",
        "sql":f"SELECT ts_code,trade_date,sig_close,fc[5] as c5d,fc[10] as c10d,fc[20] as c20d FROM ({SQL_T6_BASE}) dw INNER JOIN (SELECT ts_code,trade_date,volume_ratio,circ_mv FROM tushare.tushare_daily_basic FINAL) b USING (ts_code,trade_date) WHERE position_ratio<=0.20 AND pct_chg>=3 AND amplitude>=5 AND volume_ratio>=1.3 AND circ_mv>=300000 AND circ_mv<=1000000 LIMIT 50000",
        "params":"底20%,涨≥3%,振幅≥5%,VR≥1.3,CM30-100亿"
    },
])

# --- T7 跨市场联动 ---
SQL_T7_BASE = build_sql_base()
all_combos.extend([
    {
        "analyst":"T7","name":"C1:恐慌放量中小盘",
        "sql":f"SELECT ts_code,trade_date,sig_close,fc[5] as c5d,fc[10] as c10d,fc[20] as c20d FROM ({SQL_T7_BASE}) dw INNER JOIN (SELECT ts_code,trade_date,volume_ratio,circ_mv FROM tushare.tushare_daily_basic FINAL) b USING (ts_code,trade_date) WHERE pct_chg<=-5 AND position_ratio<=0.20 AND amplitude>=7 AND volume_ratio>=1.3 AND circ_mv>=300000 AND circ_mv<=1000000 LIMIT 50000",
        "params":"恐慌≤-5%,底20%,振幅≥7%,VR≥1.3,CM30-100亿"
    },
    {
        "analyst":"T7","name":"C2:恐慌放量企稳中小盘",
        "sql":f"SELECT ts_code,trade_date,sig_close,fc[5] as c5d,fc[10] as c10d,fc[20] as c20d FROM ({SQL_T7_BASE}) dw INNER JOIN (SELECT ts_code,trade_date,volume_ratio,circ_mv FROM tushare.tushare_daily_basic FINAL) b USING (ts_code,trade_date) WHERE pct_chg<=-5 AND position_ratio<=0.20 AND amplitude>=5 AND volume_ratio>=1.0 AND circ_mv>=300000 AND circ_mv<=1000000 LIMIT 50000",
        "params":"恐慌≤-5%,底20%,振幅≥5%,VR≥1.0,CM30-100亿"
    },
    {
        "analyst":"T7","name":"C3:底部放量企稳中盘",
        "sql":f"SELECT ts_code,trade_date,sig_close,fc[5] as c5d,fc[10] as c10d,fc[20] as c20d FROM ({SQL_T7_BASE}) dw INNER JOIN (SELECT ts_code,trade_date,volume_ratio,circ_mv FROM tushare.tushare_daily_basic FINAL) b USING (ts_code,trade_date) WHERE position_ratio<=0.20 AND pct_chg>=0 AND amplitude>=5 AND volume_ratio>=1.0 AND circ_mv>=300000 AND circ_mv<=1000000 LIMIT 50000",
        "params":"底20%,企稳(pct≥0),振幅≥5%,VR≥1.0,CM30-100亿"
    },
    {
        "analyst":"T7","name":"C4:恐慌放量深底微盘",
        "sql":f"SELECT ts_code,trade_date,sig_close,fc[5] as c5d,fc[10] as c10d,fc[20] as c20d FROM ({SQL_T7_BASE}) dw INNER JOIN (SELECT ts_code,trade_date,volume_ratio,circ_mv FROM tushare.tushare_daily_basic FINAL) b USING (ts_code,trade_date) WHERE pct_chg<=-5 AND position_ratio<=0.20 AND amplitude>=7 AND volume_ratio>=1.3 AND circ_mv<=300000 LIMIT 50000",
        "params":"恐慌≤-5%,底20%,振幅≥7%,VR≥1.3,CM≤30亿"
    },
    {
        "analyst":"T7","name":"C5:持续放量企稳中盘",
        "sql":f"SELECT ts_code,trade_date,sig_close,fc[5] as c5d,fc[10] as c10d,fc[20] as c20d FROM ({SQL_T7_BASE}) dw INNER JOIN (SELECT ts_code,trade_date,volume_ratio,circ_mv FROM tushare.tushare_daily_basic FINAL) b USING (ts_code,trade_date) WHERE position_ratio<=0.10 AND pct_chg>=0 AND amplitude>=5 AND volume_ratio>=1.0 AND circ_mv>=300000 AND circ_mv<=1000000 LIMIT 50000",
        "params":"底10%,企稳(pct≥0),振幅≥5%,VR≥1.0,CM30-100亿"
    },
])

# --- T8 量价形态 ---
SQL_T8_BASE = build_sql_base()
all_combos.extend([
    {
        "analyst":"T8","name":"C1:底部放量十字星",
        "sql":f"SELECT ts_code,trade_date,sig_close,fc[5] as c5d,fc[10] as c10d,fc[20] as c20d FROM ({SQL_T8_BASE}) dw INNER JOIN (SELECT ts_code,trade_date,volume_ratio,circ_mv FROM tushare.tushare_daily_basic FINAL) b USING (ts_code,trade_date) WHERE position_ratio<=0.20 AND amplitude>=5 AND volume_ratio>=1.3 AND circ_mv<=500000 AND pct_chg>=0 AND pct_chg<=2 LIMIT 50000",
        "params":"底20%,振幅≥5%,VR≥1.3,CM≤50亿"
    },
    {
        "analyst":"T8","name":"C2:底部放量中小阳",
        "sql":f"SELECT ts_code,trade_date,sig_close,fc[5] as c5d,fc[10] as c10d,fc[20] as c20d FROM ({SQL_T8_BASE}) dw INNER JOIN (SELECT ts_code,trade_date,volume_ratio,circ_mv FROM tushare.tushare_daily_basic FINAL) b USING (ts_code,trade_date) WHERE position_ratio<=0.20 AND pct_chg>=2 AND amplitude>=6 AND volume_ratio>=1.3 AND circ_mv<=500000 LIMIT 50000",
        "params":"底20%,涨≥2%,振幅≥6%,VR≥1.3,CM≤50亿"
    },
    {
        "analyst":"T8","name":"C3:深底大振幅微盘",
        "sql":f"SELECT ts_code,trade_date,sig_close,fc[5] as c5d,fc[10] as c10d,fc[20] as c20d FROM ({SQL_T8_BASE}) dw INNER JOIN (SELECT ts_code,trade_date,volume_ratio,circ_mv FROM tushare.tushare_daily_basic FINAL) b USING (ts_code,trade_date) WHERE position_ratio<=0.10 AND pct_chg>=3 AND amplitude>=6 AND volume_ratio>=1.3 AND circ_mv<=300000 LIMIT 50000",
        "params":"底10%,涨≥3%,振幅≥6%,VR≥1.3,CM≤30亿"
    },
    {
        "analyst":"T8","name":"C4:底部反转放量中小盘",
        "sql":f"SELECT ts_code,trade_date,sig_close,fc[5] as c5d,fc[10] as c10d,fc[20] as c20d FROM ({SQL_T8_BASE}) dw INNER JOIN (SELECT ts_code,trade_date,volume_ratio,circ_mv FROM tushare.tushare_daily_basic FINAL) b USING (ts_code,trade_date) WHERE position_ratio<=0.20 AND pct_chg>=3 AND amplitude>=5 AND volume_ratio>=1.5 AND circ_mv>=300000 AND circ_mv<=1000000 LIMIT 50000",
        "params":"底20%,涨≥3%,振幅≥5%,VR≥1.5,CM30-100亿"
    },
    {
        "analyst":"T8","name":"C5:底部中阳放量微盘",
        "sql":f"SELECT ts_code,trade_date,sig_close,fc[5] as c5d,fc[10] as c10d,fc[20] as c20d FROM ({SQL_T8_BASE}) dw INNER JOIN (SELECT ts_code,trade_date,volume_ratio,circ_mv FROM tushare.tushare_daily_basic FINAL) b USING (ts_code,trade_date) WHERE position_ratio<=0.20 AND pct_chg>=3 AND amplitude>=5 AND volume_ratio>=1.5 AND circ_mv<=300000 LIMIT 50000",
        "params":"底20%,涨≥3%,振幅≥5%,VR≥1.5,CM≤30亿"
    },
])

print(f"Total combos: {len(all_combos)}")
results = []

for i, combo in enumerate(all_combos):
    name = f"{combo['analyst']}-{combo['name']}"
    print(f"\n[{i+1}/{len(all_combos)}] {name}...")
    t0 = time.time()
    data = ch_query(combo["sql"], timeout=180)
    elapsed = time.time()-t0
    print(f"  Query time: {elapsed:.1f}s")

    if "error" in data:
        print(f"  ERROR: {str(data['error'])[:200]}")
        results.append({**combo, "status":"error", "error":str(data["error"])[:500], "stats":None})
        continue

    rows = data.get("data", [])
    print(f"  Rows: {len(rows)}")

    if len(rows) == 0:
        results.append({**combo, "status":"empty", "stats":{"signal_count":0}, "rows":[]})
        continue

    # Extract returns from the query results
    rets = []
    for r in rows:
        sig_close = float(r.get("sig_close",0) or 0)
        if sig_close <= 0: continue
        def calc_ret(col_name):
            v = r.get(col_name)
            if v is not None:
                fv = float(v)
                if fv > 0 and sig_close > 0:
                    return fv / sig_close - 1
            return None
        rets.append({
            "ret_5d": calc_ret("c5d"),
            "ret_10d": calc_ret("c10d"),
            "ret_20d": calc_ret("c20d"),
        })

    stats = compute_stats(rets)
    print(f"  signals={stats['signal_count']}, WR5d={stats.get('wr_5d',0)}%, R5d={stats.get('ret_5d',0)}%, R10d={stats.get('ret_10d',0)}%, SR5d={stats.get('sharpe_5d',0)}")
    results.append({**combo, "status":"ok", "stats":stats, "row_count":len(rows)})

# Save results
with open("/tmp/iter12_all_results.json", "w") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print("\n" + "="*60)
print("ITERATION 12 — ALL RESULTS SUMMARY")
print("="*60)
passed = []
for r in results:
    if r.get("stats") and r["stats"].get("signal_count",0) >= 200:
        s=r["stats"]
        ok = "✅" if s.get("wr_5d",0)>=52 and s.get("ret_5d",0)>=3 else "❌"
        name=f"{r['analyst']}-{r['name']}"
        print(f"{ok} {name}: N={s['signal_count']}, WR5d={s.get('wr_5d',0)}%, R5d={s.get('ret_5d',0)}%, R10d={s.get('ret_10d',0)}%, SR5d={s.get('sharpe_5d',0)}")
        if ok=="✅":
            passed.append(r)
    elif r.get("status")=="empty":
        print(f"⬜ {r['analyst']}-{r['name']}: No signals")
    elif r.get("status")=="error":
        print(f"⚠️ {r['analyst']}-{r['name']}: ERROR")

print(f"\nTotal: {len(results)} combos, Pass: {len(passed)}")
print(f"Results saved to /tmp/iter12_all_results.json")
