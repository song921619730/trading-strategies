#!/usr/bin/env python3
"""Test CH connection"""
import sys
sys.path.insert(0, '/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167')
from ch_helper import ch_query

try:
    rows = ch_query('SELECT count(*) AS cnt FROM tushare.tushare_stock_daily FINAL WHERE trade_date >= toDate(\"2024-01-01\")')
    print('OK:', rows)
except Exception as e:
    print('Error:', type(e).__name__, str(e))
