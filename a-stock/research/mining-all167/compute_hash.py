import hashlib, json

# C3 params
params_c3 = {
    'pct_chg_1d_min': -7,
    'pct_chg_1d_max': -2,
    'volume_ratio_min': 0.8,
    'circ_mv_max': 5000000000,
    'shibor_trend_10d': '下行',
    'close_position': '底40%',
    'market_cap_bucket': '小盘(<50亿)'
}
h_c3 = hashlib.md5(json.dumps(params_c3, sort_keys=True).encode()).hexdigest()[:11]
print(f'C3 hash: {h_c3}')

# C1 params
params_c1 = {
    'pct_chg_1d_min': -5,
    'pct_chg_1d_max': 2,
    'volume_ratio_min': 1.2,
    'net_mf_min': 350000,
    'circ_mv_max': 20000000000,
}
h_c1 = hashlib.md5(json.dumps(params_c1, sort_keys=True).encode()).hexdigest()[:11]
print(f'C1 hash: {h_c1}')

# C4 params
params_c4 = {
    'pct_chg_1d_min': 0,
    'pct_chg_1d_max': 999,
    'volume_ratio_min': 1.3,
    'circ_mv_max': 50000000000,
    'index_trend_20d': '沪深300上涨',
}
h_c4 = hashlib.md5(json.dumps(params_c4, sort_keys=True).encode()).hexdigest()[:11]
print(f'C4 hash: {h_c4}')

# C2 params (no signals)
params_c2 = {
    'pct_chg_1d_min': 2,
    'volume_ratio_min': 1.8,
    'circ_mv_min': 3000000000,
    'circ_mv_max': 50000000000,
    'net_mf_min': 250000,
}
h_c2 = hashlib.md5(json.dumps(params_c2, sort_keys=True).encode()).hexdigest()[:11]
print(f'C2 hash: {h_c2}')

# C5 params (no signals)
params_c5 = {
    'pct_chg_1d_min': 3,
    'volume_ratio_min': 2.0,
    'circ_mv_min': 3000000000,
    'circ_mv_max': 50000000000,
    'net_mf_min': 250000,
}
h_c5 = hashlib.md5(json.dumps(params_c5, sort_keys=True).encode()).hexdigest()[:11]
print(f'C5 hash: {h_c5}')
