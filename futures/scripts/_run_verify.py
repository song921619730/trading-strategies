import sys
sys.path.insert(0, '/mnt/f/AIcoding_space/Hermes/strategies/futures/scripts')

with open('/mnt/f/AIcoding_space/Hermes/strategies/futures/scripts/indicators.py', 'r') as f:
    code = f.read()

# Syntax check
try:
    compile(code, 'indicators.py', 'exec')
    print("SYNTAX OK")
except SyntaxError as e:
    print(f"SYNTAX ERROR: {e}")
    sys.exit(1)

# Import
try:
    from indicators import (
        calc_guppy_short_spread, calc_guppy_long_spread,
        calc_trix, calc_ultimate_oscillator, calc_rvgi, calc_kst,
        calc_ichimoku, calc_psar, calc_heikin_ashi,
        calc_keltner, calc_donchian, calc_envelope,
        calc_vwap, calc_cmf, calc_force_index, calc_force_index_ema,
        calc_eom, calc_nvi, calc_pvi, calc_klinger,
        calc_ad_line, calc_vpt, calc_mass_index, calc_dpo,
        calc_zscore, calc_volatility, calc_volatility_ratio,
        calc_return_skew, calc_return_kurt, calc_up_ratio, calc_autocorr,
        detect_gravestone_doji, detect_dragonfly_doji, detect_long_legged_doji,
        detect_spinning_top, detect_hanging_man, detect_shooting_star,
        detect_harami, detect_outside_bar, detect_marubozu,
        detect_piercing, detect_dark_cloud, detect_three_morning_star,
        detect_three_evening_star,
        calc_market_regime, calc_fib_retracement,
        compute_all_trading_indicators,
    )
    print("IMPORT OK")
except Exception as e:
    print(f"IMPORT ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Quick functional test
try:
    bars = [{"open": 100.0+i, "high": 102.0+i, "low": 99.0+i, "close": 101.0+i, "volume": 1000} for i in range(200)]
    
    assert calc_guppy_short_spread(bars) is not None
    assert calc_guppy_long_spread(bars) is not None
    assert calc_trix(bars)["trix"] is not None
    assert calc_ultimate_oscillator(bars) is not None
    assert calc_rvgi(bars)["rvg"] is not None
    assert calc_kst(bars)["kst"] is not None
    assert calc_ichimoku(bars)["tenkan_sen"] is not None
    assert calc_psar(bars)["psar"] is not None
    assert calc_heikin_ashi(bars)["ha_close"] is not None
    assert calc_keltner(bars)["upper"] is not None
    assert calc_donchian(bars)["upper"] is not None
    assert calc_envelope(bars)["upper"] is not None
    assert calc_vwap(bars) is not None
    assert calc_cmf(bars) is not None
    assert calc_force_index(bars) is not None
    assert calc_force_index_ema(bars) is not None
    assert calc_eom(bars) is not None
    assert calc_nvi(bars) is not None
    assert calc_pvi(bars) is not None
    assert calc_klinger(bars)["klinger"] is not None
    assert calc_ad_line(bars)["ad"] is not None
    assert calc_vpt(bars) is not None
    assert calc_mass_index(bars) is not None
    assert calc_dpo(bars) is not None
    assert calc_zscore(bars) is not None
    assert calc_volatility(bars) is not None
    assert calc_volatility_ratio(bars) is not None
    assert calc_return_skew(bars) is not None
    assert calc_return_kurt(bars) is not None
    assert calc_up_ratio(bars) is not None
    assert calc_autocorr(bars) is not None
    assert detect_gravestone_doji(bars) is not None
    assert detect_dragonfly_doji(bars) is not None
    assert isinstance(detect_long_legged_doji(bars), int)
    assert isinstance(detect_spinning_top(bars), int)
    assert isinstance(detect_hanging_man(bars), int)
    assert isinstance(detect_shooting_star(bars), int)
    assert detect_harami(bars) is not None
    assert isinstance(detect_outside_bar(bars), int)
    assert detect_marubozu(bars) is not None
    assert isinstance(detect_piercing(bars), int)
    assert isinstance(detect_dark_cloud(bars), int)
    assert isinstance(detect_three_morning_star(bars), int)
    assert isinstance(detect_three_evening_star(bars), int)
    assert calc_market_regime(bars) is not None
    assert calc_fib_retracement(bars) is not None
    assert len(compute_all_trading_indicators(bars)) > 50
    
    print("FUNCTIONAL TEST OK")
except Exception as e:
    print(f"FUNCTIONAL TEST ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()
print("ALL TESTS PASSED!")
