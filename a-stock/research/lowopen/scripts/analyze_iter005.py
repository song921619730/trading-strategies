import pandas as pd
df = pd.read_csv('F:/AIcoding_space/Hermes/strategies/a-stock/research/lowopen/logs/iter_005/results.csv')

print('=== TOP 20 RESULTS ===')
cols = ['sell_lg_ratio_max', 'buy_lg_ratio_min', 'net_mf_min', 'circ_mv_max', 'signal_count', 'avg_ret_5d', 'win_rate_5d', 'sharpe_5d']
top = df.sort_values('avg_ret_5d', ascending=False).head(20)
for i, row in top.iterrows():
    print(f'  sell={row["sell_lg_ratio_max"]:.2f} buy_lg={row["buy_lg_ratio_min"]:.2f} nmf={row["net_mf_min"]:.0f} cap={row["circ_mv_max"]:.0f} | sigs={row["signal_count"]:.0f} | 5D={row["avg_ret_5d"]:.4f} WR={row["win_rate_5d"]:.2%} Sh={row["sharpe_5d"]:.2f}')

print()
print('=== By sell_lg_ratio_max ===')
for sell in sorted(df['sell_lg_ratio_max'].unique()):
    subset = df[df['sell_lg_ratio_max'] == sell]
    print(f'  sell_max={sell:.2f}: avg_5D={subset["avg_ret_5d"].mean():.4f} avg_WR={subset["win_rate_5d"].mean():.2%} avg_sigs={subset["signal_count"].mean():.0f}')

print()
print('=== By buy_lg_ratio_min (sell_max=0.15 only) ===')
sub = df[df['sell_lg_ratio_max'] == 0.15]
for buy in sorted(sub['buy_lg_ratio_min'].unique()):
    s = sub[sub['buy_lg_ratio_min'] == buy]
    print(f'  buy_lg={buy:.2f}: avg_5D={s["avg_ret_5d"].mean():.4f} avg_WR={s["win_rate_5d"].mean():.2%} avg_sigs={s["signal_count"].mean():.0f}')

print()
print('=== Top when sell_max=0.15 AND buy_lg=0.05 ===')
best = df[(df['sell_lg_ratio_max'] == 0.15) & (df['buy_lg_ratio_min'] == 0.05)].sort_values('avg_ret_5d', ascending=False)
for i, row in best.iterrows():
    print(f'  nmf={row["net_mf_min"]:.0f} cap={row["circ_mv_max"]:.0f} | sigs={row["signal_count"]:.0f} | 5D={row["avg_ret_5d"]:.4f} WR={row["win_rate_5d"]:.2%} Sh={row["sharpe_5d"]:.2f}')
