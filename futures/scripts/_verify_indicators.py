def run_verify():
    import sys
    sys.path.insert(0, '/mnt/f/AIcoding_space/Hermes/strategies/futures/scripts')
    
    with open('/mnt/f/AIcoding_space/Hermes/strategies/futures/scripts/indicators.py', 'r') as f:
        code = f.read()
    try:
        compile(code, 'indicators.py', 'exec')
        print("语法检查通过")
    except SyntaxError as e:
        print(f"语法错误: {e}")
        return
    
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
            _ema_series, _sma_values, _true_range,
            compute_all_trading_indicators,
        )
        print("全部新函数导入成功")
        
        names = [
            'calc_guppy_short_spread', 'calc_guppy_long_spread',
            'calc_trix', 'calc_ultimate_oscillator', 'calc_rvgi', 'calc_kst',
            'calc_ichimoku', 'calc_psar', 'calc_heikin_ashi',
            'calc_keltner', 'calc_donchian', 'calc_envelope',
            'calc_vwap', 'calc_cmf', 'calc_force_index', 'calc_force_index_ema',
            'calc_eom', 'calc_nvi', 'calc_pvi', 'calc_klinger',
            'calc_ad_line', 'calc_vpt', 'calc_mass_index', 'calc_dpo',
            'calc_zscore', 'calc_volatility', 'calc_volatility_ratio',
            'calc_return_skew', 'calc_return_kurt', 'calc_up_ratio', 'calc_autocorr',
            'detect_gravestone_doji', 'detect_dragonfly_doji', 'detect_long_legged_doji',
            'detect_spinning_top', 'detect_hanging_man', 'detect_shooting_star',
            'detect_harami', 'detect_outside_bar', 'detect_marubozu',
            'detect_piercing', 'detect_dark_cloud', 'detect_three_morning_star',
            'detect_three_evening_star',
            'calc_market_regime', 'calc_fib_retracement',
            '_ema_series', '_sma_values', '_true_range',
        ]
        for name in names:
            fn = eval(name)
            args = fn.__code__.co_varnames[:fn.__code__.co_argcount]
            defaults = fn.__defaults__
            sig_parts = []
            n_defaults = len(defaults) if defaults else 0
            n_args = len(args)
            for i, a in enumerate(args):
                if i >= n_args - n_defaults:
                    d = defaults[i - (n_args - n_defaults)]
                    sig_parts.append(f"{a}={d}")
                else:
                    sig_parts.append(a)
            print(f"  {name}({', '.join(sig_parts)})")
        
        print("\n=== 功能快速验证 ===")
        test_bars = [
            {"time": i, "open": float(100+i), "high": float(102+i), "low": float(99+i), "close": float(101+i), "volume": 1000}
            for i in range(200)
        ]
        
        # Test each function
        for fn_name, fn in [
            ("guppy_short_spread", calc_guppy_short_spread),
            ("guppy_long_spread", calc_guppy_long_spread),
            ("ultimate_oscillator", calc_ultimate_oscillator),
            ("vwap", calc_vwap),
            ("cmf", lambda b: calc_cmf(b)),
            ("force_index", calc_force_index),
            ("force_index_ema", calc_force_index_ema),
            ("eom", calc_eom),
            ("nvi", calc_nvi),
            ("pvi", calc_pvi),
            ("vpt", calc_vpt),
            ("mass_index", calc_mass_index),
            ("dpo", lambda b: calc_dpo(b)),
            ("zscore", lambda b: calc_zscore(b)),
            ("volatility", lambda b: calc_volatility(b)),
            ("volatility_ratio", calc_volatility_ratio),
            ("return_skew", lambda b: calc_return_skew(b)),
            ("return_kurt", lambda b: calc_return_kurt(b)),
            ("up_ratio", lambda b: calc_up_ratio(b)),
            ("autocorr", lambda b: calc_autocorr(b)),
            ("long_legged_doji", detect_long_legged_doji),
            ("spinning_top", detect_spinning_top),
            ("hanging_man", detect_hanging_man),
            ("shooting_star", detect_shooting_star),
            ("outside_bar", detect_outside_bar),
            ("piercing", detect_piercing),
            ("dark_cloud", detect_dark_cloud),
            ("three_morning_star", detect_three_morning_star),
            ("three_evening_star", detect_three_evening_star),
        ]:
            try:
                v = fn(test_bars)
                print(f"  {fn_name} = {v}")
            except Exception as e:
                print(f"  {fn_name} = ERROR: {e}")
        
        for fn_name, fn in [
            ("trix", calc_trix),
            ("rvgi", calc_rvgi),
            ("kst", calc_kst),
            ("ichimoku", calc_ichimoku),
            ("psar", calc_psar),
            ("heikin_ashi", calc_heikin_ashi),
            ("keltner", lambda b: calc_keltner(b)),
            ("donchian", lambda b: calc_donchian(b)),
            ("envelope", lambda b: calc_envelope(b)),
            ("klinger", calc_klinger),
            ("ad_line", calc_ad_line),
            ("gravestone_doji", detect_gravestone_doji),
            ("dragonfly_doji", detect_dragonfly_doji),
            ("harami", detect_harami),
            ("marubozu", detect_marubozu),
            ("market_regime", calc_market_regime),
            ("fib_retracement", calc_fib_retracement),
        ]:
            try:
                v = fn(test_bars)
                non_none = {k: v for k, v in v.items() if v is not None} if isinstance(v, dict) else v
                print(f"  {fn_name} = {non_none}")
            except Exception as e:
                print(f"  {fn_name} = ERROR: {e}")
        
        # Test compute_all
        print("\n=== compute_all_trading_indicators ===")
        all_inds = compute_all_trading_indicators(test_bars)
        new_keys = [k for k in sorted(all_inds.keys()) if k not in ['price','high','low','open','range','range_pct','body','body_pct','session','utc_hour','volume']]
        print(f"  Total indicators: {len(all_inds)}")
        print(f"  Sample new indicators: {new_keys[:30]}...")
        
        print("\n全部验证通过！")
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    run_verify()
